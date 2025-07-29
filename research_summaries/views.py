# research_summaries/views.py
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, StreamingHttpResponse
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods
from django.views.generic import TemplateView
from django.views.decorators.cache import cache_control
import logging
from django.db.models import Q
from .email_parser import fetch_research_summaries
from .file_downloader import download_documents
from .models import ResearchNote
import boto3
from botocore.exceptions import ClientError
from django.conf import settings
import json
import time
import markdown
from django.utils.html import mark_safe
from research_summaries.OpenAI_toolbox.prompts import AGGREGATE_SUMMARY_INSTRUCTION
from research_summaries.openai_utils import get_openai_client
from research_summaries.processors.file_downloader_2 import download_documents_playwright
from agents.models import StockTicker


logger = logging.getLogger(__name__)

class ResearchSummariesView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = 'research_summaries/research_summaries.html'
    login_url = '/accounts/login/'
    permission_required = 'accounts.can_view_research_summaries'

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

        # Group the results
        from collections import defaultdict, OrderedDict

        # Get all results for grouping (limit to reasonable number for performance)
        all_results = list(queryset[:400])  # Limit to 200 most recent results

        # Separate reports with tickers from those without
        ticker_groups = defaultdict(list)
        report_type_groups = defaultdict(list)

        for note in all_results:
            if note.parsed_ticker:
                ticker_groups[note.parsed_ticker].append(note)
            else:
                report_type = note.report_type or "Uncategorized"
                report_type_groups[report_type].append(note)

        # Sort ticker groups alphabetically and sort reports within each group by summary time
        sorted_ticker_groups = OrderedDict()
        for ticker in sorted(ticker_groups.keys()):
            sorted_ticker_groups[ticker] = sorted(
                ticker_groups[ticker],
                key=lambda x: (x.source or '', x.raw_title or '')
            )

        # Sort report type groups alphabetically and sort reports within each group by summary time
        sorted_report_type_groups = OrderedDict()
        for report_type in sorted(report_type_groups.keys()):
            sorted_report_type_groups[report_type] = sorted(
                report_type_groups[report_type],
                key=lambda x: (x.source or '', x.raw_title or '')
            )

        # Calculate total results
        total_results = len(all_results)
        total_available = queryset.count()

        # Simple result info (no complex pagination for grouped results)
        results_info = {
            'showing_count': total_results,
            'total_available': total_available,
            'limited': total_results < total_available
        }

        # Get status counts for dashboard (still show all statuses for reference)
        status_counts = {
            'total': ResearchNote.objects.count(),
            'not_downloaded': ResearchNote.objects.filter(status=0).count(),
            'downloaded': ResearchNote.objects.filter(status=1).count(),
            'preprocessed': ResearchNote.objects.filter(status=2).count(),
            'summarized': ResearchNote.objects.filter(status=3).count(),
            'filtered_count': total_results,
        }

        # Get unique sources for filter dropdown (from summarized notes only)
        sources = ResearchNote.objects.filter(status=3).values_list('source', flat=True).exclude(
            source__isnull=True).exclude(source='').distinct().order_by('source')

        # Recent activity
        recent_summaries = ResearchNote.objects.filter(status=3).order_by('-file_summary_time')[:5]

        # Get latest report time from all results for "Mark as Read" functionality
        latest_report_time = None
        if all_results:
            latest_report_time = max(
                note.file_summary_time for note in all_results
                if note.file_summary_time
            )

        # Format datetime for HTML input (remove microseconds and timezone info for display)
        formatted_datetime = filter_datetime.strftime('%Y-%m-%dT%H:%M') if filter_datetime else ''

        context.update({
            'ticker_groups': sorted_ticker_groups,
            'report_type_groups': sorted_report_type_groups,
            'results_info': results_info,
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
                    new_last_read_time = latest_report_time + timedelta(seconds=59)

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
            from research_summaries.processors.document_cleaner import clean_pdf_from_s3
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

                    # Clean the document and get hash
                    success, file_hash = clean_pdf_from_s3(s3_key)

                    if success:
                        note.status = 2
                        note.file_update_time = now()
                        note.file_hash_id = file_hash
                        note.save(update_fields=["status", "file_update_time", "file_hash_id"])
                        success_count += 1
                        yield f"data: {json.dumps({'type': 'success', 'message': f'✅ Cleaned & updated {note.file_id} with hash: {file_hash[:8]}...'})}\n\n"
                    else:
                        yield f"data: {json.dumps({'type': 'error', 'message': f'❌ Failed to clean {note.file_id}'})}\n\n"

                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'message': f'❌ Error processing {note.file_id}: {str(e)}'})}\n\n"

            # Final summary
            yield f"data: {json.dumps({'type': 'complete', 'message': f'🏁 Cleaning completed! {success_count}/{total_count} files processed successfully.'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'❌ Fatal error during cleaning: {str(e)}'})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'message': 'Process terminated due to error.'})}\n\n"

    # Return StreamingHttpResponse with correct content type for SSE
    response = StreamingHttpResponse(
        generate_cleaning_updates(),
        content_type='text/event-stream'
    )
    response['Cache-Control'] = 'no-cache'
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

