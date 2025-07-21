from __future__ import annotations
import datetime
import shutil, pathlib, logging
from bs4 import BeautifulSoup


def _as_date(value) -> datetime.date:
    """Return a datetime.date no matter whether value is str or date."""
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str):
        return datetime.date.fromisoformat(value)
    raise TypeError(f"Un‑supported date value: {value!r}")


LOGGER = logging.getLogger("file_utils")

ALLOWED_EXT = {
    ".c", ".cpp", ".css", ".csv", ".doc", ".docx", ".gif", ".go", ".html",
    ".java", ".jpeg", ".jpg", ".js", ".json", ".md", ".pdf", ".php", ".pkl",
    ".png", ".pptx", ".py", ".rb", ".tar", ".tex", ".ts", ".txt", ".webp",
    ".xlsx", ".xml", ".zip",
}


def normalise_for_openai(path: pathlib.Path) -> pathlib.Path:
    """
    Return a *new* Path that is safe to upload. The original file is left intact.

    Rules
    -----
    * *.htm*  → copy to *.html*
    * Allowed ext → unchanged
    * Otherwise   → extract visible text to *.txt*
    """
    ext = path.suffix.lower()

    # 1) straight‑through
    if ext in ALLOWED_EXT:
        return path

    # 2) .htm  →  .html  (cheap copy)
    if ext in {".htm", ".shtml"}:
        new_path = path.with_suffix(".html")
        shutil.copyfile(path, new_path)
        LOGGER.debug("Renamed %s → %s", path.name, new_path.name)
        return new_path

    # 3) fallback: strip HTML tags, write .txt
    try:
        text = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "lxml").get_text(" ", strip=True)
    except Exception:
        text = path.read_text(encoding="utf-8", errors="ignore")
    new_path = path.with_suffix(".txt")
    new_path.write_text(text, encoding="utf-8")
    LOGGER.debug("Converted %s → %s (plain text fallback)", path.name, new_path.name)
    return new_path