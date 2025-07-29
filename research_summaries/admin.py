# research_summaries/admin.py
from django.contrib import admin
from .models import ResearchNote, ResearchNoteIndustry


class ResearchNoteIndustryInline(admin.TabularInline):
    model = ResearchNoteIndustry
    extra = 1


@admin.register(ResearchNote)
class ResearchNoteAdmin(admin.ModelAdmin):
    list_display = [
        'file_id',
        'source',
        'raw_title_truncated',
        'parsed_ticker',
        'publication_date',
        'raw_author',
        'raw_company_count',
        'status',
        'file_hash_id',
        'is_advanced_summary',
        'is_vectorized',
        'is_persistent_document',
        'vector_group_id',
        'created_at'
    ]
    list_filter = [
        'status',
        'source',
        'provider',
        'report_type',
        'is_advanced_summary',
        'is_vectorized',
        'is_persistent_document',
        'vector_group_id',
        'publication_date',
        'created_at',
        'file_download_time',
        'file_summary_time'
    ]
    search_fields = [
        'file_id',
        'raw_title',
        'raw_author',
        'source',
        'raw_companies',
        'parsed_ticker',
        'openai_file_id',
        'file_hash_id'
    ]
    readonly_fields = [
        'created_at',
        'updated_at',
        'file_hash_id'
    ]
    inlines = [ResearchNoteIndustryInline]

    fieldsets = (
        ('Core Information', {
            'fields': ('source', 'provider', 'file_id', 'download_link')
        }),
        ('Content Details', {
            'fields': (
                'raw_title',
                'raw_author',
                'raw_companies',
                'raw_company_count',
                'raw_page_count',
                'parsed_ticker',
                'publication_date'
            )
        }),
        ('Classification', {
            'fields': ('report_type', 'status')
        }),
        ('Processing Flags', {
            'fields': ('is_advanced_summary', 'is_vectorized', 'vector_group_id'),
            'description': 'Advanced processing and vectorization status'
        }),
        ('File Management', {
            'fields': ('file_directory', 'file_hash_id', 'openai_file_id', 'file_download_time', 'file_update_time', 'file_summary_time')
        }),
        ('Summary', {
            'fields': ('report_summary',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def raw_title_truncated(self, obj):
        if obj.raw_title:
            return obj.raw_title[:50] + '...' if len(obj.raw_title) > 50 else obj.raw_title
        return 'Untitled'

    raw_title_truncated.short_description = 'Title'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related()

    actions = ['mark_for_is_advanced_summary', 'mark_as_vectorized', 'clear_vector_assignment']

    def mark_for_is_advanced_summary(self, request, queryset):
        """Mark selected notes for advanced summary processing"""
        updated = queryset.update(is_advanced_summary=True)
        self.message_user(request, f'{updated} notes marked for advanced summary.')
    mark_for_is_advanced_summary.short_description = "Mark for advanced summary"

    def mark_as_vectorized(self, request, queryset):
        """Mark selected notes as vectorized"""
        updated = queryset.update(is_vectorized=True)
        self.message_user(request, f'{updated} notes marked as vectorized.')
    mark_as_vectorized.short_description = "Mark as vectorized"

    def clear_vector_assignment(self, request, queryset):
        """Clear vector group assignment"""
        updated = queryset.update(vector_group_id=None, is_vectorized=False)
        self.message_user(request, f'{updated} notes had vector assignments cleared.')
    clear_vector_assignment.short_description = "Clear vector assignment"

    # Custom list display methods for better formatting
    def publication_date(self, obj):
        if obj.publication_date:
            return obj.publication_date.strftime('%Y-%m-%d')
        return '-'
    publication_date.short_description = 'Pub Date'
    publication_date.admin_order_field = 'publication_date'

    def is_advanced_summary(self, obj):
        return '✓' if obj.is_advanced_summary else '✗'
    is_advanced_summary.short_description = 'Adv Summary'
    is_advanced_summary.boolean = True

    def is_vectorized(self, obj):
        return '✓' if obj.is_vectorized else '✗'
    is_vectorized.short_description = 'Vectorized'
    is_vectorized.boolean = True

    def vector_group_id(self, obj):
        return obj.vector_group_id if obj.vector_group_id else '-'
    vector_group_id.short_description = 'Vector Group'
    vector_group_id.admin_order_field = 'vector_group_id'


@admin.register(ResearchNoteIndustry)
class ResearchNoteIndustryAdmin(admin.ModelAdmin):
    list_display = ['research_note', 'ticker', 'industry', 'sub_industry']
    list_filter = ['industry', 'sub_industry']
    search_fields = ['ticker', 'industry', 'sub_industry', 'research_note__raw_title']
    autocomplete_fields = ['research_note']