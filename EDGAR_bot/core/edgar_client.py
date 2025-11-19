"""
EDGAR helper – list + download SEC filings
Re‑written 2025‑07‑22
"""

from __future__ import annotations

import logging, os, re, time, boto3, requests
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from requests.adapters import HTTPAdapter, Retry

from EDGAR_bot.core import config
from EDGAR_bot.core.state import StateDB
from EDGAR_bot.core.utils import _as_date

log = logging.getLogger("edgar_client")

# ───────────────────────── constants ─────────────────────────
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_ARCHIVES        = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{doc}"
_ARCH            = "https://www.sec.gov/Archives/edgar/data"

EARNINGS_PAT = re.compile(
    r"(?i)("
    r"ex(?:hibit)?\s*[-_\.]?\s*99"           # EX‑99, Exhibit‑99, etc.
    r"|(?<!\d)99(?!\d)"                      # stand‑alone “99”
    r"|press\s*release"
    r"|news\s*release"
    r"|earnings"
    r"|financial"
    r"|investor"
    r"|presentation"
    r"|transcript"
    r"|q[1-4]\s*fy\d{2}"
    r"|fy\d{2}\s*q[1-4]"
    r")",
    re.I,
)

EX_RE = re.compile(r"(?i)ex(?:hibit)?\s*[-_\.]?\s*\d")

ALLOWED_EXT = {".htm", ".html", ".txt", ".pdf"}

# ─────────────────────── HTTP plumbing ───────────────────────
def _build_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=config.REQUEST_RETRY_TOTAL,
        backoff_factor=config.REQUEST_RETRY_BACKOFF,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )
    s.headers.update(config.HEADERS)
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


_session = _build_session()


def _safe_get(url: str) -> requests.Response:
    time.sleep(config.SLEEP_BETWEEN_CALLS)          # global politeness delay
    r = _session.get(url, timeout=config.REQUEST_TIMEOUT)
    r.raise_for_status()
    return r


# ───────────────────────── utilities ─────────────────────────
def _list_directory(cik: str, accession: str) -> List[Dict]:
    cik_num          = int(cik.lstrip("0"))
    accession_nodash = accession.replace("-", "")
    url              = f"{_ARCH}/{cik_num}/{accession_nodash}/index.json"
    return _safe_get(url).json()["directory"]["item"]


def _looks_like_earnings(text: str) -> bool:
    log.info("Checking this blob: %s", text)
    return bool(EARNINGS_PAT.search(text))


def _dir_has_earnings(dir_items: List[Dict]) -> bool:
    for it in dir_items:
        log.info("These are the fields: %s", it)
        blob = f"{it['name']} {it.get('description','')} {it.get('type','')}"
        if _looks_like_earnings(blob):
            return True
    return False


# ────────────────────────── public API ───────────────────────
def list_recent_filings(cik: str) -> List[Dict]:
    data  = _safe_get(_SUBMISSIONS_URL.format(cik=cik)).json()
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


# ------------------------------------------------------------------
def download_filing(cik: str, row: Dict, dest_root: Path) -> list[Path] | None:
    """
    Download the primary document and qualifying exhibits.
    Returns a list[Path] of saved files or None if skipped/failed.
    """
    cik_str   = cik.lstrip("0")
    acc_clean = row["accession"].replace("-", "")
    dest_dir  = dest_root / cik_str / acc_clean
    dest_dir.mkdir(parents=True, exist_ok=True)

    if config.ENV == "heroku":
        s3        = boto3.client("s3")
        s3_bucket = os.environ["S3_BUCKET"]

    # 1. directory JSON --------------------------------------------------
    try:
        dir_items = _list_directory(cik, row["accession"])
    except Exception as exc:
        log.error("Dir‑listing failed for %s: %s", row["accession"], exc)
        return None

    # 8‑K gate – skip if nothing smells like earnings
    if row["form"].startswith("8-K") and not _dir_has_earnings(dir_items):
        log.info("Skip 8‑K (no earnings exhibit) %s", row["accession"])

        # --- Mark it as processed, regardless of the execution context ----
        async def _mark():
            await StateDB().mark_processed(
                cik,
                row.get("ticker", ""),
                row["accession"],
                _as_date(row["filing_date"]),
            )

        try:
            import asyncio
            loop = asyncio.get_running_loop()  # ← we’re inside an async task
            loop.create_task(_mark())  # fire‑and‑forget, non‑blocking
        except RuntimeError:
            # no running loop (download_filing called from sync code) ─ use sync bridge
            from asgiref.sync import async_to_sync
            async_to_sync(_mark)()  # runs the coroutine in a thread

        return None

    # 2. primary ---------------------------------------------------------
    primary_url = _ARCHIVES.format(cik=cik_str, accession=acc_clean, doc=row["primary_doc"])
    try:
        out_path = dest_dir / row["primary_doc"]
        out_path.write_bytes(_safe_get(primary_url).content)
    except Exception as exc:
        log.error("Primary download failed for %s: %s", row["accession"], exc)
        return None

    if config.ENV == "heroku":
        s3.upload_file(str(out_path), s3_bucket, f"edgar-bot/{cik_str}/{acc_clean}/{out_path.name}")

    saved: list[Path] = [out_path]

    # 3. exhibits --------------------------------------------------------
    for item in dir_items:
        name = item["name"]
        ext  = Path(name).suffix.lower()

        # 3‑A) format guard
        if ext and ext not in ALLOWED_EXT:
            continue

        t    = item.get("type", "")
        desc = item.get("description", "")
        blob = f"{name} {t} {desc}"

        # 3‑B) should we keep it?
        if row["form"].startswith("8-K"):
            if not _looks_like_earnings(blob):
                continue
        else:
            if not (t.upper().startswith("EX") or desc.upper().startswith("EX") or EX_RE.search(name)):
                continue

        # 3‑C) download
        ex_path = dest_dir / name
        if ex_path.exists():
            continue  # already present (resume run)

        try:
            ex_url = f"{_ARCH}/{cik_str}/{acc_clean}/{name}"
            ex_resp = _safe_get(ex_url)
            ex_path.write_bytes(ex_resp.content)
            saved.append(ex_path)
            log.info("Saved exhibit %s", ex_path)

            if config.ENV == "heroku":
                ex_key = f"edgar-bot/{cik_str}/{acc_clean}/{name}"
                s3.upload_file(str(ex_path), s3_bucket, ex_key)
                log.info("Uploaded exhibit to s3://%s/%s", s3_bucket, ex_key)

        except Exception as exc:
            log.warning("Failed exhibit %s: %s", name, exc)

    return saved if saved else None
