# documents/models.py
from django.db import models
from django.utils import timezone


class Document(models.Model):
    """
    General-purpose document storage model for user-uploaded files.
    Documents are stored in S3 and can be associated with knowledge bases.
    """

    # File identification
    file_directory = models.CharField(
        max_length=255,
        help_text="S3 directory path (e.g., 'ResearchNotes', 'UserDocuments')"
    )
    file_hash_id = models.CharField(
        max_length=64,
        unique=True,
        help_text="SHA-256 hash of file content for deduplication"
    )
    openai_file_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="OpenAI file ID after upload"
    )

    # Knowledge base association
    vector_group_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Links to KnowledgeBase.vector_group_id"
    )

    # Document metadata
    filename = models.CharField(
        max_length=500,
        help_text="Original filename"
    )

    # Dates
    upload_date = models.DateTimeField(
        default=timezone.now,
        help_text="When the file was uploaded"
    )
    publication_date = models.DateField(
        null=True,
        blank=True,
        help_text="Document publication date (if applicable)"
    )

    # Processing flags
    is_vectorized = models.BooleanField(
        default=False,
        help_text="Whether this document has been added to a vector store"
    )

    # Document classification - free text field
    report_type = models.CharField(
        max_length=100,
        default='general',
        help_text="Type of document (free text)"
    )

    # Additional metadata
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional metadata (extracted text, page count, etc.)"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-upload_date', '-created_at']
        indexes = [
            models.Index(fields=['file_hash_id']),
            models.Index(fields=['vector_group_id']),
            models.Index(fields=['is_vectorized']),
            models.Index(fields=['report_type']),
            models.Index(fields=['-upload_date']),
        ]
        verbose_name = 'Document'
        verbose_name_plural = 'Documents'

    def __str__(self):
        return f"{self.filename} ({self.report_type})"

    @property
    def knowledge_base(self):
        """Get associated KnowledgeBase if vector_group_id is set"""
        if self.vector_group_id:
            from agents.models import KnowledgeBase
            try:
                return KnowledgeBase.objects.get(vector_group_id=self.vector_group_id)
            except KnowledgeBase.DoesNotExist:
                return None
        return None

    def mark_as_vectorized(self):
        """Mark document as successfully vectorized"""
        self.is_vectorized = True
        self.save(update_fields=['is_vectorized', 'updated_at'])