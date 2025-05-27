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
        'raw_author',
        'raw_company_count',
        'status',
        'created_at'
    ]
    list_filter = [
        'status',
        'source',
        'provider',
        'created_at',
        'file_download_time'
    ]
    search_fields = [
        'file_id',
        'raw_title',
        'raw_author',
        'source',
        'raw_companies'
    ]
    readonly_fields = [
        'created_at',
        'updated_at'
    ]
    inlines = [ResearchNoteIndustryInline]

    fieldsets = (
        ('Core Information', {
            'fields': ('source', 'provider', 'file_id', 'download_link')
        }),
        ('Content Details', {
            'fields': (
            'raw_title', 'raw_author', 'raw_companies', 'raw_company_count', 'raw_page_count', 'parsed_ticker')
        }),
        ('Classification', {
            'fields': ('report_type', 'status')
        }),
        ('File Management', {
            'fields': ('file_directory', 'file_download_time', 'file_update_time', 'file_summary_time')
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


@admin.register(ResearchNoteIndustry)
class ResearchNoteIndustryAdmin(admin.ModelAdmin):
    list_display = ['research_note', 'ticker', 'industry', 'sub_industry']
    list_filter = ['industry', 'sub_industry']
    search_fields = ['ticker', 'industry', 'sub_industry', 'research_note__raw_title']
    autocomplete_fields = ['research_note']