@login_required
@cache_control(no_cache=True)
def get_pdf_url(request, note_id):
    """Generate a pre-signed URL for viewing PDF from S3"""
    try:
        note = get_object_or_404(ResearchNote, id=note_id)

        if not note.file_directory:
            return JsonResponse({
                'error': 'No PDF file associated with this research note'
            }, status=404)

        if note.status < 1:
            return JsonResponse({
                'error': 'PDF file is not yet downloaded. Please try again later.'
            }, status=404)

        # Extract S3 key from file_directory
        s3_key = note.file_directory.strip()

        if s3_key.startswith('https://'):
            try:
                s3_key = s3_key.split('amazonaws.com/')[-1]
            except IndexError:
                s3_key = s3_key.split('.com/')[-1]
        elif s3_key.startswith('s3://'):
            parts = s3_key.split('/', 3)
            if len(parts) < 4:
                return JsonResponse({'error': 'Invalid file path format'}, status=400)
            s3_key = parts[3]

        # Check required settings
        required_settings = ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_STORAGE_BUCKET_NAME']
        missing_settings = [setting for setting in required_settings
                            if not getattr(settings, setting, None)]

        if missing_settings:
            return JsonResponse({
                'error': 'Server configuration error. Please contact administrator.'
            }, status=500)

        # Initialize S3 client
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=getattr(settings, 'AWS_S3_REGION_NAME', 'us-east-1')
        )

        bucket_name = settings.AWS_STORAGE_BUCKET_NAME

        # Check if object exists
        try:
            s3_client.head_object(Bucket=bucket_name, Key=s3_key)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                return JsonResponse({
                    'error': 'PDF file not found in storage.'
                }, status=404)
            else:
                return JsonResponse({
                    'error': 'Unable to access PDF file.'
                }, status=500)

        # Generate pre-signed URL for inline viewing
        try:
            # Clean filename for Content-Disposition
            clean_filename = (note.raw_title or 'Research_Report').replace('"', '').replace('\\', '')

            presigned_url = s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': bucket_name,
                    'Key': s3_key,
                    # CRITICAL: Set Content-Disposition to inline for browser viewing
                    'ResponseContentDisposition': 'inline',
                    'ResponseContentType': 'application/pdf'
                },
                ExpiresIn=3600,  # 1 hour
                HttpMethod='GET'
            )

            return JsonResponse({
                'success': True,
                'url': presigned_url,
                'filename': f"{clean_filename}.pdf",
                'expires_in': 3600
            })

        except ClientError as e:
            return JsonResponse({
                'error': f'Could not generate PDF access URL: {str(e)}'
            }, status=500)

    except Exception as e:
        logger.error(f"Unexpected error in get_pdf_url for note {note_id}: {e}")
        return JsonResponse({
            'error': 'An unexpected error occurred. Please try again later.'
        }, status=500)


@login_required
def aggregate_summary_stream(request, ticker):
    """Stream the aggregate summary generation with real-time updates"""

    def generate_summary_updates():
        """Generator that yields real-time updates during summary generation"""
        try:
            from django.utils import timezone
            from datetime import timedelta

            yield f"data: {json.dumps({'type': 'info', 'message': f'🔍 Gathering {ticker} reports with your current filters...'})}\n\n"

            # Get user's last read time for default datetime filter (same logic as main view)
            user_profile = request.user.profile
            if user_profile.last_read_time:
                default_datetime = user_profile.last_read_time
            else:
                default_datetime = timezone.now() - timedelta(hours=24)

            # Get query parameters for filtering (same as main view)
            source_filter = request.GET.get('source', '')
            search_query = request.GET.get('search', '')
            datetime_filter = request.GET.get('datetime', '')

            # Parse datetime filter or use default (same logic as main view)
            if datetime_filter:
                try:
                    from django.utils.dateparse import parse_datetime, parse_date
                    filter_datetime = parse_datetime(datetime_filter)
                    if not filter_datetime:
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

            # Build queryset with EXACT same filters as main research summaries page
            queryset = ResearchNote.objects.filter(
                status=3,  # Only summarized notes
                parsed_ticker=ticker,
                report_summary__isnull=False
            ).order_by('-file_summary_time')

            # Apply datetime filter - show reports updated after the filter datetime
            queryset = queryset.filter(file_summary_time__gte=filter_datetime)

            # Apply other filters (same as main view)
            if source_filter:
                queryset = queryset.filter(source__icontains=source_filter)

            if search_query:
                queryset = queryset.filter(
                    Q(raw_title__icontains=search_query) |
                    Q(raw_author__icontains=search_query) |
                    Q(raw_companies__icontains=search_query) |
                    Q(parsed_ticker__icontains=search_query)
                )

            notes = list(queryset)
            notes_count = len(notes)

            if notes_count == 0:
                yield f"data: {json.dumps({'type': 'error', 'message': f'❌ No reports found for {ticker} with current filters'})}\n\n"
                return

            yield f"data: {json.dumps({'type': 'info', 'message': f'📊 Found {notes_count} reports for {ticker}'})}\n\n"
            yield f"data: {json.dumps({'type': 'info', 'message': '🤖 Generating aggregate summary with OpenAI...'})}\n\n"

            # Generate aggregate summary (this is the long-running part)
            try:
                summary_markdown = generate_aggregate_summary(ticker, notes)

                yield f"data: {json.dumps({'type': 'info', 'message': '📝 Converting summary to HTML...'})}\n\n"

                # Convert markdown to HTML
                html_content = markdown.markdown(
                    summary_markdown,
                    extensions=['extra', 'codehilite']
                )

                yield f"data: {json.dumps({'type': 'success', 'message': f'✅ Successfully generated aggregate summary for {ticker}!'})}\n\n"

                # Send the final result
                yield f"data: {json.dumps({'type': 'complete', 'summary_html': mark_safe(html_content).__str__(), 'ticker': ticker, 'notes_count': notes_count})}\n\n"

            except Exception as e:
                logger.error(f"Error generating aggregate summary for {ticker}: {e}")
                yield f"data: {json.dumps({'type': 'error', 'message': f'❌ Failed to generate summary: {str(e)}'})}\n\n"

        except Exception as e:
            logger.error(f"Error in aggregate_summary_stream for {ticker}: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': f'🚨 Critical error: {str(e)}'})}\n\n"

    response = StreamingHttpResponse(
        generate_summary_updates(),
        content_type='text/event-stream'
    )
    response['Cache-Control'] = 'no-cache'
    response['Connection'] = 'keep-alive'
    response['X-Accel-Buffering'] = 'no'
    return response


@login_required
def aggregate_summary(request, ticker):
    """Generate and display aggregate summary for a specific ticker with same filters as main page"""

    # Check if this is a streaming request
    if request.GET.get('stream') == 'true':
        return aggregate_summary_stream(request, ticker)

    # Check if this is a full page request (new tab) - show loading page
    if request.GET.get('fullpage'):
        try:
            from django.utils import timezone
            from datetime import timedelta

            # Get basic info for the loading page
            user_profile = request.user.profile
            if user_profile.last_read_time:
                default_datetime = user_profile.last_read_time
            else:
                default_datetime = timezone.now() - timedelta(hours=24)

            # Get query parameters
            source_filter = request.GET.get('source', '')
            search_query = request.GET.get('search', '')
            datetime_filter = request.GET.get('datetime', '')

            # Parse datetime filter
            if datetime_filter:
                try:
                    from django.utils.dateparse import parse_datetime, parse_date
                    filter_datetime = parse_datetime(datetime_filter)
                    if not filter_datetime:
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

            # Get count of notes for display
            queryset = ResearchNote.objects.filter(
                status=3,
                parsed_ticker=ticker,
                report_summary__isnull=False,
                file_summary_time__gte=filter_datetime
            )

            if source_filter:
                queryset = queryset.filter(source__icontains=source_filter)
            if search_query:
                queryset = queryset.filter(
                    Q(raw_title__icontains=search_query) |
                    Q(raw_author__icontains=search_query) |
                    Q(raw_companies__icontains=search_query) |
                    Q(parsed_ticker__icontains=search_query)
                )

            notes_count = queryset.count()

            if notes_count == 0:
                return render(request, 'research_summaries/aggregate_summary.html', {
                    'ticker': ticker,
                    'error': f"No reports found for {ticker} with current filters",
                    'notes_count': 0
                })

            return render(request, 'research_summaries/aggregate_summary.html', {
                'ticker': ticker,
                'notes_count': notes_count,
                'loading': True
            })

        except Exception as e:
            logger.error(f"Error in aggregate_summary fullpage view for {ticker}: {e}")
            return render(request, 'research_summaries/aggregate_summary.html', {
                'ticker': ticker,
                'error': "An unexpected error occurred",
                'notes_count': 0
            })

    # For regular AJAX requests, return an error suggesting to use the modal instead
    return JsonResponse({
        'success': False,
        'error': 'Direct AJAX requests are no longer supported. Please use the modal interface.',
        'suggestion': 'Use the aggregate summary button on the research summaries page.'
    })


def generate_aggregate_summary(ticker, notes):
    """
    Generate aggregate summary for multiple research notes of the same ticker.

    Args:
        ticker (str): The stock ticker symbol
        notes (list): List of ResearchNote objects that match user's current filters

    Returns:
        str: Markdown-formatted aggregate summary
    """

    MODEL = "gpt-4.1-mini-2025-04-14"

    notes_count = len(notes)
    if notes_count == 0:
        return "# No Reports Found\n\nNo reports available for analysis."

    try:
        reports_summaries = []
        for note in notes:
            if note.report_summary:
                reports_summaries.append(note.report_summary)

        if not reports_summaries:
            return f"# {ticker} - No Summary Data Available\n\nNo report summaries found for analysis."

        client = get_openai_client()

        prompt_content = (
            f"Please create a comprehensive aggregate research summary for {ticker} based on the following {len(reports_summaries)} research reports.\n\n"
            "**Report Summaries:**\n"
            f"{json.dumps(reports_summaries, indent=2, default=str)}"
        )

        response = client.responses.create(
            model=MODEL,
            instructions=AGGREGATE_SUMMARY_INSTRUCTION,
            input=prompt_content,
            temperature=0.2,
        )

        summarized_text = response.output_text

        return summarized_text

    except Exception as e:
        logger.error(f"Error generating aggregate summary for {ticker}: {e}")
        return f"# {ticker} - Summary Generation Error\n\nError generating summary: {str(e)}"


@login_required
@require_POST
def flag_report(request, note_id):
    """Flag a report for report type reassignment"""
    try:
        import json
        from django.utils.timezone import now

        # Get the research note
        note = get_object_or_404(ResearchNote, id=note_id)

        # Parse request body
        data = json.loads(request.body)
        new_report_type = data.get('new_report_type', '').strip()

        # Validate the new report type
        valid_report_types = [
            "Initiation Report",
            "Company Update",
            "Quarter Preview",
            "Quarter Review",
            "Industry Note",
            "Macro/Strategy Report",
            "Invalid"
        ]

        if new_report_type not in valid_report_types:
            return JsonResponse({
                'success': False,
                'error': 'Invalid report type selected'
            }, status=400)

        # Store original values for logging
        original_report_type = note.report_type
        original_status = note.status

        # Update the note
        note.report_type = new_report_type
        note.status = 2  # Revert to "Preprocessed" status
        note.file_update_time = now()

        # Clear the existing summary since we're changing the type
        note.report_summary = None
        note.parsed_ticker = None
        note.file_summary_time = None

        # Save the changes
        note.save(update_fields=[
            'report_type',
            'status',
            'file_update_time',
            'report_summary',
            'parsed_ticker',
            'file_summary_time'
        ])

        # Log the change
        logger.info(f"Report {note.file_id} flagged by user {request.user.username}: "
                    f"type changed from '{original_report_type}' to '{new_report_type}', "
                    f"status reverted from {original_status} to 2")

        return JsonResponse({
            'success': True,
            'message': f'Report successfully flagged and reassigned to "{new_report_type}"',
            'new_report_type': new_report_type,
            'new_status': 2,
            'note_id': note_id
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid request format'
        }, status=400)

    except Exception as e:
        logger.error(f"Error flagging report {note_id}: {e}")
        return JsonResponse({
            'success': False,
            'error': 'An unexpected error occurred'
        }, status=500)


@login_required
def process_downloads_stream_v2(request):
    """GET endpoint for Server-Sent Events file downloading using Playwright/Firefox"""

    def generate_updates():
        try:
            yield "data: " + json.dumps({"status": "info", "message": "🚀 Starting download process (Playwright/Firefox)..."}) + "\n\n"

            for update in download_documents_playwright():
                yield "data: " + json.dumps(update) + "\n\n"
                # Reduced sleep time to avoid timeouts

        except GeneratorExit:
            # Handle case where client disconnects
            yield "data: " + json.dumps({"status": "info", "message": "🔌 Connection closed by client"}) + "\n\n"
            return
        except Exception as e:
            yield "data: " + json.dumps({"status": "error", "message": f"🚨 Unexpected error: {str(e)}"}) + "\n\n"

        # Final completion message
        yield "data: " + json.dumps({"status": "complete", "message": "✨ Download process finished (Playwright/Firefox)"}) + "\n\n"

    response = StreamingHttpResponse(generate_updates(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['Connection'] = 'keep-alive'
    response['X-Accel-Buffering'] = 'no'  # Disable nginx buffering
    return response


@login_required
@require_POST
def download_summary_pdf(request, note_id):
    """Generate and download a PDF of the research summary"""
    try:
        note = get_object_or_404(ResearchNote, id=note_id)

        if not note.report_summary:
            return JsonResponse({
                'success': False,
                'error': 'No summary available for this report'
            }, status=404)

        # Import reportlab for PDF generation
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
        import io
        from django.http import FileResponse

        # Create a file-like buffer to receive PDF data
        buffer = io.BytesIO()

        # Create the PDF object, using the buffer as its "file"
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)

        # Container for the 'Flowable' objects
        elements = []

        # Define styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            spaceAfter=30,
            alignment=TA_CENTER
        )

        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            spaceAfter=12,
            spaceBefore=16,
            textColor=colors.darkblue
        )

        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=10,
            spaceAfter=12,
            alignment=TA_JUSTIFY
        )

        # Title
        clean_title = note.raw_title or "Research Report Summary"
        elements.append(Paragraph(clean_title, title_style))
        elements.append(Spacer(1, 12))

        # Metadata section
        metadata_data = []
        if note.source:
            metadata_data.append(['Source:', note.source])
        if note.parsed_ticker:
            metadata_data.append(['Ticker:', note.parsed_ticker])
        if note.publication_date:
            metadata_data.append(['Publication Date:', note.publication_date.strftime('%B %d, %Y')])
        if note.raw_author:
            metadata_data.append(['Author(s):', note.raw_author])
        if note.report_type:
            metadata_data.append(['Report Type:', note.report_type])

        if metadata_data:
            metadata_table = Table(metadata_data, colWidths=[1.5 * inch, 4 * inch])
            metadata_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(metadata_table)
            elements.append(Spacer(1, 20))

        # Summary content
        summary_data = note.report_summary

        # Add different sections based on report type
        if note.report_type == "Company Update":
            # Sentiment, Price Target, Rating
            if summary_data.get('sentiment') or summary_data.get('price_target') or summary_data.get('stock_rating'):
                elements.append(Paragraph("Key Metrics", heading_style))

                key_metrics = []
                if summary_data.get('sentiment'):
                    key_metrics.append(['Sentiment:', summary_data['sentiment']])
                if summary_data.get('price_target'):
                    key_metrics.append(['Price Target:', f"${summary_data['price_target']}"])
                if summary_data.get('stock_rating'):
                    key_metrics.append(['Rating:', summary_data['stock_rating']])

                if key_metrics:
                    metrics_table = Table(key_metrics, colWidths=[1.5 * inch, 4 * inch])
                    metrics_table.setStyle(TableStyle([
                        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, -1), 10),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ]))
                    elements.append(metrics_table)
                    elements.append(Spacer(1, 12))

            # Executive Summary
            if summary_data.get('executive_summary'):
                elements.append(Paragraph("Executive Summary", heading_style))
                elements.append(Paragraph(summary_data['executive_summary'], normal_style))

            # Bull Points
            if summary_data.get('bull_points'):
                elements.append(Paragraph("Bullish Points", heading_style))
                for point in summary_data['bull_points']:
                    elements.append(Paragraph(f"• {point}", normal_style))

            # Bear Points
            if summary_data.get('bear_points'):
                elements.append(Paragraph("Bearish Points", heading_style))
                for point in summary_data['bear_points']:
                    elements.append(Paragraph(f"• {point}", normal_style))

            # Valuation Analysis
            if summary_data.get('valuation_analysis'):
                elements.append(Paragraph("Valuation Analysis", heading_style))
                elements.append(Paragraph(summary_data['valuation_analysis'], normal_style))

            # Extra Details
            if summary_data.get('extra_details'):
                elements.append(Paragraph("Additional Details", heading_style))
                elements.append(Paragraph(summary_data['extra_details'], normal_style))

        else:
            # Generic handling for other report types
            for key, value in summary_data.items():
                if key in ['stock_ticker', 'title', 'source', 'authors']:
                    continue  # Skip metadata we already showed

                if value:
                    # Convert key to readable format
                    readable_key = key.replace('_', ' ').title()
                    elements.append(Paragraph(readable_key, heading_style))

                    if isinstance(value, list):
                        for item in value:
                            if isinstance(item, dict):
                                # Handle complex objects like stock_recaps
                                for sub_key, sub_value in item.items():
                                    if sub_value:
                                        elements.append(
                                            Paragraph(f"<b>{sub_key.replace('_', ' ').title()}:</b> {sub_value}",
                                                      normal_style))
                            else:
                                elements.append(Paragraph(f"• {item}", normal_style))
                    else:
                        elements.append(Paragraph(str(value), normal_style))

        # Build PDF
        doc.build(elements)

        # Get the value of the BytesIO buffer and return it as a response
        buffer.seek(0)

        # Create filename
        base_filename = (note.raw_title or "Research_Report").replace('"', '').replace('\\', '').replace('/', '_')[:50]
        filename = f"{base_filename}_summary.pdf"

        response = FileResponse(
            buffer,
            as_attachment=True,
            filename=filename,
            content_type='application/pdf'
        )

        return response

    except ImportError:
        return JsonResponse({
            'success': False,
            'error': 'PDF generation library not available. Please install reportlab.'
        }, status=500)
    except Exception as e:
        logger.error(f"Error generating PDF for note {note_id}: {e}")
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while generating the PDF'
        }, status=500)


@login_required
@require_POST
def set_advanced_summary(request, note_id):
    """Set the advanced summary flag for a research note"""
    try:
        note = get_object_or_404(ResearchNote, id=note_id)

        # Toggle the advanced summary flag
        note.is_advanced_summary = not note.is_advanced_summary
        note.save(update_fields=['is_advanced_summary'])

        return JsonResponse({
            'success': True,
            'is_advanced_summary': note.is_advanced_summary,
            'message': f'Advanced summary {"enabled" if note.is_advanced_summary else "disabled"} for this report'
        })

    except Exception as e:
        logger.error(f"Error setting advanced summary for note {note_id}: {e}")
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while updating the advanced summary flag'
        }, status=500)


class AdvancedSummariesView(LoginRequiredMixin, TemplateView):
    template_name = 'research_summaries/advanced_summaries.html'
    login_url = '/accounts/login/'

    def get_context_data(self, **kwargs):
        from django.utils import timezone
        from datetime import timedelta
        context = super().get_context_data(**kwargs)

        # Get user's last read time for advanced summaries
        user_profile = self.request.user.profile
        if user_profile.last_read_time_advanced:
            default_datetime = user_profile.last_read_time_advanced
        else:
            default_datetime = timezone.now() - timedelta(hours=24)

        # Get query parameters for filtering and search
        source_filter = self.request.GET.get('source', '')
        search_query = self.request.GET.get('search', '')
        datetime_filter = self.request.GET.get('datetime', '')

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
                else:
                    filter_datetime = timezone.make_aware(filter_datetime) if timezone.is_naive(filter_datetime) else filter_datetime
            except:
                filter_datetime = default_datetime
        else:
            filter_datetime = default_datetime

        # Build queryset - Filter for status 4 instead of 3
        queryset = ResearchNote.objects.filter(status=4).order_by('-file_summary_time')

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

        # Group the results
        from collections import defaultdict, OrderedDict

        # Get all results for grouping (limit to reasonable number for performance)
        all_results = list(queryset[:400])  # Limit to 200 most recent results

        # Separate reports with tickers from those without
        ticker_groups = defaultdict(list)
        report_type_groups = defaultdict(list)

        for note in all_results:
            if note.parsed_ticker:
                ticker_groups[note.parsed_ticker].append(note)
            else:
                report_type = note.report_type or "Uncategorized"
                report_type_groups[report_type].append(note)

        # Sort ticker groups alphabetically and sort reports within each group by summary time
        sorted_ticker_groups = OrderedDict()
        for ticker in sorted(ticker_groups.keys()):
            sorted_ticker_groups[ticker] = sorted(
                ticker_groups[ticker],
                key=lambda x: (x.source or '', x.raw_title or '')
            )

        # Sort report type groups alphabetically and sort reports within each group by summary time
        sorted_report_type_groups = OrderedDict()
        for report_type in sorted(report_type_groups.keys()):
            sorted_report_type_groups[report_type] = sorted(
                report_type_groups[report_type],
                key=lambda x: (x.source or '', x.raw_title or '')
            )

        # Calculate total results
        total_results = len(all_results)
        total_available = queryset.count()

        # Simple result info
        results_info = {
            'showing_count': total_results,
            'total_available': total_available,
            'limited': total_results < total_available
        }

        # Get status counts for dashboard
        status_counts = {
            'total': ResearchNote.objects.count(),
            'not_downloaded': ResearchNote.objects.filter(status=0).count(),
            'downloaded': ResearchNote.objects.filter(status=1).count(),
            'preprocessed': ResearchNote.objects.filter(status=2).count(),
            'summarized': ResearchNote.objects.filter(status=3).count(),
            'advanced': ResearchNote.objects.filter(status=4).count(),
            'filtered_count': total_results,
        }

        # Get unique sources for filter dropdown (from advanced notes only)
        sources = ResearchNote.objects.filter(status=4).values_list('source', flat=True).exclude(
            source__isnull=True).exclude(source='').distinct().order_by('source')

        # Recent activity - show recent advanced summaries
        recent_summaries = ResearchNote.objects.filter(status=4).order_by('-file_summary_time')[:5]

        # Get latest report time from all results for "Mark as Read" functionality
        latest_report_time = None
        if all_results:
            latest_report_time = max(
                note.file_summary_time for note in all_results
                if note.file_summary_time
            )

        # Format datetime for HTML input
        formatted_datetime = filter_datetime.strftime('%Y-%m-%dT%H:%M') if filter_datetime else ''

        context.update({
            'ticker_groups': sorted_ticker_groups,
            'report_type_groups': sorted_report_type_groups,
            'results_info': results_info,
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
            'user_last_read_time': user_profile.last_read_time_advanced,
            'is_advanced': True,  # Flag to identify this is advanced view
        })

        return context


@login_required
def mark_as_read_advanced(request):
    """AJAX endpoint to update user's last_read_time_advanced"""
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
                    # Add 59 seconds to the latest report time
                    new_last_read_time = latest_report_time + timedelta(seconds=59)

                    # Update user's profile
                    user_profile = request.user.profile
                    user_profile.last_read_time_advanced = new_last_read_time
                    user_profile.save()

                    return JsonResponse({
                        'success': True,
                        'new_last_read_time': new_last_read_time.isoformat(),
                        'message': f'Advanced summaries marked as read up to {new_last_read_time.strftime("%B %d, %Y at %I:%M %p")}'
                    })

            return JsonResponse({'success': False, 'message': 'Invalid datetime provided'})

        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    return JsonResponse({'success': False, 'message': 'Invalid request method'})


class ResearchNotePersistenceView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    """View for managing ResearchNote persistence status"""
    template_name = 'research_summaries/manage_persistence.html'
    login_url = '/accounts/login/'
    permission_required = 'accounts.can_view_research_summaries'

    def get_context_data(self, **kwargs):
        import json
        from django.core.serializers.json import DjangoJSONEncoder

        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Manage Research Note Persistence'

        # Get only research notes that have been uploaded to OpenAI
        research_notes = ResearchNote.objects.filter(
            openai_file_id__isnull=False
        ).exclude(
            openai_file_id__exact=''
        ).select_related().order_by('-publication_date', '-file_summary_time')

        # Process notes to include vector group information
        notes_data = []
        for note in research_notes:
            # Get all vector group IDs for this note
            vector_ids = set()

            # Add the note's own vector_group_id
            if note.vector_group_id:
                vector_ids.add(note.vector_group_id)

            # Get vector IDs from StockTicker mapping
            if note.parsed_ticker:
                ticker_vector_ids = list(StockTicker.objects.filter(
                    main_ticker=note.parsed_ticker
                ).values_list('vector_id', flat=True))
                vector_ids.update(ticker_vector_ids)

            notes_data.append({
                'id': note.id,
                'raw_title': note.raw_title or 'Untitled',
                'source': note.source or '-',
                'publication_date': note.publication_date.isoformat() if note.publication_date else None,
                'parsed_ticker': note.parsed_ticker or '-',
                'report_type': note.report_type or '-',
                'vector_group_ids': sorted(list(vector_ids)),
                'is_persistent_document': note.is_persistent_document,
            })

        # Properly serialize to JSON using DjangoJSONEncoder
        context['research_notes_json'] = json.dumps(notes_data, cls=DjangoJSONEncoder)
        context['total_count'] = len(notes_data)

        # Get unique values for filters
        context['unique_sources'] = sorted(list(set(n['source'] for n in notes_data if n['source'] != '-')))
        context['unique_tickers'] = sorted(
            list(set(n['parsed_ticker'] for n in notes_data if n['parsed_ticker'] != '-')))
        context['unique_report_types'] = sorted(
            list(set(n['report_type'] for n in notes_data if n['report_type'] != '-')))

        return context


