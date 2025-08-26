# agents/urls.py
from django.urls import path
from . import views, api_views, knowledge_base_views, prompt_views

app_name = 'agents'

urlpatterns = [
    # Main chat interface
    path('', views.AgentView.as_view(), name='chat'),
    path('v2/', views.AgentView2.as_view(), name='chat_v2'),
    path('v3/', views.AgentView3.as_view(), name='chat_v3'),

    # KnowledgeBase management pages
    path('knowledge-bases/create/', knowledge_base_views.CreateKnowledgeBaseView.as_view(), name='create_knowledge_base'),
    path('knowledge-bases/manage/', knowledge_base_views.ManageKnowledgeBasesView.as_view(), name='manage_knowledge_bases'),
    path('knowledge-bases/metrics/', knowledge_base_views.KnowledgeBaseMetricsView.as_view(), name='knowledge_base_metrics'),

    # API endpoints
    path('api/knowledge-bases/', views.api_knowledge_bases, name='api_knowledge_bases'),
    path('api/sessions/create/', views.api_create_session, name='api_create_session'),
    path('api/chat/stream/', views.api_chat_stream, name='api_chat_stream'),
    path('api/sessions/<uuid:session_id>/history/', views.api_session_history, name='api_session_history'),
    path('api/sessions/<uuid:session_id>/clear/', views.api_clear_session, name='api_clear_session'),
    path('api/sessions/<uuid:session_id>/delete/', views.api_delete_session, name='api_delete_session'),
    path('api/sessions/<uuid:session_id>/rename/', views.api_rename_session, name='api_rename_session'),
    path('api/sessions/<uuid:session_id>/export-pdf/', views.api_export_session_pdf, name='api_export_session_pdf'),  # Export PDF
    path('api/sessions/', views.api_user_sessions, name='api_user_sessions'),
    path('api/messages/<int:message_id>/delete/', views.api_delete_message, name='api_delete_message'),

    path('api/knowledge-bases/create/', api_views.api_create_knowledge_base, name='api_create_knowledge_base'),
    path('api/knowledge-bases/list/', api_views.api_list_knowledge_bases, name='api_list_knowledge_bases'),
    path('api/knowledge-bases/<int:kb_id>/delete/', api_views.api_delete_knowledge_base, name='api_delete_knowledge_base'),

    # Prompts
    path('prompts/', prompt_views.PromptListView.as_view(), name='prompt_list'),
    path('prompts/create/', prompt_views.PromptCreateView.as_view(), name='prompt_create'),
    path('prompts/<int:pk>/edit/', prompt_views.PromptUpdateView.as_view(), name='prompt_update'),
    path('prompts/<int:pk>/delete/', prompt_views.prompt_delete_view, name='prompt_delete'),
    path('prompts/<int:pk>/detail/', prompt_views.prompt_detail_api, name='prompt_detail'),

    # Other support functions
    path('upload-stocks/', views.StockTickerUploadView.as_view(), name='stock_ticker_upload'),
]