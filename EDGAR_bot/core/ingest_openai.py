"""
EDGAR‑bot → OpenAI vector‑store ingestion helper
================================================
Uploads each SEC filing exactly once and attaches it to every vector‑store
linked to the ticker.
"""

from __future__ import annotations
import asyncio, logging, os, pathlib
from typing import Iterable

import openai
from openai import OpenAI
from asgiref.sync import sync_to_async

# ── Django bootstrap (only if not started via manage.py) ────────────────────
import django
if not django.apps.apps.ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "edgar-gamma-bot.settings")
    django.setup()

from agents.models import StockTicker, KnowledgeBase
from EDGAR_bot.core import utils                       # normalise_for_openai
from EDGAR_bot.core.state import StateDB

# ── globals ─────────────────────────────────────────────────────────────────
log       = logging.getLogger("edgar_ingest")
CLIENT    = OpenAI()
STATE = StateDB()
router    = getattr(CLIENT, "vector_stores", None) or getattr(getattr(CLIENT, "beta", None), "vector_stores", None)
if router is None:
    raise RuntimeError(f"OpenAI SDK {openai.__version__} lacks vector‑store API")

# ── helpers ────────────────────────────────────────────────────────────────
async def _vector_store_has_file(store_id: str, identifier: str) -> bool:
    """identifier may be file_id *or* filename"""
    loop = asyncio.get_running_loop()

    def _blocking() -> bool:
        page = router.files.list(vector_store_id=store_id)
        while True:
            for obj in page.data:
                if hasattr(obj, "file_id") and obj.file_id == identifier:
                    return True
                if hasattr(obj, "filename") and obj.filename == identifier:
                    return True
                if hasattr(obj, "file_id"):
                    meta = CLIENT.files.retrieve(obj.file_id)
                    if meta.filename == identifier:
                        return True
            if page.has_next_page():
                page = page.get_next_page()
            else:
                break
        return False

    return await loop.run_in_executor(None, _blocking)


async def _get_or_upload_file(path: pathlib.Path) -> str:
    """Return OpenAI *file_id* for *path*, uploading if necessary."""
    loop = asyncio.get_running_loop()

    def _blocking() -> str:
        # search by filename
        page = CLIENT.files.list(purpose="assistants")
        while True:
            for f in page.data:
                if f.filename == path.name:
                    return f.id
            if page.has_next_page():
                page = page.get_next_page()
            else:
                break
        # upload once
        with path.open("rb") as fh:
            f = CLIENT.files.create(file=fh, purpose="assistants")
            return f.id

    return await loop.run_in_executor(None, _blocking)


async def _attach_file_to_store(store_id: str, file_id: str, filename: str) -> None:
    if await _vector_store_has_file(store_id, file_id) or await _vector_store_has_file(store_id, filename):
        return
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: router.file_batches.create(vector_store_id=store_id, file_ids=[file_id]),
    )


async def _attach_files_for_store(store_id: str, vector_group_id: int, file_map: dict[pathlib.Path, str],) -> None:
    for path, fid in file_map.items():
        try:
            await _attach_file_to_store(store_id, fid, path.name)
            log.info("Attached %s → %s", path.name, store_id)

            # ── NEW: remember in processed_files table ──
            cik, accession, _ = path.parts[-3:]
            await STATE.add_file_id(
                cik, accession, path.name, fid, vector_group_id
            )
        except Exception as exc:
            log.warning("Attach failure %s → %s: %s", path.name, store_id, exc)


# ── public coroutine ───────────────────────────────────────────────────────
async def ingest(ticker: str, saved_paths: list[pathlib.Path]) -> None:
    if not saved_paths:
        return

    # vector_group_ids for this ticker
    vec_ids = set(
        await sync_to_async(
            lambda: list(
                StockTicker.objects.filter(main_ticker__iexact=ticker)
                .values_list("vector_id", flat=True)
            )
        )()
    )
    if not vec_ids:
        log.warning("Ticker %s not found in StockTicker", ticker)
        return

    kb_rows = await sync_to_async(
        lambda: list(
            KnowledgeBase.objects.filter(
                vector_group_id__in = vec_ids, is_active = True
            ).values_list("vector_store_id", "vector_group_id")
        )
    )()
    store_to_group = {sid: gid for sid, gid in kb_rows}
    store_ids = set(store_to_group)

    if not store_ids:
        log.warning("No active KnowledgeBase for %s (groups=%s)", ticker, sorted(vec_ids))
        return

    # Normalise & upload each exhibit exactly once (sequentially)
    file_map: dict[pathlib.Path, str] = {}
    for p in saved_paths:
        norm = utils.normalise_for_openai(p)
        try:
            fid = await _get_or_upload_file(norm)
            file_map[norm] = fid             # Path → file_id
        except Exception as exc:
            log.warning("Upload failure %s: %s", norm.name, exc)

    if not file_map:
        return

    tasks = [
        _attach_files_for_store(sid, store_to_group[sid], file_map)
        for sid in store_ids
    ]
    await asyncio.gather(*tasks, return_exceptions=True)

import atexit
atexit.register(STATE.close)