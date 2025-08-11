# research_summaries/urls.py
from django.urls import path
from . import views

app_name = 'research_summaries'

urlpatterns = [
    # Main research summaries page
    path('summaries/', views.ResearchSummariesView.as_view(), name='research_summaries'),
    path('summaries/advanced/', views.AdvancedSummariesView.as_view(), name='advanced_summaries'),
    path('summaries/expert-calls/', views.ExpertCallsView.as_view(), name='expert_calls'),
    path('note/<int:note_id>/', views.research_note_detail, name='note_detail'),
    path('mark-as-read/', views.mark_as_read, name='mark_as_read'),
    path('mark-as-read-advanced/', views.mark_as_read_advanced, name='mark_as_read_advanced'),
    path('toggle-favorite/<int:note_id>/', views.toggle_note_favorite, name='toggle_favorite'),
    path('pdf/<int:note_id>/', views.get_pdf_url, name='get_pdf_url'),
    path('aggregate-summary/<str:ticker>/', views.aggregate_summary, name='aggregate_summary'),
    path('aggregate-summary-stream/<str:ticker>/', views.aggregate_summary_stream, name='aggregate_summary_stream'),
    path('flag-report/<int:note_id>/', views.flag_report, name='flag_report'),
    path('download-summary/<int:note_id>/', views.download_summary_pdf, name='download_summary_pdf'),
    path('set-advanced-summary/<int:note_id>/', views.set_advanced_summary, name='set_advanced_summary'),

    # Test/admin pages (keep these for now)
    path('email-test/', views.email_test_view, name='email_test'),
    path('download-test/', views.download_test_view, name='download_test'),
    path('document-cleaner/', views.document_cleaner_page, name='document_cleaner_page'),
    path('document-summarizer/', views.document_summarizer_page, name='document_summarizer_page'),

    # Streaming endpoints
    path('process-emails/', views.process_emails_stream, name='process_emails'),
    path('process-downloads/', views.process_downloads_stream, name='process_downloads'),
    path('clean-documents-stream/', views.clean_documents_stream, name='clean_documents_stream'),
    path('summarize-documents-stream/', views.summarize_documents_stream, name='summarize_documents_stream'),
    path('process-downloads-v2/', views.process_downloads_stream_v2, name='process_downloads_v2'),

    # AJAX endpoints
    path('process-emails-ajax/', views.process_emails_ajax, name='process_emails_ajax'),
    path('recent-notes/', views.get_recent_notes, name='recent_notes'),
    path('cleaning-status/', views.get_cleaning_status, name='get_cleaning_status'),
    path('summarization-status/', views.get_summarization_status, name='get_summarization_status'),

    # Persistence management URLs
    path('manage-persistence/', views.ResearchNotePersistenceView.as_view(), name='manage_persistence'),
    path('api/update-persistence/', views.api_update_persistence_status, name='api_update_persistence'),
    path('api/research-notes-data/', views.api_research_notes_data, name='api_research_notes_data'),
]