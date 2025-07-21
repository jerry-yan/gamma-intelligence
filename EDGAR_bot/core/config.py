"""
Central runtime configuration – every other module imports from here.
Edit here, restart the job, and all settings propagate.
"""
import datetime, logging, os
from pathlib import Path
from importlib import resources

START_DATE = datetime.date(2024, 7, 1)   # ignore anything earlier

# ── Identification (SEC requires a contact string) ───────────────────────
USER_AGENT = "1832AM-EDGARbot/0.1 (derek.bastien@scotiagam.com)"

# ── Identification (SEC requires a contact string) ───────────────────────
ENV = os.getenv("EDGAR_ENV", "local")          # 'local' | 'heroku'

HEADERS = {
    # Browser‑like stub (keeps corporate proxies happy) + required contact
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36 "
        f"{USER_AGENT}"
    ),
    "Accept-Encoding": "gzip, deflate",
    "Accept": "application/json, text/plain, */*",
}

# ── Network / polite‑crawl settings ───────────────────────────────────────
REQUEST_TIMEOUT = 30           # seconds
REQUEST_RETRY_TOTAL = 5        # total attempts per request
REQUEST_RETRY_BACKOFF = 1.0    # exponential‑backoff factor (1 → 1 s, 2 s, 4 s…)
SLEEP_BETWEEN_CALLS = 0.15     # seconds; ~6–7 req/s aggregate across tasks
MAX_CONCURRENT_TICKERS = 4     # async semaphore
SCHEDULE_MINUTES       = 10          # run every 10 minutes

# ──────────────────────────── path handling ──────────────────────────────
# This file lives at …/EDGAR_bot/core/config.py
BASE_DIR = Path(__file__).resolve().parent          # …/EDGAR_bot/core
APP_DIR  = BASE_DIR.parent                          # …/EDGAR_bot

if ENV == "heroku":
    # Heroku dyno filesystem is ephemeral
    ROOT_DIR  = Path("/app")                        # slug root
    LOG_DIR   = ROOT_DIR / "tmp"                    # ignored by Logplex
    CACHE_DIR = ROOT_DIR / "tmp/.cache"
    DATA_DIR  = ROOT_DIR / "tmp/filings"            # tmp before S3 upload
    DB_URL    = os.environ["DATABASE_URL"]          # provided by Heroku

else:
    ROOT_DIR  = APP_DIR                             # keep data inside package tree
    LOG_DIR   = ROOT_DIR / "logs"
    CACHE_DIR = ROOT_DIR / ".cache"
    DATA_DIR  = ROOT_DIR / "filings"
    DB_PATH   = ROOT_DIR / "state.db"               # SQLite file

    # ensure folders exist
    for _p in (LOG_DIR, CACHE_DIR, DATA_DIR):
        _p.mkdir(exist_ok=True)

# ─── Files used by the pipeline ──────────────────────────────────────────
TICKER_CSV = resources.files("EDGAR_bot.data") / "companies.csv"

# ───────────────────────────── logging ───────────────────────────────────
handlers: list[logging.Handler] = [logging.StreamHandler()]
if ENV == "local":
    LOG_FILE = LOG_DIR / "edgar_bot.log"
    handlers.append(logging.FileHandler(LOG_FILE, encoding="utf‑8"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=handlers,
)

# ────────────────────── filing‑type / exhibit filters ────────────────────
ALLOWED_FORMS = {
    "10-K", "10-K/A",
    "10-Q", "10-Q/A",
    "8-K",  "8-K/A",
}

# regex used in edgar_client to detect earnings press‑release exhibits
EARNINGS_EXHIBIT_RE = r"(?i)(ex|exhibit)[-_\.]?99|earnings.?release|press.?release"