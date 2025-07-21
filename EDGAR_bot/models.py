from django.db import models


class ProcessedFiling(models.Model):
    """
    One row per SEC submission we have fully processed.
    """
    id          = models.BigAutoField(primary_key=True)
    cik         = models.CharField(max_length=10)
    ticker      = models.CharField(max_length=12)
    accession   = models.CharField(max_length=20)
    filing_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table        = "processed"
        ordering        = ["-filing_date"]
        unique_together = [("cik", "accession")]
        indexes = [
            models.Index(fields=["cik", "accession"]),
            models.Index(fields=["ticker"]),
        ]

    def __str__(self) -> str:
        return f"{self.ticker} {self.accession}"


class ProcessedFile(models.Model):
    """
    One row per *individual file* uploaded to OpenAI and attached
    to at least one vector‑store.
    """
    id        = models.BigAutoField(primary_key=True)
    cik       = models.CharField(max_length=10)
    accession = models.CharField(max_length=20)
    filename  = models.CharField(max_length=260)
    file_id   = models.CharField(max_length=100)
    vector_group_id = models.PositiveIntegerField()

    class Meta:
        db_table        = "processed_files"
        unique_together = [("cik", "accession", "filename", "vector_group_id")]
        indexes = [
            models.Index(fields=["cik", "accession"]),
            models.Index(fields=["file_id"]),
        ]

    def __str__(self) -> str:
        return self.filename
