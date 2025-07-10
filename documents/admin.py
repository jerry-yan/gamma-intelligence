# documents/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = [
        'filename_truncated',
        'report_type',
        'vector_group_display',
        'publication_date',
        'upload_date_formatted',
        'is_vectorized_display',
        'file_hash_truncated',
    ]

    list_filter = [
        'report_type',
        'is_vectorized',
        'upload_date',
        'publication_date',
        'vector_group_id',
    ]

    search_fields = [
        'filename',
        'file_hash_id',
        'openai_file_id',
        'report_type',
    ]

    readonly_fields = [
        'file_hash_id',
        'created_at',
        'updated_at',
        'upload_date',
        'metadata_display',
        'knowledge_base_link',
    ]

    fieldsets = (
        ('File Information', {
            'fields': (
                'filename',
                'file_directory',
                'file_hash_id',
            )
        }),
        ('Document Details', {
            'fields': (
                'report_type',
                'publication_date',
                'upload_date',
            )
        }),
        ('Vector Database', {
            'fields': (
                'vector_group_id',
                'knowledge_base_link',
                'is_vectorized',
                'openai_file_id',
            )
        }),
        ('Metadata', {
            'fields': ('metadata_display',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    # Custom display methods
    def filename_truncated(self, obj):
        if len(obj.filename) > 50:
            return obj.filename[:47] + '...'
        return obj.filename

    filename_truncated.short_description = 'Filename'
    filename_truncated.admin_order_field = 'filename'

    def file_hash_truncated(self, obj):
        if obj.file_hash_id:
            return f"{obj.file_hash_id[:8]}..."
        return '-'

    file_hash_truncated.short_description = 'Hash'

    def vector_group_display(self, obj):
        if obj.vector_group_id:
            kb = obj.knowledge_base
            if kb:
                return format_html(
                    '<span title="{}">{}</span>',
                    kb.display_name,
                    obj.vector_group_id
                )
            return obj.vector_group_id
        return '-'

    vector_group_display.short_description = 'Vector Group'
    vector_group_display.admin_order_field = 'vector_group_id'

    def is_vectorized_display(self, obj):
        if obj.is_vectorized:
            return format_html('<span style="color: green;">✓</span>')
        return format_html('<span style="color: red;">✗</span>')

    is_vectorized_display.short_description = 'Vectorized'
    is_vectorized_display.admin_order_field = 'is_vectorized'

    def upload_date_formatted(self, obj):
        return obj.upload_date.strftime('%Y-%m-%d %H:%M')

    upload_date_formatted.short_description = 'Uploaded'
    upload_date_formatted.admin_order_field = 'upload_date'

    def metadata_display(self, obj):
        if obj.metadata:
            import json
            return format_html(
                '<pre style="margin: 0;">{}</pre>',
                json.dumps(obj.metadata, indent=2)
            )
        return '-'

    metadata_display.short_description = 'Metadata JSON'

    def knowledge_base_link(self, obj):
        kb = obj.knowledge_base
        if kb:
            from django.urls import reverse
            from django.utils.html import format_html
            url = reverse('admin:agents_knowledgebase_change', args=[kb.pk])
            return format_html(
                '<a href="{}">{}</a>',
                url,
                kb.display_name
            )
        return '-'

    knowledge_base_link.short_description = 'Knowledge Base'

    # Actions
    actions = ['mark_as_vectorized', 'mark_as_not_vectorized', 'clear_vector_group']

    def mark_as_vectorized(self, request, queryset):
        updated = queryset.update(is_vectorized=True, updated_at=timezone.now())
        self.message_user(request, f'{updated} documents marked as vectorized.')

    mark_as_vectorized.short_description = "Mark selected as vectorized"

    def mark_as_not_vectorized(self, request, queryset):
        updated = queryset.update(is_vectorized=False, updated_at=timezone.now())
        self.message_user(request, f'{updated} documents marked as not vectorized.')

    mark_as_not_vectorized.short_description = "Mark selected as not vectorized"

    def clear_vector_group(self, request, queryset):
        updated = queryset.update(
            vector_group_id=None,
            is_vectorized=False,
            updated_at=timezone.now()
        )
        self.message_user(request, f'{updated} documents had vector group cleared.')

    clear_vector_group.short_description = "Clear vector group assignment"

    # Optimize queries
    def get_queryset(self, request):
        return super().get_queryset(request).select_related()