"""
StateDB – wraps the Django ORM but is SAFE inside asyncio code.
"""
from __future__ import annotations
import datetime, logging, os
from typing import Any

import django
from asgiref.sync import sync_to_async   # ← thread‑pool helper
from django.db import close_old_connections

if not django.apps.apps.ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gamma-intelligence.settings")
    django.setup()

from EDGAR_bot.models import ProcessedFiling, ProcessedFile
from EDGAR_bot.core import config

log = logging.getLogger("state")


class StateDB:
    """
    Async‑capable API:
        await state.seen(...)
        await state.mark_processed(...)
        await state.add_file_id(...)
    """

    def __init__(self, *_a: Any, **_kw: Any) -> None:
        self.db_label = f"Django‑ORM ({config.ENV})"
        log.debug("Opened state DB via %s", self.db_label)

    # ─────────────────────────── helpers ──────────────────────────────
    @staticmethod
    def _run(func, *args, **kwargs):
        """Run blocking ORM code in the thread‑pool."""
        return sync_to_async(func, thread_sensitive=True)(*args, **kwargs)

    # ─────────────────────────── public API ────────────────────────────
    async def seen(self, cik: str, accession: str) -> bool:
        return await self._run(
            lambda: ProcessedFiling.objects.filter(cik=cik, accession=accession).exists()
        )

    async def mark_processed(
        self,
        cik: str,
        ticker: str,
        accession: str,
        filing_date: datetime.date | None,
    ) -> None:
        await self._run(
            ProcessedFiling.objects.get_or_create,
            cik=cik,
            accession=accession,
            defaults={"ticker": ticker, "filing_date": filing_date},
        )

    async def add_file_id(
        self,
        cik: str,
        accession: str,
        filename: str,
        file_id: str,
        vector_group_id: int,
    ) -> None:
        await self._run(
            ProcessedFile.objects.get_or_create,
            cik=cik,
            accession=accession,
            filename=filename,
            vector_group_id=vector_group_id,
            defaults={"file_id": file_id},
        )

    # housekeeping (no‑op in async world, but keeps old callers happy)
    def close(self) -> None:                # noqa: D401
        close_old_connections()
