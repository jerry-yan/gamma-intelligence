"""
Modified jobs orchestrator for edgar_scheduler_2.
Includes Watchlist support during earnings periods.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Dict, List

from django.db import models
from asgiref.sync import sync_to_async

from EDGAR_bot.core import config, edgar_client, ticker_map
from EDGAR_bot.core.state import StateDB
from EDGAR_bot.core.utils import _as_date
from EDGAR_bot.models import Watchlist

LOGGER = logging.getLogger("jobs_v2")


async def _handle_ticker(
    sem: asyncio.Semaphore,
    state: StateDB,
    ticker: str,
    cik: str,
) -> None:
    """
    Process one ticker (list → download → ingest).

    * Every *row* we pass downstream now carries the originating **ticker**
      so that `download_filing()` and the OpenAI ingestion pipeline never
      lose that context.
    """
    async with sem:  # global concurrency cap
        # ── 1. recent SEC rows ──────────────────────────────────────────
        try:
            api_rows: List[Dict] = edgar_client.list_recent_filings(cik)
        except Exception as exc:  # network / SEC error
            LOGGER.error("Submissions fetch failed for %s (%s): %s", ticker, cik, exc)
            return

        # ── 2. skip already-seen or disallowed rows ────────────────────
        rows: list[dict] = []
        for r in api_rows:
            if r["form"] not in config.ALLOWED_FORMS:
                continue
            if _as_date(r["filing_date"]) < config.START_DATE:
                continue
            if await state.seen(cik, r["accession"]):
                continue

            r["ticker"] = ticker  # ←★ ALWAYS attach the ticker ★
            rows.append(r)

        LOGGER.info("Found %d new filings for %s (%s)", len(rows), ticker, cik)

        # ── 3. download + ingest each remaining filing ─────────────────
        for r in rows:
            filing_date = _as_date(r["filing_date"])

            # race-safe double-check
            if filing_date < config.START_DATE or await state.seen(cik, r["accession"]):
                continue

            LOGGER.info(
                "Downloading %s %s %s (%s)...",
                r["filing_date"],
                r["form"],
                r["accession"],
                ticker,
            )

            paths = edgar_client.download_filing(cik, r, Path(config.DATA_DIR))
            if not paths:
                continue

            # mark immediately so retries don't re-download
            await state.mark_processed(cik, ticker, r["accession"], filing_date)

            # fire-and-forget OpenAI ingestion
            from EDGAR_bot.core import ingest_openai
            asyncio.create_task(ingest_openai.ingest(ticker, paths))


@sync_to_async
def get_watchlist_tickers_sync() -> List[str]:
    """
    Retrieve active tickers from the Watchlist model (synchronous version).

    Returns:
        List of ticker symbols from the watchlist, or empty list if none.
    """
    try:
        # Query active watchlist tickers
        watchlist_tickers = list(
            Watchlist.objects
            .filter(is_active=True)
            .values_list('ticker', flat=True)
        )

        if watchlist_tickers:
            LOGGER.info("Found %d active tickers in Watchlist", len(watchlist_tickers))
        else:
            LOGGER.info("No active tickers found in Watchlist")

        return [t.upper() for t in watchlist_tickers]

    except Exception as e:
        LOGGER.error("Error retrieving Watchlist tickers: %s", e)
        return []


async def get_watchlist_tickers() -> List[str]:
    """
    Retrieve active tickers from the Watchlist model (async wrapper).

    Returns:
        List of ticker symbols from the watchlist, or empty list if none.
    """
    return await get_watchlist_tickers_sync()


async def load_target_tickers_with_watchlist(is_earnings_period: bool) -> List[str]:
    """
    Load target tickers based on the current period.

    During earnings period:
    - First check Watchlist for active tickers
    - If Watchlist is empty, use full CSV list

    During cooldown period:
    - Always use full CSV list

    Args:
        is_earnings_period: Whether we're currently in an earnings period

    Returns:
        List of ticker symbols to process
    """
    # Always load the full CSV list first
    full_tickers = ticker_map.load_target_tickers(config.TICKER_CSV)

    if not is_earnings_period:
        # Cooldown period: use full CSV list
        LOGGER.info("Cooldown period: using full CSV list (%d tickers)", len(full_tickers))
        return full_tickers

    # Earnings period: check Watchlist first
    watchlist_tickers = await get_watchlist_tickers()

    if watchlist_tickers:
        # Filter to only include tickers that are in both Watchlist and CSV
        # This ensures we have valid tickers with CIK mappings
        valid_watchlist_tickers = [
            t for t in watchlist_tickers
            if t in full_tickers
        ]

        if valid_watchlist_tickers:
            LOGGER.info(
                "Earnings period: using Watchlist tickers (%d of %d are in CSV)",
                len(valid_watchlist_tickers),
                len(watchlist_tickers)
            )

            # Log any watchlist tickers not in CSV
            invalid_tickers = set(watchlist_tickers) - set(valid_watchlist_tickers)
            if invalid_tickers:
                LOGGER.warning(
                    "Watchlist tickers not found in CSV and will be skipped: %s",
                    ", ".join(sorted(invalid_tickers))
                )

            return valid_watchlist_tickers
        else:
            LOGGER.warning(
                "No Watchlist tickers found in CSV, falling back to full list"
            )

    # No valid Watchlist tickers, use full CSV list
    LOGGER.info(
        "Earnings period: using full CSV list (%d tickers) - Watchlist empty or invalid",
        len(full_tickers)
    )
    return full_tickers


async def run_once(is_earnings_period: bool = False) -> None:
    """
    Run one cycle of the EDGAR bot with period-aware ticker selection.

    * Build the SEC ticker-to-CIK map
    * Load tickers based on current period (Watchlist for earnings, full CSV for cooldown)
    * Open the StateDB
    * Drive concurrent processing with a semaphore

    Args:
        is_earnings_period: Whether we're currently in an earnings period
    """
    # Build the SEC map (always needed for CIK lookups)
    sec_map: Dict[str, str] = ticker_map.build_ticker_to_cik_map()

    # Load tickers based on current period (now async)
    tickers: List[str] = await load_target_tickers_with_watchlist(is_earnings_period)

    # Check for missing CIK mappings
    missing = [t for t in tickers if t not in sec_map]
    if missing:
        LOGGER.warning("Ticker(s) not found in SEC map and will be skipped: %s", ", ".join(missing))

    # Build work list of (ticker, cik) tuples
    work = [(t, sec_map[t]) for t in tickers if t in sec_map]

    if not work:
        LOGGER.warning("No valid tickers to process")
        return

    # Log summary of what we're processing
    period_type = "EARNINGS" if is_earnings_period else "COOLDOWN"
    LOGGER.info(
        "Starting %s period run with %d tickers",
        period_type,
        len(work)
    )

    # Open state database
    state = StateDB()
    LOGGER.info("Opened state DB at %s", state.db_label)

    # Process all tickers concurrently with semaphore
    sem = asyncio.Semaphore(config.MAX_CONCURRENT_TICKERS)
    await asyncio.gather(*(_handle_ticker(sem, state, t, cik) for t, cik in work))

    state.close()

    LOGGER.info("Completed %s period run", period_type)


# Synchronous entry point (for backwards compatibility)
def main() -> None:
    """Run once in cooldown mode (default behavior)."""
    asyncio.run(run_once(is_earnings_period=False))


if __name__ == "__main__":
    main()