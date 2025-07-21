"""
Ticker → CIK lookup (download once, cached to .cache/sec_ticker_map.json).
"""
from __future__ import annotations

import csv
import json
import logging
import re
from pathlib import Path
from typing import Dict
from importlib import resources

import requests

from EDGAR_bot.core import config

LOGGER = logging.getLogger("ticker_map")

SEC_TICKER_URL = "https://www.sec.gov/include/ticker.txt"
SEC_JSON_URL   = "https://www.sec.gov/files/company_tickers.json"

CACHE_PATH = Path(config.CACHE_DIR) / "sec_ticker_map.json"
CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────────────────────────────────
def _parse_line(line: str) -> tuple[str, str] | None:
    """Return (TICKER, 10‑char‑CIK) or None if malformed."""
    line = line.strip()
    if not line:
        return None

    if "|" in line:
        parts = line.split("|", 1)
    else:                                   # behind some proxies '|' → whitespace
        m = re.match(r"([A-Za-z0-9.\-]+)\s+(\d+)", line)
        if not m:
            return None
        parts = m.groups()

    ticker, cik = parts
    return ticker.upper(), cik.zfill(10)


def _download_sec_ticker_file() -> Dict[str, str]:
    """Primary txt → fallback JSON, with verbose logging."""
    def _fetch(u: str) -> str:
        r = requests.get(u, headers=config.HEADERS, timeout=config.REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.text

    txt = _fetch(SEC_TICKER_URL)
    mapping = {t: c for ln in txt.splitlines() if (pc := _parse_line(ln))
               for t, c in [pc]}

    if len(mapping) >= 20_000:               # sanity
        LOGGER.info("Downloaded SEC mapping from ticker.txt (%d rows)", len(mapping))
        return mapping

    LOGGER.warning("ticker.txt parsed to %d rows – falling back to JSON", len(mapping))
    data = json.loads(_fetch(SEC_JSON_URL))
    mapping = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in data.values()}
    LOGGER.info("Downloaded SEC mapping from company_tickers.json (%d rows)", len(mapping))
    return mapping


def build_ticker_to_cik_map() -> Dict[str, str]:
    if CACHE_PATH.exists():
        try:
            with CACHE_PATH.open(encoding="utf-8") as fh:
                cached = json.load(fh)
            LOGGER.info("Loaded SEC ticker map from cache (%d rows)", len(cached))
            return cached
        except Exception:
            LOGGER.exception("Cache corrupted – refreshing")

    mapping = _download_sec_ticker_file()
    with CACHE_PATH.open("w", encoding="utf-8") as fh:
        json.dump(mapping, fh)
    LOGGER.info("Cached SEC ticker map (%d rows)", len(mapping))
    return mapping


def load_target_tickers(csv_path: Path) -> list[str]:
    path = resources.files("EDGAR_bot.data") / "companies.csv"
    LOGGER.info("Loading target tickers from %s", path.name)
    tickers: set[str] = set()
    with csv_path.open() as fh:
        for row in csv.reader(fh):
            if row:
                tickers.add(row[0].strip().upper())
    LOGGER.info("Loaded %d tickers from master list", len(tickers))
    return sorted(tickers)
