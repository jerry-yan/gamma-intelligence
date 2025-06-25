# research_summaries/models.py
from django.db import models


class ResearchNote(models.Model):
    # --- Core fields
    source = models.CharField(max_length=255, null=True, blank=True)  # e.g., "JP Morgan"
    provider = models.CharField(max_length=255, default="AlphaSense")  # default

    file_id = models.CharField(max_length=255, null=True, blank=True, unique=True)  # SRFS-00-xxx
    download_link = models.URLField(max_length=1000, null=True, blank=True)  # long URLs

    file_directory = models.CharField(max_length=1000, null=True, blank=True)  # file path
    file_hash_id = models.CharField(max_length=64, null=True, blank=True)

    raw_companies = models.CharField(max_length=1000, null=True, blank=True)
    raw_company_count = models.PositiveIntegerField(null=True, blank=True)  # 0, 1, 2, etc.
    raw_author = models.CharField(max_length=1000, null=True, blank=True)
    raw_title = models.CharField(max_length=1000, null=True, blank=True)
    raw_page_count = models.PositiveIntegerField(null=True, blank=True)
    parsed_ticker = models.CharField(max_length=20, null=True, blank=True)

    report_type = models.CharField(max_length=255, null=True, blank=True)  # e.g., "Company Update"

    report_summary = models.JSONField(null=True, blank=True)  # JSON object (Postgres-native)

    publication_date = models.DateField(null=True, blank=True, help_text="Date extracted from PDF filename")
    is_advanced_summary = models.BooleanField(default=False, help_text="Whether advanced summarization was used")
    vector_group_id = models.PositiveIntegerField(null=True, blank=True, help_text="Vector database group assignment")
    is_vectorized = models.BooleanField(default=False, help_text="Whether this note has been added to a vector store")

    # --- Timestamps
    file_download_time = models.DateTimeField(null=True, blank=True)
    file_update_time = models.DateTimeField(null=True, blank=True)
    file_summary_time = models.DateTimeField(null=True, blank=True)

    # --- Metrics
    created_at = models.DateTimeField(auto_now_add=True)  # when the DB row was created
    updated_at = models.DateTimeField(auto_now=True)  # whenever the DB row was updated

    # --- Status tracking ---
    STATUS_CHOICES = [
        (0, "Not Downloaded"),
        (1, "Downloaded"),
        (2, "Preprocessed"),
        (3, "Summarized"),
        (4, "Advanced Summarized"),
        (10, "Error 1"),
        (11, "Error 2"),
    ]
    status = models.PositiveIntegerField(choices=STATUS_CHOICES, default=0)

    def __str__(self):
        return f"{self.source or 'Unknown Source'} - {self.report_type or 'Unknown Type'} ({self.get_status_display()})"

    class Meta:
        ordering = ['-file_download_time', '-created_at']
        indexes = [
            models.Index(fields=['parsed_ticker', '-publication_date']),
            models.Index(fields=['vector_group_id']),
            models.Index(fields=['is_vectorized']),
            models.Index(fields=['status', '-file_download_time']),
        ]


class ResearchNoteIndustry(models.Model):
    research_note = models.ForeignKey(ResearchNote, on_delete=models.CASCADE, related_name="industries")
    ticker = models.CharField(max_length=10)  # e.g., "AAPL", "MSFT"
    industry = models.CharField(max_length=255, null=True, blank=True)
    sub_industry = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"{self.ticker} - {self.industry or 'Unknown'}"