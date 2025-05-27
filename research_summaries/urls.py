# research_summaries/urls.py
from django.urls import path
from . import views

app_name = 'research_summaries'

urlpatterns = [
    path('email-test/', views.email_test_view, name='email_test'),
    path('process-emails/', views.process_emails_ajax, name='process_emails'),
    path('recent-notes/', views.get_recent_notes, name='recent_notes'),
]