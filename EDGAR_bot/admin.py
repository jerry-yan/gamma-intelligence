# EDGAR_bot/admin.py
from django.contrib import admin
from .models import ProcessedFiling, ProcessedFile, Watchlist


@admin.register(ProcessedFiling)
class ProcessedFilingAdmin(admin.ModelAdmin):
    """
    One row per SEC submission we finished processing.
    """
    date_hierarchy = "filing_date"
    list_display   = ("ticker", "cik", "accession", "filing_date")
    list_filter    = ("ticker",)
    search_fields  = ("ticker", "cik", "accession")
    ordering       = ("-filing_date",)


@admin.register(ProcessedFile)
class ProcessedFileAdmin(admin.ModelAdmin):
    """
    One row per file that was uploaded to OpenAI and
    attached to (at least) one vector‑store.
    """
    list_display  = (
        "filename",
        "cik",
        "accession",
        "vector_group_id",
        "file_id_short",
    )
    list_filter   = ("vector_group_id",)
    search_fields = ("filename", "cik", "accession", "file_id")

    ordering      = ("-accession", "filename")

    # helper column: show only first 12 chars of file_id
    @admin.display(description="file_id")
    def file_id_short(self, obj):
        return obj.file_id[:12] + "…"


@admin.register(Watchlist)
class WatchlistAdmin(admin.ModelAdmin):
    list_display = ['ticker', 'earnings_date', 'is_active', 'cik']
    list_filter = ['is_active', 'earnings_date']
    search_fields = ['ticker']
    list_editable = ['is_active']