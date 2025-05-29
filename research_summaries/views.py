# research_summaries/views.py
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, StreamingHttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView
from django.core.paginator import Paginator
from django.db.models import Q, Count
from .email_parser import fetch_research_summaries
from .file_downloader import download_documents
from .models import ResearchNote
import json
import time


class ResearchSummariesView(LoginRequiredMixin, TemplateView):
    template_name = 'research_summaries/research_summaries.html'
    login_url = '/accounts/login/'

    def get_context_data(self, **kwargs):
        from django.utils import timezone
        from datetime import timedelta
        context = super().get_context_data(**kwargs)

        # Get user's last read time for default datetime filter
        user_profile = self.request.user.profile
        if user_profile.last_read_time:
            default_datetime = user_profile.last_read_time
        else:
            default_datetime = timezone.now() - timedelta(hours=24)

        # Get query parameters for filtering and search
        source_filter = self.request.GET.get('source', '')
        search_query = self.request.GET.get('search', '')
        datetime_filter = self.request.GET.get('datetime', '')
        page_number = self.request.GET.get('page', 1)

        # Parse datetime filter or use default
        if datetime_filter:
            try:
                from django.utils.dateparse import parse_datetime
                filter_datetime = parse_datetime(datetime_filter)
                if not filter_datetime:
                    # Try parsing as date and convert to datetime
                    from django.utils.dateparse import parse_date
                    filter_date = parse_date(datetime_filter)
                    if filter_date:
                        filter_datetime = timezone.make_aware(
                            timezone.datetime.combine(filter_date, timezone.datetime.min.time())
                        )
                    else:
                        filter_datetime = default_datetime
            except:
                filter_datetime = default_datetime
        else:
            filter_datetime = default_datetime

        # Base queryset - only show summarized research notes
        queryset = ResearchNote.objects.filter(status=3).order_by('-file_summary_time')

        # Apply datetime filter - show reports updated after the filter datetime
        queryset = queryset.filter(file_summary_time__gte=filter_datetime)

        # Apply other filters
        if source_filter:
            queryset = queryset.filter(source__icontains=source_filter)

        if search_query:
            queryset = queryset.filter(
                Q(raw_title__icontains=search_query) |
                Q(raw_author__icontains=search_query) |
                Q(raw_companies__icontains=search_query) |
                Q(parsed_ticker__icontains=search_query)
            )

        # Pagination
        paginator = Paginator(queryset, 20)  # Show 20 items per page
        page_obj = paginator.get_page(page_number)

        # Get status counts for dashboard (still show all statuses for reference)
        status_counts = {
            'total': ResearchNote.objects.count(),
            'not_downloaded': ResearchNote.objects.filter(status=0).count(),
            'downloaded': ResearchNote.objects.filter(status=1).count(),
            'preprocessed': ResearchNote.objects.filter(status=2).count(),
            'summarized': ResearchNote.objects.filter(status=3).count(),
            'filtered_count': queryset.count(),
        }

        # Get unique sources for filter dropdown (from summarized notes only)
        sources = ResearchNote.objects.filter(status=3).values_list('source', flat=True).distinct().exclude(
            source__isnull=True).exclude(source='')

        # Recent activity
        recent_summaries = ResearchNote.objects.filter(status=3).order_by('-file_summary_time')[:5]

        # Get latest report time on current page for "Mark as Read" functionality
        latest_report_time = None
        if page_obj.object_list:
            latest_report_time = max(
                note.file_summary_time for note in page_obj.object_list
                if note.file_summary_time
            )

        # Format datetime for HTML input (remove microseconds and timezone info for display)
        formatted_datetime = filter_datetime.strftime('%Y-%m-%dT%H:%M') if filter_datetime else ''

        context.update({
            'page_obj': page_obj,
            'research_notes': page_obj.object_list,
            'status_counts': status_counts,
            'sources': sorted(sources),
            'recent_summaries': recent_summaries,
            'current_filters': {
                'source': source_filter,
                'search': search_query,
                'datetime': datetime_filter,
            },
            'filter_datetime': filter_datetime,
            'formatted_datetime': formatted_datetime,
            'latest_report_time': latest_report_time,
            'user_last_read_time': user_profile.last_read_time,
        })

        return context


@login_required
def mark_as_read(request):
    """AJAX endpoint to update user's last_read_time"""
    if request.method == 'POST':
        from django.utils import timezone
        from datetime import timedelta
        import json

        try:
            data = json.loads(request.body)
            latest_report_time_str = data.get('latest_report_time')

            if latest_report_time_str:
                from django.utils.dateparse import parse_datetime
                latest_report_time = parse_datetime(latest_report_time_str)
                if latest_report_time:
                    # Add 1 second to the latest report time
                    new_last_read_time = latest_report_time + timedelta(seconds=1)

                    # Update user's profile
                    user_profile = request.user.profile
                    user_profile.last_read_time = new_last_read_time
                    user_profile.save()

                    return JsonResponse({
                        'success': True,
                        'new_last_read_time': new_last_read_time.isoformat(),
                        'message': f'Marked as read up to {new_last_read_time.strftime("%B %d, %Y at %I:%M %p")}'
                    })

            return JsonResponse({'success': False, 'message': 'Invalid datetime provided'})

        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    return JsonResponse({'success': False, 'message': 'Invalid request method'})


@login_required
def research_note_detail(request, note_id):
    """View individual research note with full summary"""
    note = get_object_or_404(ResearchNote, id=note_id)

    context = {
        'note': note,
        'summary_data': note.report_summary if note.report_summary else None,
    }

    return render(request, 'research_summaries/note_detail.html', context)


@login_required
def toggle_note_favorite(request, note_id):
    """AJAX endpoint to toggle favorite status (if you want to add this feature later)"""
    if request.method == 'POST':
        note = get_object_or_404(ResearchNote, id=note_id)
        # You can add a favorite field to your model later
        return JsonResponse({'success': True})
    return JsonResponse({'success': False})


# Keep all your existing test views below...

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
def download_test_view(request):
    """Test page for file downloading"""
    # Get notes that need downloading
    pending_downloads = ResearchNote.objects.filter(status=0).order_by('-created_at')[:10]
    recent_downloads = ResearchNote.objects.filter(status=1).order_by('-file_download_time')[:10]

    # Get status counts
    status_counts = {
        'total': ResearchNote.objects.count(),
        'not_downloaded': ResearchNote.objects.filter(status=0).count(),
        'downloaded': ResearchNote.objects.filter(status=1).count(),
        'preprocessed': ResearchNote.objects.filter(status=2).count(),
        'summarized': ResearchNote.objects.filter(status=3).count(),
    }

    context = {
        'pending_downloads': pending_downloads,
        'recent_downloads': recent_downloads,
        'status_counts': status_counts,
    }
    return render(request, 'research_summaries/download_test.html', context)


@login_required
def process_downloads_stream(request):
    """GET endpoint for Server-Sent Events file downloading"""

    def generate_updates():
        try:
            yield "data: " + json.dumps({"status": "info", "message": "🚀 Starting download process..."}) + "\n\n"

            for update in download_documents():
                yield "data: " + json.dumps(update) + "\n\n"
                # Reduced sleep time to avoid timeouts

        except GeneratorExit:
            # Handle case where client disconnects
            yield "data: " + json.dumps({"status": "info", "message": "🔌 Connection closed by client"}) + "\n\n"
            return
        except Exception as e:
            yield "data: " + json.dumps({"status": "error", "message": f"🚨 Unexpected error: {str(e)}"}) + "\n\n"

        # Final completion message
        yield "data: " + json.dumps({"status": "complete", "message": "✨ Download process finished"}) + "\n\n"

    response = StreamingHttpResponse(generate_updates(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['Connection'] = 'keep-alive'
    response['X-Accel-Buffering'] = 'no'  # Disable nginx buffering
    return response


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


@login_required
def document_cleaner_page(request):
    """Render the document cleaner test page"""
    pending_notes = ResearchNote.objects.filter(status=1)
    cleaned_notes = ResearchNote.objects.filter(status=2)

    context = {
        'pending_count': pending_notes.count(),
        'cleaned_count': cleaned_notes.count(),
        'pending_notes': pending_notes[:10],  # Show first 10 for preview
    }
    return render(request, 'research_summaries/document_cleaner.html', context)


@login_required
def clean_documents_stream(request):
    """Stream the document cleaning process with real-time updates"""

    def generate_cleaning_updates():
        """Generator that yields real-time updates during cleaning"""

        try:
            # Import here to avoid circular imports
            from research_summaries.management.commands.clean_documents import clean_pdf_from_s3
            from django.utils.timezone import now

            # Get initial counts
            pending_notes = ResearchNote.objects.filter(status=1)
            total_count = pending_notes.count()

            if total_count == 0:
                yield f"data: {json.dumps({'type': 'info', 'message': '✅ No PDFs awaiting cleaning.'})}\n\n"
                yield f"data: {json.dumps({'type': 'complete', 'message': 'No work to do!'})}\n\n"
                return

            yield f"data: {json.dumps({'type': 'info', 'message': f'🧹 Starting to clean {total_count} research PDFs from S3...'})}\n\n"

            # Process each note individually for better progress tracking
            success_count = 0

            for i, note in enumerate(pending_notes, 1):
                try:
                    # Extract S3 key from file_directory
                    s3_key = note.file_directory
                    if s3_key.startswith('https://'):
                        s3_key = s3_key.split('amazonaws.com/')[-1]
                    elif s3_key.startswith('s3://'):
                        s3_key = s3_key.split('/', 3)[-1]

                    yield f"data: {json.dumps({'type': 'progress', 'message': f'🔄 Processing {i}/{total_count}: {note.file_id}', 'current': i, 'total': total_count})}\n\n"

                    # Clean the document
                    if clean_pdf_from_s3(s3_key):
                        note.status = 2
                        note.file_update_time = now()
                        note.save(update_fields=["status", "file_update_time"])
                        success_count += 1
                        yield f"data: {json.dumps({'type': 'success', 'message': f'✅ Cleaned & updated {note.file_id}'})}\n\n"
                    else:
                        yield f"data: {json.dumps({'type': 'error', 'message': f'❌ Failed to clean {note.file_id}'})}\n\n"

                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'message': f'❌ Error processing {note.file_id}: {str(e)}'})}\n\n"

            # Final summary
            yield f"data: {json.dumps({'type': 'complete', 'message': f'🏁 Cleaning completed! {success_count}/{total_count} files processed successfully.'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'Fatal error during cleaning: {str(e)}'})}\n\n"

    response = StreamingHttpResponse(
        generate_cleaning_updates(),
        content_type='text/event-stream'
    )
    response['Cache-Control'] = 'no-cache'
    response['Connection'] = 'keep-alive'
    response['X-Accel-Buffering'] = 'no'
    return response


