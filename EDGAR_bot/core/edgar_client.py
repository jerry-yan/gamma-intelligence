"""
Thin wrapper around SEC JSON endpoints + file download with
retry/back‑off and START_DATE filtering.
"""
from __future__ import annotations

import logging, time, httpx, re, os, boto3
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import requests
from requests.adapters import HTTPAdapter, Retry

from . import config

LOGGER = logging.getLogger("edgar_client")

_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_ARCHIVES = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{doc}"
_ARCH = "https://www.sec.gov/Archives/edgar/data"

EARNINGS_PAT = re.compile(config.EARNINGS_EXHIBIT_RE, re.I)
EX_RE = re.compile(r"(?i)ex(?:hibit)?\s*[-_\.]?\s*\d")

def _list_directory(cik: str, accession: str) -> List[Dict]:
    """
    Return the JSON directory listing for one filing.

    Raises if SEC returns non‑200.
    """
    cik_num         = int(cik.lstrip("0"))            #  0000200406 → 200406
    accession_nodash = accession.replace("-", "")     #  0000200406-25-000170 → 000020040625000170
    url             = f"{_ARCH}/{cik_num}/{accession_nodash}/index.json"

    time.sleep(config.SLEEP_BETWEEN_CALLS)
    r = httpx.get(url, headers=config.HEADERS, timeout=config.REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.json()["directory"]["item"]              # list[dict]

def _build_session() -> requests.Session:
    sess = requests.Session()
    retry = Retry(
        total=config.REQUEST_RETRY_TOTAL,
        backoff_factor=config.REQUEST_RETRY_BACKOFF,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )
    sess.headers.update(config.HEADERS)
    sess.mount("https://", HTTPAdapter(max_retries=retry))
    return sess


_session = _build_session()


def _safe_get(url: str) -> requests.Response:
    """Global rate‑limit + retry handled by session adapter."""
    time.sleep(config.SLEEP_BETWEEN_CALLS)
    r = _session.get(url, timeout=config.REQUEST_TIMEOUT)
    r.raise_for_status()
    return r


# ── Public API ────────────────────────────────────────────────────────────
def list_recent_filings(cik: str) -> List[Dict]:
    url = _SUBMISSIONS_URL.format(cik=cik)
    data = _safe_get(url).json()
    recent = data["filings"]["recent"]

    rows = [
        {
            "accession": acc,
            "form": form,
            "filing_date": datetime.strptime(fdate, "%Y-%m-%d").date(),
            "primary_doc": doc,
        }
        for acc, form, fdate, doc in zip(
            recent["accessionNumber"],
            recent["form"],
            recent["filingDate"],
            recent["primaryDocument"],
        )
    ]

    return [r for r in rows if r["filing_date"] >= config.START_DATE]


def _has_earnings_exhibit(dir_items: List[Dict]) -> bool:
    """
    Return True when the directory listing contains at least one EX‑99 exhibit
    (file name, description, or type).
    """
    for item in dir_items:
        name = item["name"]
        desc = item.get("description", "")
        typ  = item.get("type", "")
        hit = EARNINGS_PAT.search(name) or EARNINGS_PAT.search(desc) or EARNINGS_PAT.search(typ)

        # ▶ DEBUG – comment out once verified
        LOGGER.debug("earnings‑scan | %s | %s | %s | hit=%s",
                     name, desc or "‑", typ or "‑", hit)

        if hit:
            return True
    return False


def download_filing(cik: str, row: Dict, dest_root: Path) -> list[Path] | None:
    """
    Download the primary document plus qualifying exhibits for a filing.

    • 10‑K / 10‑Q (and amendments) are always kept.
    • 8‑K is kept **only** when an earnings‑release exhibit (Ex‑99.*) exists.
    • In Heroku mode (`EDGAR_ENV=heroku`) every saved file is also
      uploaded to an S3 bucket specified via $S3_BUCKET.
    """
    # ── 0. init paths & (optional) S3 client ─────────────────────────────
    cik_stripped   = cik.lstrip("0")
    acc_no_dashes  = row["accession"].replace("-", "")
    dest_dir       = dest_root / cik_stripped / acc_no_dashes
    dest_dir.mkdir(parents=True, exist_ok=True)

    exhibits: list[Path] = []

    # ▶ CHANGE: create S3 client only in Heroku env
    if config.ENV == "heroku":
        s3        = boto3.client("s3")
        s3_bucket = os.environ["S3_BUCKET"]

    # ── 1. grab directory JSON first (lets us pre‑filter 8‑K) ───────────
    try:
        dir_items = _list_directory(cik, row["accession"])
    except Exception as exc:
        LOGGER.error("Could not read filing directory %s: %s", row["accession"], exc)
        return None

    if row["form"].startswith("8-K") and not _has_earnings_exhibit(dir_items):
        LOGGER.info("Skip 8‑K (no earnings exhibit) %s", row["accession"])
        return None

    # ── 2. download primary document ────────────────────────────────────
    primary_url = _ARCHIVES.format(
        cik=cik_stripped,
        accession=acc_no_dashes,
        doc=row["primary_doc"],
    )

    try:
        resp = _safe_get(primary_url)
    except requests.HTTPError as ex:
        LOGGER.error("Primary download failed for %s: %s", row["accession"], ex)
        return None

    out_path = dest_dir / row["primary_doc"]
    out_path.write_bytes(resp.content)
    LOGGER.debug("Saved primary %s", out_path)

    # ▶ CHANGE: S3 upload for primary (Heroku only)
    if config.ENV == "heroku":
        s3_key = f"{cik_stripped}/{acc_no_dashes}/{row['primary_doc']}"
        s3.upload_file(str(out_path), f"{s3_bucket}/edgar-bot", s3_key)
        LOGGER.info("Uploaded primary to s3://%s/%s", s3_bucket, s3_key)

    # ── 3. iterate exhibits – heavy filters applied ─────────────────────
    for item in dir_items:
        name = item["name"]

        # keep only human‑readable formats
        if not name.lower().endswith((".htm", ".html", ".txt", ".pdf")):
            continue

        t    = item["type"].upper()
        desc = item.get("description", "").upper()

        # coarse EX filter
        if not (t.startswith("EX") or desc.startswith("EX") or EX_RE.search(name)):
            continue

        # parent is 8‑K: keep only earnings exhibits
        if row["form"].startswith("8-K") and not (
            EARNINGS_PAT.search(name) or EARNINGS_PAT.search(desc) or EARNINGS_PAT.search(t)):
            continue

        ex_path = dest_dir / name
        exhibits.append(ex_path)

        if ex_path.exists():
            LOGGER.debug("Skip existing exhibit %s", ex_path)
            continue

        ex_url = f"{_ARCH}/{cik_stripped}/{acc_no_dashes}/{name}"
        try:
            ex_resp = _safe_get(ex_url)
            ex_path.write_bytes(ex_resp.content)
            LOGGER.info("Saved exhibit %s", ex_path)

            # ▶ CHANGE: S3 upload for exhibit
            if config.ENV == "heroku":
                ex_key = f"{cik_stripped}/{acc_no_dashes}/{name}"
                s3.upload_file(str(ex_path), s3_bucket, ex_key)
                LOGGER.info("Uploaded exhibit to s3://%s/%s", s3_bucket, ex_key)

        except Exception as exc:
            LOGGER.warning("Failed exhibit %s: %s", name, exc)

        time.sleep(0.12)           # stay polite (max ~8 req/s)

    return [out_path] + exhibits