# chatbot/admin.py
from django.contrib import admin
from .models import KnowledgeBase, ChatSession, ChatMessage, StockTicker, Prompt


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


@admin.register(StockTicker)
class StockTickerAdmin(admin.ModelAdmin):
    list_display = ['main_ticker', 'full_ticker', 'company_name', 'industry', 'vector_id']
    list_filter = ['industry', 'sub_industry']
    search_fields = ['main_ticker', 'full_ticker', 'company_name']
    ordering = ['main_ticker']


@admin.register(Prompt)
class PromptAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'prompt_preview', 'created_at', 'updated_at']
    list_filter = ['created_at', 'updated_at', 'user']
    search_fields = ['name', 'prompt', 'user__username', 'user__email']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['user']
    ordering = ['-updated_at']

    def prompt_preview(self, obj):
        return obj.prompt[:100] + '...' if len(obj.prompt) > 100 else obj.prompt

    prompt_preview.short_description = 'Prompt Preview'

    fieldsets = (
        (None, {
            'fields': ('user', 'name', 'prompt')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )