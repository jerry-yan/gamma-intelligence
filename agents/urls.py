# agents/urls.py
from django.urls import path
from . import views
from .views import AgentView

app_name = 'agents'

urlpatterns = [
    # Main chat interface
    path('', AgentView.as_view(), name='chat'),

    # API endpoints
    path('api/knowledge-bases/', views.api_knowledge_bases, name='api_knowledge_bases'),
    path('api/sessions/create/', views.api_create_session, name='api_create_session'),
    path('api/chat/stream/', views.api_chat_stream, name='api_chat_stream'),
    path('api/sessions/<uuid:session_id>/history/', views.api_session_history, name='api_session_history'),
    path('api/sessions/<uuid:session_id>/clear/', views.api_clear_session, name='api_clear_session'),
    path('api/sessions/', views.api_user_sessions, name='api_user_sessions'),
    path('api/messages/<int:message_id>/delete/', views.api_delete_message, name='api_delete_message'),

    # Other support functions
    path('upload-stocks/', views.StockTickerUploadView.as_view(), name='stock_ticker_upload'),
]