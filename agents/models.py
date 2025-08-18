# agents/models.py
from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid

User = get_user_model()


class KnowledgeBase(models.Model):
    """Represents a vector store in OpenAI"""

    class Purpose(models.IntegerChoices):
        INDUSTRY = 0, 'Industry'
        USER = 1, 'User'
        # Add more purposes here in the future
        # CUSTOM = 2, 'Custom'
        # RESEARCH = 3, 'Research'

    name = models.CharField(max_length=100, unique=True)
    display_name = models.CharField(max_length=200)
    vector_store_id = models.CharField(max_length=100, unique=True, help_text="OpenAI Vector Store ID")
    vector_group_id = models.PositiveIntegerField(unique=True,
                                                  help_text="Unique identifier matching ResearchNote vector_group_id")
    description = models.TextField(blank=True)
    file_retention = models.PositiveIntegerField(
        default=730,  # 2 years = 730 days
        validators=[
            MinValueValidator(1),  # Minimum 1 day
            MaxValueValidator(109500)  # Maximum 300 years = 109500 days
        ],
        help_text="File retention period in days (default: 2 years = 730 days)"
    )
    purpose = models.IntegerField(
        choices=Purpose.choices,
        default=Purpose.INDUSTRY,
        help_text="Purpose of this knowledge base"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_name']
        verbose_name = 'Knowledge Base'
        verbose_name_plural = 'Knowledge Bases'
        indexes = [
            models.Index(fields=['vector_group_id']),
            models.Index(fields=['is_active', 'vector_group_id']),
            models.Index(fields=['purpose']),  # Index for purpose field
        ]

    def __str__(self):
        return f"{self.display_name} (Group {self.vector_group_id})"

    def get_retention_display(self):
        """Get human-readable retention period"""
        days = self.file_retention
        if days == 1:
            return "1 day"
        elif days < 7:
            return f"{days} days"
        elif days < 30:
            weeks = days // 7
            return f"{weeks} week{'s' if weeks > 1 else ''}"
        elif days < 365:
            months = days // 30
            return f"{months} month{'s' if months > 1 else ''}"
        else:
            years = days // 365
            return f"{years} year{'s' if years > 1 else ''}"


class ChatSession(models.Model):
    """A continuous chat session that can use different knowledge bases"""
    session_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='chat_sessions')
    title = models.CharField(max_length=200, blank=True, help_text="Auto-generated from first message")
    response_id = models.CharField(max_length=100, blank=True,
                                   help_text="OpenAI Response ID for conversation continuity")
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-last_activity']
        indexes = [
            models.Index(fields=['session_id']),
            models.Index(fields=['user', '-last_activity']),
        ]

    def generate_title(self):
        """Generate a title from the first user message"""
        first_message = self.messages.filter(role='user').first()
        if first_message:
            self.title = first_message.content[:50] + ('...' if len(first_message.content) > 50 else '')
            self.save()

    def __str__(self):
        return f"Session {self.session_id.hex[:8]} - {self.title[:30] or 'Untitled'}"


class ChatMessage(models.Model):
    """Individual messages in a chat session"""
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
    ]

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    knowledge_base = models.ForeignKey(
        KnowledgeBase,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Knowledge base used for this message (if any)"
    )
    metadata = models.JSONField(default=dict, blank=True)  # Store tool use, citations, response_id, etc.
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['session', 'created_at']),
            models.Index(fields=['role', 'created_at']),
        ]

    def __str__(self):
        content_preview = self.content[:50] + ('...' if len(self.content) > 50 else '')
        return f"{self.role}: {content_preview}"


class StockTicker(models.Model):
    """Model to store stock ticker information"""
    main_ticker = models.CharField(max_length=10)
    full_ticker = models.CharField(max_length=50)
    company_name = models.CharField(max_length=255)
    industry = models.CharField(max_length=255)
    sub_industry = models.CharField(max_length=255)
    vector_id = models.IntegerField()  # Corresponds to vector_group_id in knowledge base

    class Meta:
        db_table = 'stock_tickers'
        ordering = ['main_ticker']
        unique_together = [['main_ticker', 'vector_id']]
        indexes = [
            models.Index(fields=['main_ticker']),
            models.Index(fields=['vector_id']),
        ]

    def __str__(self):
        return f"{self.main_ticker} - {self.company_name}"


class Prompt(models.Model):
    """Model to store user-created prompts"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='prompts')
    name = models.CharField(max_length=200, help_text="Name for this prompt")
    prompt = models.TextField(help_text="The prompt content")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['user', '-updated_at']),
        ]
        unique_together = [['user', 'name']]  # Each user can only have one prompt with the same name

    def __str__(self):
        return f"{self.name} - {self.user.username}"