@login_required
def get_cleaning_status(request):
    """Get current status of document cleaning queue"""
    pending_count = ResearchNote.objects.filter(status=1).count()
    cleaned_count = ResearchNote.objects.filter(status=2).count()

    return JsonResponse({
        'pending_count': pending_count,
        'cleaned_count': cleaned_count,
    })


# Add these new view functions to your existing views.py:

@login_required
def document_summarizer_page(request):
    """Render the document summarizer test page"""
    pending_notes = ResearchNote.objects.filter(status=2)
    summarized_notes = ResearchNote.objects.filter(status=3)

    context = {
        'pending_count': pending_notes.count(),
        'summarized_count': summarized_notes.count(),
        'pending_notes': pending_notes[:10],  # Show first 10 for preview
    }
    return render(request, 'research_summaries/document_summarizer.html', context)


@login_required
def summarize_documents_stream(request):
    """Stream the document summarization process with real-time updates"""

    def generate_summarization_updates():
        """Generator that yields real-time updates during summarization"""

        try:
            # Import here to avoid circular imports
            from research_summaries.document_summarizer import summarize_documents
            from django.utils.timezone import now

            # Get initial counts
            pending_notes = ResearchNote.objects.filter(status=2)
            total_count = pending_notes.count()

            if total_count == 0:
                yield f"data: {json.dumps({'type': 'info', 'message': '✅ No documents awaiting summarization.'})}\n\n"
                yield f"data: {json.dumps({'type': 'complete', 'message': 'No work to do!'})}\n\n"
                return

            yield f"data: {json.dumps({'type': 'info', 'message': f'📝 Starting to summarize {total_count} research documents...'})}\n\n"

            # We'll need to modify the summarize_documents function to yield updates
            # For now, let's call it and provide basic progress tracking

            # Process each note individually for better progress tracking
            success_count = 0

            for i, note in enumerate(pending_notes, 1):
                try:
                    yield f"data: {json.dumps({'type': 'progress', 'message': f'🔄 Processing {i}/{total_count}: {note.file_id}', 'current': i, 'total': total_count})}\n\n"

                    # Call individual document processing (we'll need to modify the main function)
                    from research_summaries.document_summarizer import process_single_document

                    if process_single_document(note):
                        success_count += 1
                        yield f"data: {json.dumps({'type': 'success', 'message': f'✅ Summarized {note.file_id}'})}\n\n"
                    else:
                        yield f"data: {json.dumps({'type': 'error', 'message': f'❌ Failed to summarize {note.file_id}'})}\n\n"

                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'message': f'❌ Error processing {note.file_id}: {str(e)}'})}\n\n"

            # Final summary
            yield f"data: {json.dumps({'type': 'complete', 'message': f'🏁 Summarization completed! {success_count}/{total_count} documents processed successfully.'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'Fatal error during summarization: {str(e)}'})}\n\n"

    response = StreamingHttpResponse(
        generate_summarization_updates(),
        content_type='text/event-stream'
    )
    response['Cache-Control'] = 'no-cache'
    response['Connection'] = 'keep-alive'
    response['X-Accel-Buffering'] = 'no'
    return response


@login_required
def get_summarization_status(request):
    """Get current status of document summarization queue"""
    pending_count = ResearchNote.objects.filter(status=2).count()
    summarized_count = ResearchNote.objects.filter(status=3).count()
    error_count = ResearchNote.objects.filter(status=10).count()

    return JsonResponse({
        'pending_count': pending_count,
        'summarized_count': summarized_count,
        'error_count': error_count,
    })