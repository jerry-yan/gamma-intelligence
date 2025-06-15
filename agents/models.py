# agents/models.py
from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()


class KnowledgeBase(models.Model):
    """Represents a vector store in OpenAI"""
    name = models.CharField(max_length=100, unique=True)
    display_name = models.CharField(max_length=200)
    vector_store_id = models.CharField(max_length=100, unique=True, help_text="OpenAI Vector Store ID")
    vector_group_id = models.PositiveIntegerField(unique=True, help_text="Unique identifier matching ResearchNote vector_group_id")
    description = models.TextField(blank=True)
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
        ]

    def __str__(self):
        return f"{self.display_name} (Group {self.vector_group_id})"


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