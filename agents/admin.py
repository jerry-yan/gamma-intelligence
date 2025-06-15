# chatbot/admin.py
from django.contrib import admin
from .models import KnowledgeBase, ChatSession, ChatMessage


@admin.register(KnowledgeBase)
class KnowledgeBaseAdmin(admin.ModelAdmin):
    list_display = ['display_name', 'name', 'vector_group_id', 'vector_store_id', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['display_name', 'name', 'vector_store_id', 'vector_group_id', 'description']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ['session_id', 'user', 'title', 'created_at', 'last_activity']
    list_filter = ['created_at', 'last_activity']
    search_fields = ['session_id', 'user__username', 'user__email', 'title']
    readonly_fields = ['session_id', 'created_at']
    raw_id_fields = ['user']


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ['session', 'role', 'knowledge_base', 'content_preview', 'created_at']
    list_filter = ['role', 'knowledge_base', 'created_at']
    search_fields = ['content', 'session__session_id']
    readonly_fields = ['created_at']
    raw_id_fields = ['session', 'knowledge_base']

    def content_preview(self, obj):
        return obj.content[:100] + '...' if len(obj.content) > 100 else obj.content

    content_preview.short_description = 'Content'