@login_required
@permission_required('accounts.can_view_research_summaries', raise_exception=True)
@require_http_methods(["POST"])
def api_update_persistence_status(request):
    """API endpoint to update persistence status for multiple notes"""
    try:
        data = json.loads(request.body)
        note_ids = data.get('note_ids', [])
        is_persistent = data.get('is_persistent', False)

        if not note_ids:
            return JsonResponse({
                'success': False,
                'error': 'No note IDs provided'
            }, status=400)

        # Validate note IDs are integers
        try:
            note_ids = [int(note_id) for note_id in note_ids]
        except (ValueError, TypeError):
            return JsonResponse({
                'success': False,
                'error': 'Invalid note ID format'
            }, status=400)

        # Update the persistence status
        updated_count = ResearchNote.objects.filter(
            id__in=note_ids,
            openai_file_id__isnull=False
        ).update(
            is_persistent_document=is_persistent
        )

        return JsonResponse({
            'success': True,
            'updated_count': updated_count,
            'message': f'Successfully updated {updated_count} research notes'
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        logger.error(f"Error updating persistence status: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@permission_required('accounts.can_view_research_summaries', raise_exception=True)
@require_http_methods(["GET"])
def api_research_notes_data(request):
    """API endpoint to get filtered research notes data"""
    try:
        # Get filter parameters
        search = request.GET.get('search', '')
        ticker = request.GET.get('ticker', '')
        source = request.GET.get('source', '')
        report_type = request.GET.get('report_type', '')
        is_persistent = request.GET.get('is_persistent', '')

        # Build query
        notes = ResearchNote.objects.filter(openai_file_id__isnull=False)

        if search:
            notes = notes.filter(
                Q(raw_title__icontains=search) |
                Q(source__icontains=search) |
                Q(parsed_ticker__icontains=search) |
                Q(report_type__icontains=search)
            )

        if ticker:
            notes = notes.filter(parsed_ticker__iexact=ticker)

        if source:
            notes = notes.filter(source__icontains=source)

        if report_type:
            notes = notes.filter(report_type__icontains=report_type)

        if is_persistent != '':
            notes = notes.filter(is_persistent_document=(is_persistent == 'true'))

        # Get data
        notes_data = []
        for note in notes.select_related():
            # Get vector IDs
            vector_ids = set()
            if note.vector_group_id:
                vector_ids.add(note.vector_group_id)

            if note.parsed_ticker:
                ticker_vector_ids = StockTicker.objects.filter(
                    main_ticker=note.parsed_ticker
                ).values_list('vector_id', flat=True)
                vector_ids.update(ticker_vector_ids)

            notes_data.append({
                'id': note.id,
                'raw_title': note.raw_title or 'Untitled',
                'source': note.source or '-',
                'publication_date': note.publication_date.isoformat() if note.publication_date else None,
                'parsed_ticker': note.parsed_ticker or '-',
                'report_type': note.report_type or '-',
                'vector_group_ids': sorted(list(vector_ids)),
                'is_persistent_document': note.is_persistent_document,
            })

        return JsonResponse({'notes': notes_data})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)