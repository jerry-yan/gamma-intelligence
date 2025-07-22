"""
Orchestrator – run one cycle and exit.  Safe to call from cron/Task Scheduler.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Dict, List

from EDGAR_bot.core import config, edgar_client, ticker_map
from EDGAR_bot.core.state import StateDB
from EDGAR_bot.core.utils import _as_date

LOGGER = logging.getLogger("jobs")


# ────────────────────────────────────────────────────────────────────────────
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
    async with sem:                                 # global concurrency cap
        # ── 1. recent SEC rows ──────────────────────────────────────────
        try:
            api_rows: List[Dict] = edgar_client.list_recent_filings(cik)
        except Exception as exc:                    # network / SEC error
            LOGGER.error("Submissions fetch failed for %s (%s): %s", ticker, cik, exc)
            return

        # ── 2. skip already‑seen or disallowed rows ────────────────────
        rows: list[dict] = []
        for r in api_rows:
            if r["form"] not in config.ALLOWED_FORMS:
                continue
            if _as_date(r["filing_date"]) < config.START_DATE:
                continue
            if await state.seen(cik, r["accession"]):
                continue

            r["ticker"] = ticker          # ←★ ALWAYS attach the ticker ★
            rows.append(r)

        LOGGER.info("Found %d new filings for %s (%s)", len(rows), ticker, cik)

        # ── 3. download + ingest each remaining filing ─────────────────
        for r in rows:
            filing_date = _as_date(r["filing_date"])

            # race‑safe double‑check
            if filing_date < config.START_DATE or await state.seen(cik, r["accession"]):
                continue

            LOGGER.info(
                "Downloading %s %s %s (%s)…",
                r["filing_date"],
                r["form"],
                r["accession"],
                ticker,
            )

            paths = edgar_client.download_filing(cik, r, Path(config.DATA_DIR))
            if not paths:
                continue

            # mark immediately so retries don’t re‑download
            await state.mark_processed(cik, ticker, r["accession"], filing_date)

            # fire‑and‑forget OpenAI ingestion
            from EDGAR_bot.core import ingest_openai
            asyncio.create_task(ingest_openai.ingest(ticker, paths))


# ────────────────────────────────────────────────────────────────────────────
async def run_once() -> None:
    """
    * Build the SEC ticker‑to‑CIK map
    * Open the StateDB
    * Drive concurrent processing with a semaphore
    """
    sec_map: Dict[str, str] = ticker_map.build_ticker_to_cik_map()
    tickers: List[str]      = ticker_map.load_target_tickers(config.TICKER_CSV)

    missing = [t for t in tickers if t not in sec_map]
    if missing:
        LOGGER.warning("Ticker(s) not found and will be skipped: %s", ", ".join(missing))

    work = [(t, sec_map[t]) for t in tickers if t in sec_map]

    state = StateDB()
    LOGGER.info("Opened state DB at %s", state.db_label)

    sem = asyncio.Semaphore(config.MAX_CONCURRENT_TICKERS)
    await asyncio.gather(*(_handle_ticker(sem, state, t, cik) for t, cik in work))

    state.close()


# synchronous entry‑point ----------------------------------------------------
def main() -> None:
    asyncio.run(run_once())


if __name__ == "__main__":
    main()
