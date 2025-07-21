"""
Orchestrator – run one cycle and exit.  Safe to call from cron/Task Scheduler.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from EDGAR_bot.core import config, edgar_client, ticker_map
from EDGAR_bot.core.state import StateDB
from EDGAR_bot.core.utils import _as_date

LOGGER = logging.getLogger("jobs")

async def _handle_ticker(
    sem: asyncio.Semaphore,
    state: "StateDB",
    ticker: str,
    cik: str,
) -> None:
    """Process one ticker (list → download → ingest)."""

    async with sem:                             # global concurrency cap
        # ── 1. recent SEC rows ──────────────────────────────────────────
        try:
            api_rows = edgar_client.list_recent_filings(cik)
        except Exception as exc:
            LOGGER.error(
                "Failed to fetch submissions for %s (%s): %s", ticker, cik, exc
            )
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
            rows.append(r)

        LOGGER.info("Found %d new filings for %s (%s)", len(rows), ticker, cik)

        # ── 3. download + ingest each remaining filing ─────────────────
        for r in rows:
            filing_date = _as_date(r["filing_date"])

            # double‑check inside the loop (race‑safe)
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

            # mark immediately so retries don’t redownload
            await state.mark_processed(cik, ticker, r["accession"], filing_date)

            # fire‑and‑forget OpenAI ingestion
            from EDGAR_bot.core import ingest_openai

            asyncio.create_task(ingest_openai.ingest(ticker, paths))


async def run_once():
    # 1. Build ticker→CIK map + master tickers
    sec_map = ticker_map.build_ticker_to_cik_map()
    tickers = ticker_map.load_target_tickers(config.TICKER_CSV)

    missing = [t for t in tickers if t not in sec_map]
    if missing:
        LOGGER.warning("Ticker(s) not found and will be skipped: %s", ", ".join(missing))

    work = [(t, sec_map[t]) for t in tickers if t in sec_map]

    # 2. Open / create state DB
    # db_arg = None if config.ENV == "heroku" else Path(config.DB_PATH)
    # state  = StateDB(db_arg)
    state = StateDB()
    LOGGER.info("Opened state DB at %s", state.db_label)

    # 3. Process with limited concurrency
    sem = asyncio.Semaphore(config.MAX_CONCURRENT_TICKERS)
    await asyncio.gather(*(_handle_ticker(sem, state, t, cik) for t, cik in work))
    state.close()


def main():
    asyncio.run(run_once())


if __name__ == "__main__":
    main()
