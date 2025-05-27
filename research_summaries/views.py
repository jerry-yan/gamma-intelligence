# research_summaries/views.py
from django.shortcuts import render
from django.http import JsonResponse, StreamingHttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView
from .email_parser import fetch_research_summaries
from .models import ResearchNote
import json
import time


class ResearchSummariesView(LoginRequiredMixin, TemplateView):
    template_name = 'research_summaries/research_summaries.html'
    login_url = '/accounts/login/'


@login_required
def email_test_view(request):
    """Test page for email processing"""
    recent_notes = ResearchNote.objects.order_by('-created_at')[:5]

    # Get status counts
    status_counts = {
        'total': ResearchNote.objects.count(),
        'not_downloaded': ResearchNote.objects.filter(status=0).count(),
        'downloaded': ResearchNote.objects.filter(status=1).count(),
        'preprocessed': ResearchNote.objects.filter(status=2).count(),
        'summarized': ResearchNote.objects.filter(status=3).count(),
    }

    context = {
        'recent_notes': recent_notes,
        'status_counts': status_counts,
    }
    return render(request, 'research_summaries/email_test.html', context)


@login_required
def process_emails_stream(request):
    """GET endpoint for Server-Sent Events email processing"""

    def generate_updates():
        yield "data: " + json.dumps({"status": "info", "message": "🚀 Starting email processing..."}) + "\n\n"

        try:
            for update in fetch_research_summaries():
                yield "data: " + json.dumps(update) + "\n\n"
                time.sleep(0.1)  # Small delay to make updates visible

        except Exception as e:
            yield "data: " + json.dumps({"status": "error", "message": f"🚨 Unexpected error: {str(e)}"}) + "\n\n"

        # Final completion message
        yield "data: " + json.dumps({"status": "complete", "message": "✨ Email processing finished"}) + "\n\n"

    response = StreamingHttpResponse(generate_updates(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['Connection'] = 'keep-alive'
    response['X-Accel-Buffering'] = 'no'  # Disable nginx buffering
    return response


@csrf_exempt
@require_POST
@login_required
def process_emails_ajax(request):
    """AJAX endpoint for processing emails with real-time updates"""

    def generate_updates():
        yield "data: " + json.dumps({"status": "info", "message": "🚀 Starting email processing..."}) + "\n\n"

        try:
            for update in fetch_research_summaries():
                yield "data: " + json.dumps(update) + "\n\n"
                time.sleep(0.1)  # Small delay to make updates visible

        except Exception as e:
            yield "data: " + json.dumps({"status": "error", "message": f"🚨 Unexpected error: {str(e)}"}) + "\n\n"

        # Final completion message
        yield "data: " + json.dumps({"status": "complete", "message": "✨ Email processing finished"}) + "\n\n"

    response = StreamingHttpResponse(generate_updates(), content_type='text/plain')
    response['Cache-Control'] = 'no-cache'
    response['Connection'] = 'keep-alive'
    return response


@login_required
def get_recent_notes(request):
    """AJAX endpoint to get recent notes for refreshing the list"""
    recent_notes = ResearchNote.objects.order_by('-created_at')[:10]
    notes_data = []

    for note in recent_notes:
        # Format the created_at timestamp
        created_at_str = note.created_at.strftime('%b %d, %H:%M') if note.created_at else 'Unknown'

        # Truncate title if it's too long
        title = note.raw_title or 'Untitled'
        if len(title) > 50:
            title = title[:47] + '...'

        # Handle companies display
        companies_display = note.raw_companies or 'None'
        if len(companies_display) > 30:
            companies_display = companies_display[:27] + '...'

        notes_data.append({
            'id': note.id,
            'title': title,
            'source': note.source or 'Unknown',
            'author': note.raw_author or 'Unknown',
            'companies': companies_display,
            'company_count': note.raw_company_count or 0,
            'status': note.get_status_display(),
            'status_value': note.status,
            'created_at': created_at_str,
            'file_id': note.file_id or 'No ID',
            'page_count': note.raw_page_count or 0,
        })

    # Get updated status counts
    status_counts = {
        'total': ResearchNote.objects.count(),
        'not_downloaded': ResearchNote.objects.filter(status=0).count(),
        'downloaded': ResearchNote.objects.filter(status=1).count(),
        'preprocessed': ResearchNote.objects.filter(status=2).count(),
        'summarized': ResearchNote.objects.filter(status=3).count(),
    }

    return JsonResponse({
        'notes': notes_data,
        'status_counts': status_counts
    })