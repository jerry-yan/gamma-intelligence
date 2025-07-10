# agents/views.py
import json
import logging
import pandas as pd
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import FormView, TemplateView
from django.utils import timezone
from django.urls import reverse_lazy
from django.db import transaction
from .models import KnowledgeBase, ChatSession, ChatMessage, StockTicker
from research_summaries.openai_utils import get_openai_client
from .forms import ExcelUploadForm

logger = logging.getLogger(__name__)


class AgentView(LoginRequiredMixin, TemplateView):
    """Main chatbot interface view"""
    template_name = 'agents/chat.html'
    login_url = '/accounts/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['knowledge_bases'] = KnowledgeBase.objects.filter(is_active=True)
        context['user'] = self.request.user
        return context


@login_required
@require_http_methods(["GET"])
def api_knowledge_bases(request):
    """API endpoint to get available knowledge bases"""
    try:
        knowledge_bases = KnowledgeBase.objects.filter(is_active=True).values(
            'id', 'display_name', 'description', 'name', 'vector_group_id'
        )
        return JsonResponse({
            'success': True,
            'knowledge_bases': list(knowledge_bases)
        })
    except Exception as e:
        logger.error(f"Error fetching knowledge bases: {e}")
        return JsonResponse({'success': False, 'error': 'Failed to load knowledge bases'}, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_create_session(request):
    """Create a new chat session"""
    try:
        # Create session without knowledge base
        session = ChatSession.objects.create(user=request.user)

        logger.info(f"Created new chat session {session.session_id} for user {request.user.username}")

        return JsonResponse({
            'success': True,
            'session_id': str(session.session_id),
            'created_at': session.created_at.isoformat()
        })

    except Exception as e:
        logger.error(f"Error creating session: {e}")
        return JsonResponse({'success': False, 'error': 'Failed to create session'}, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_chat_stream(request):
    """Handle chat messages and stream responses using SSE"""
    try:
        data = json.loads(request.body)
        message = data.get('message', '').strip()
        session_id = data.get('session_id')
        knowledge_base_id = data.get('knowledge_base_id')  # Optional

        if not message:
            return JsonResponse({'error': 'Message is required'}, status=400)

        if not session_id:
            return JsonResponse({'error': 'Session ID is required'}, status=400)

        # Get session and verify ownership
        try:
            session = ChatSession.objects.get(
                session_id=session_id,
                user=request.user
            )
        except ChatSession.DoesNotExist:
            return JsonResponse({'error': 'Session not found or unauthorized'}, status=404)

        # Update last activity
        session.last_activity = timezone.now()
        session.save(update_fields=['last_activity'])

        # Get knowledge base if specified
        knowledge_base = None
        if knowledge_base_id:
            try:
                knowledge_base = KnowledgeBase.objects.get(id=knowledge_base_id, is_active=True)
                logger.info(
                    f"Using knowledge base: {knowledge_base.display_name} (Group {knowledge_base.vector_group_id})")
            except KnowledgeBase.DoesNotExist:
                return JsonResponse({'error': 'Knowledge base not found'}, status=404)

        # Save user message with optional knowledge base
        user_message = ChatMessage.objects.create(
            session=session,
            role='user',
            content=message,
            knowledge_base=knowledge_base
        )

        # Generate title from first message if needed
        if not session.title:
            session.generate_title()

        def event_stream():
            """Generate SSE events for streaming response"""
            try:
                # Get OpenAI client
                client = get_openai_client()

                # Build parameters for Responses API
                stream_params = {
                    # "model": "gpt-4o-mini",
                    # "model": "gpt-4.1-mini-2025-04-14",
                    "model": "o3-2025-04-16",
                    # "model": "o3-mini-2025-01-31",
                    "input": message,
                    "stream": True,
                    # "temperature": 0.7,
                }

                # Add tools only if knowledge base is specified
                if knowledge_base:
                    stream_params["tools"] = [{
                        "type": "file_search",
                        "vector_store_ids": [knowledge_base.vector_store_id],
                        "max_num_results": 5,
                    }]
                    yield f"data: {json.dumps({'type': 'info', 'message': f'Using knowledge base: {knowledge_base.display_name}'})}\n\n"

                # Add response_id if continuing conversation
                if session.response_id:
                    stream_params["previous_response_id"] = session.response_id

                # Stream the response
                response = client.responses.create(**stream_params)

                assistant_message = ""
                response_id = None
                tool_uses = []
                citations = []

                for chunk in response:
                    # Capture response ID
                    if hasattr(chunk, 'response') and hasattr(chunk.response, 'id'):
                        response_id = chunk.response.id

                    # Handle different event types from Responses API
                    if hasattr(chunk, 'type'):
                        # Handle text delta events
                        if chunk.type == 'response.output_text.delta' and hasattr(chunk, 'delta'):
                            assistant_message += chunk.delta
                            yield f"data: {json.dumps({'type': 'content', 'content': chunk.delta})}\n\n"

                        # Handle tool use events (file search)
                        elif chunk.type == 'response.tool_call.delta' and hasattr(chunk, 'tool_call'):
                            if chunk.tool_call.type == 'file_search':
                                tool_uses.append('file_search')
                                yield f"data: {json.dumps({'type': 'tool_use', 'tool': 'file_search', 'status': 'searching'})}\n\n"

                        # Handle citation events if available
                        elif chunk.type == 'response.citation' and hasattr(chunk, 'citation'):
                            citations.append({
                                'file_id': chunk.citation.file_id,
                                'quote': chunk.citation.quote
                            })

                # Update session with response ID
                if response_id and response_id != session.response_id:
                    session.response_id = response_id
                    session.save(update_fields=['response_id'])
                    logger.info(f"Updated session {session.session_id} with response_id: {response_id}")

                # Save assistant message with knowledge base reference
                if assistant_message:
                    metadata = {
                        'tool_uses': tool_uses,
                        'response_id': response_id
                    }
                    if citations:
                        metadata['citations'] = citations

                    ChatMessage.objects.create(
                        session=session,
                        role='assistant',
                        content=assistant_message,
                        knowledge_base=knowledge_base,  # Store which KB was used (if any)
                        metadata=metadata
                    )

                # Send completion signal
                yield f"data: {json.dumps({'type': 'done'})}\n\n"

            except Exception as e:
                logger.error(f"Streaming error in session {session.session_id}: {str(e)}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'error': 'An error occurred while generating the response.'})}\n\n"

        # Return streaming response
        response = StreamingHttpResponse(
            event_stream(),
            content_type='text/event-stream'
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON in request body'}, status=400)
    except Exception as e:
        logger.error(f"Chat error: {str(e)}", exc_info=True)
        return JsonResponse({'error': 'An unexpected error occurred'}, status=500)


@login_required
@require_http_methods(["GET"])
def api_session_history(request, session_id):
    """Get chat history for a session"""
    try:
        session = ChatSession.objects.get(
            session_id=session_id,
            user=request.user
        )

        messages = []
        for msg in session.messages.exclude(role='system').select_related('knowledge_base').order_by('created_at'):
            message_data = {
                'id': msg.id,
                'role': msg.role,
                'content': msg.content,
                'created_at': msg.created_at.isoformat(),
                'metadata': msg.metadata or {}
            }

            # Include knowledge base info if used
            if msg.knowledge_base:
                message_data['knowledge_base'] = {
                    'id': msg.knowledge_base.id,
                    'name': msg.knowledge_base.display_name,
                    'vector_group_id': msg.knowledge_base.vector_group_id
                }

            messages.append(message_data)

        return JsonResponse({
            'success': True,
            'session_id': str(session.session_id),
            'title': session.title or 'New Chat',
            'messages': messages,
            'created_at': session.created_at.isoformat(),
            'response_id': session.response_id
        })

    except ChatSession.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Session not found'}, status=404)
    except Exception as e:
        logger.error(f"Error loading session history: {e}")
        return JsonResponse({'success': False, 'error': 'Failed to load session history'}, status=500)


@login_required
@require_http_methods(["GET"])
def api_user_sessions(request):
    """Get all sessions for the current user"""
    try:
        sessions = ChatSession.objects.filter(
            user=request.user
        ).order_by('-last_activity')[:30]  # Increased from 20 to 30

        session_list = []
        for session in sessions:
            # Get last assistant message for preview
            last_message = session.messages.filter(role='assistant').last()
            if not last_message:
                last_message = session.messages.filter(role='user').last()

            session_list.append({
                'session_id': str(session.session_id),
                'title': session.title or 'New Chat',
                'last_activity': session.last_activity.isoformat(),
                'last_message': last_message.content[:100] if last_message else None,
                'message_count': session.messages.exclude(role='system').count(),
                'has_response_id': bool(session.response_id)
            })

        return JsonResponse({
            'success': True,
            'sessions': session_list
        })

    except Exception as e:
        logger.error(f"Error loading user sessions: {e}")
        return JsonResponse({'success': False, 'error': 'Failed to load sessions'}, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_delete_message(request, message_id):
    """Delete a single message and all subsequent messages in the session"""
    try:
        message = ChatMessage.objects.get(
            id=message_id,
            session__user=request.user
        )

        # Store session for response
        session = message.session
        message_timestamp = message.created_at

        # Delete this message and all subsequent messages
        deleted_count = session.messages.filter(created_at__gte=message_timestamp).delete()[0]

        logger.info(f"Deleted {deleted_count} messages from session {session.session_id}")

        # Clear response_id since conversation history changed
        session.response_id = ""

        # Regenerate title if we deleted the first user message
        first_user_message = session.messages.filter(role='user').first()
        if not first_user_message:
            session.title = ""

        session.save(update_fields=['response_id', 'title'])

        return JsonResponse({
            'success': True,
            'deleted_count': deleted_count
        })

    except ChatMessage.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Message not found'}, status=404)
    except Exception as e:
        logger.error(f"Error deleting message: {e}")
        return JsonResponse({'success': False, 'error': 'Failed to delete message'}, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_clear_session(request, session_id):
    """Clear all messages in a session"""
    try:
        session = ChatSession.objects.get(
            session_id=session_id,
            user=request.user
        )

        # Delete all messages in the session
        deleted_count = session.messages.all().delete()[0]

        # Reset response_id and title
        session.response_id = ""
        session.title = ""
        session.save(update_fields=['response_id', 'title'])

        logger.info(f"Cleared {deleted_count} messages from session {session.session_id}")

        return JsonResponse({
            'success': True,
            'deleted_count': deleted_count
        })

    except ChatSession.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Session not found'}, status=404)
    except Exception as e:
        logger.error(f"Error clearing session: {e}")
        return JsonResponse({'success': False, 'error': 'Failed to clear session'}, status=500)


@login_required
@csrf_exempt
@require_http_methods(["DELETE"])
def api_delete_session(request, session_id):
    """Delete an entire session"""
    try:
        session = ChatSession.objects.get(
            session_id=session_id,
            user=request.user
        )

        session.delete()
        logger.info(f"Deleted session {session_id} for user {request.user.username}")

        return JsonResponse({'success': True})

    except ChatSession.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Session not found'}, status=404)
    except Exception as e:
        logger.error(f"Error deleting session: {e}")
        return JsonResponse({'success': False, 'error': 'Failed to delete session'}, status=500)


class StockTickerUploadView(LoginRequiredMixin, FormView):
    template_name = 'agents/upload_stocks.html'
    form_class = ExcelUploadForm
    success_url = reverse_lazy('agents:stock_ticker_list')  # Update this to your list view

    def form_valid(self, form):
        excel_file = form.cleaned_data['excel_file']

        try:
            # Read the Excel file
            df = pd.read_excel(excel_file, engine='openpyxl')

            # Validate required columns
            required_columns = ['Main Ticker', 'Full Ticker', 'Company Name',
                                'Industry', 'Subindustry', 'Vector ID']

            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                messages.error(self.request, f"Missing columns: {', '.join(missing_columns)}")
                return self.form_invalid(form)

            # Clean the data
            df = df.dropna(subset=required_columns)

            # Check for duplicates in the file
            duplicates = df[df.duplicated(subset=['Main Ticker', 'Vector ID'], keep=False)]
            if len(duplicates) > 0:
                messages.warning(
                    self.request,
                    f"Found {len(duplicates)} rows with duplicate Main Ticker + Vector ID. "
                    "Keeping only the first occurrence of each duplicate."
                )
                # Remove duplicates, keeping the first occurrence
                df = df.drop_duplicates(subset=['Main Ticker', 'Vector ID'], keep='first')

            # Import data in bulk
            stock_tickers = []
            with transaction.atomic():
                # Optional: Clear existing data
                if form.cleaned_data.get('clear_existing', False):
                    StockTicker.objects.all().delete()

                # Create a dictionary to track duplicates within our list
                seen = set()
                skipped = 0

                for _, row in df.iterrows():
                    ticker_key = (str(row['Main Ticker']).strip(), int(row['Vector ID']))

                    # Skip if we've already processed this combination
                    if ticker_key in seen:
                        skipped += 1
                        continue

                    seen.add(ticker_key)

                    stock_ticker = StockTicker(
                        main_ticker=str(row['Main Ticker']).strip(),
                        full_ticker=str(row['Full Ticker']).strip(),
                        company_name=str(row['Company Name']).strip(),
                        industry=str(row['Industry']).strip(),
                        sub_industry=str(row['Subindustry']).strip(),
                        vector_id=int(row['Vector ID'])
                    )
                    stock_tickers.append(stock_ticker)

                # Bulk create for better performance
                # ignore_conflicts will skip duplicates already in the database
                created = StockTicker.objects.bulk_create(stock_tickers, ignore_conflicts=True)

            messages.success(
                self.request,
                f"Successfully processed {len(stock_tickers)} unique stock tickers! "
                f"({len(created)} new records created)"
            )
            return super().form_valid(form)

        except Exception as e:
            messages.error(self.request, f"Error processing file: {str(e)}")
            return self.form_invalid(form)