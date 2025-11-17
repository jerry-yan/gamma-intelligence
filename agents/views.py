# agents/views.py
import json
import logging
import pandas as pd
from datetime import date, timedelta
import threading
import time
from queue import Queue, Empty
from django.http import JsonResponse, StreamingHttpResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.views.generic import FormView, TemplateView
from django.utils import timezone
from django.urls import reverse_lazy
from django.db import transaction
from .models import KnowledgeBase, ChatSession, ChatMessage, StockTicker, Prompt
from documents.models import Document
from research_summaries.openai_utils import get_openai_client
from .forms import ExcelUploadForm
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_LEFT, TA_CENTER
import html
import re
import hashlib
import tempfile
import os

logger = logging.getLogger(__name__)

AVAILABLE_MODELS = {
    'o3': {
        'api_name': 'o3-2025-04-16',
        'display_name': 'o3',
        'description': 'Latest O3 model with advanced reasoning capabilities'
    },
    'gpt-4.1': {
        'api_name': 'gpt-4.1-2025-04-14',
        'display_name': 'GPT-4.1',
        'description': 'Standard GPT-4.1 model for faster responses'
    },
    'gpt-4.1-mini': {
        'api_name': 'gpt-4.1-mini-2025-04-14',
        'display_name': 'GPT-4.1 Mini',
        'description': 'Efficient GPT-4.1-mini model for faster responses'
    },
    'gpt-5': {
        'api_name': 'gpt-5-2025-08-07',
        'display_name': 'GPT-5',
        'description': 'Standard GPT-5 model'
    },
    'gpt-5.1': {
        'api_name': 'gpt-5.1-2025-11-13',
        'display_name': 'GPT-5.1',
        'description': 'Standard GPT-5.1 model'
    },
    'gpt-5-mini': {
        'api_name': 'gpt-5-mini-2025-08-07',
        'display_name': 'GPT-5 Mini',
        'description': 'Efficient GPT-5-mini model for faster responses'
    },
    'gpt-4o-mini': {
        'api_name': 'gpt-4o-mini-2024-07-18',
        'display_name': 'GPT-4o Mini',
        'description': 'Fastest GPT-4o Mini model'
    },
}


class AgentView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    """Main chatbot interface view"""
    template_name = 'agents/chat.html'
    login_url = '/accounts/login/'
    permission_required = 'accounts.can_view_agents'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['knowledge_bases'] = KnowledgeBase.objects.filter(is_active=True)
        context['user'] = self.request.user
        user_prompts = Prompt.objects.filter(user=self.request.user).values('id', 'name', 'prompt')
        context['user_prompts'] = list(user_prompts)
        # Define privileged users who get access to all models
        privileged_users = ['yuhaoyan', 'dhoang', 'dbastien']

        # Check if current user is privileged
        if self.request.user.username in privileged_users:
            # Show all available models
            available_models = [
                {
                    'key': k,
                    'display_name': v['display_name'],
                    'description': v['description']
                }
                for k, v in AVAILABLE_MODELS.items()
            ]
        else:
            # Show only o3 and gpt-4o-mini for regular users
            unrestricted_models = ['o3', 'gpt-4o-mini']
            available_models = [
                {
                    'key': k,
                    'display_name': v['display_name'],
                    'description': v['description']
                }
                for k, v in AVAILABLE_MODELS.items()
                if k in unrestricted_models
            ]

        context['available_models'] = available_models
        return context


def get_api_model_name(model_key):
    """Get the API model name from the model key"""
    return AVAILABLE_MODELS.get(model_key, AVAILABLE_MODELS['o3'])['api_name']


def get_model_display_name(model_key):
    """Get the display name from the model key"""
    return AVAILABLE_MODELS.get(model_key, AVAILABLE_MODELS['o3'])['display_name']


@login_required
@permission_required('accounts.can_view_agents', raise_exception=True)
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
        selected_model = data.get('model', 'o3')

        if not message:
            return JsonResponse({'error': 'Message is required'}, status=400)

        if not session_id:
            return JsonResponse({'error': 'Session ID is required'}, status=400)

        # Map the selected model to the actual API model name
        api_model = AVAILABLE_MODELS.get(selected_model, 'o3').get('api_name')
        logger.info(f"Using model: {selected_model} -> {api_model}")

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
            knowledge_base=knowledge_base,
            metadata={'model_used': api_model}
        )

        # Generate title from first message if needed
        if not session.title:
            session.generate_title()

        def event_stream():
            """Generate SSE events for streaming response"""
            # Variables to accumulate the response
            assistant_message = ""
            response_id = None
            tool_uses = []
            citations = []
            last_save_length = 0
            assistant_msg_obj = None
            chunk_count = 0
            stream_start_time = timezone.now()

            logger.info(f"[STREAM START] Session {session.session_id} - User: {request.user.username}")

            try:
                # Get OpenAI client
                client = get_openai_client()

                today_str = date.today().strftime("%B %d, %Y")

                instructions = (
                    "You are a veteran portfolio manager with 20 years experience, you now write investment commentaries that result in people making huge sums of money with your timely and accurate insights. \n"
                    "You are instrumental to helping your clients find investment opportunities and avoid blowups. \n"
                    f"Today's date is {today_str}."
                )

                # Build parameters for Responses API
                stream_params = {
                    "model": api_model,
                    "instructions": instructions,
                    "input": message,
                    "stream": True,
                }

                # Add tools only if knowledge base is specified
                if knowledge_base:
                    stream_params["tools"] = [{
                        "type": "file_search",
                        "vector_store_ids": [knowledge_base.vector_store_id],
                        "max_num_results": 50,
                    }]
                    yield f"data: {json.dumps({'type': 'info', 'message': f'Using knowledge base: {knowledge_base.display_name}'})}\n\n"

                # Add response_id if continuing conversation
                if session.response_id:
                    stream_params["previous_response_id"] = session.response_id

                logger.info(f"[OPENAI REQUEST] Session {session.session_id} - Starting OpenAI stream")

                # Stream the response
                response = client.responses.create(**stream_params)

                chunk_queue = Queue()

                def response_reader():
                    try:
                        for chunk in response:
                            chunk_queue.put(('chunk', chunk))
                    except Exception as stream_error:
                        chunk_queue.put(('error', stream_error))
                    finally:
                        chunk_queue.put(('done', None))

                threading.Thread(target=response_reader, daemon=True).start()

                heartbeat_interval = 5  # seconds
                heartbeat_max_duration = timedelta(minutes=5).total_seconds()
                last_message_time = time.monotonic()

                streaming_active = True
                while streaming_active:
                    try:
                        item_type, payload = chunk_queue.get(timeout=heartbeat_interval)
                    except Empty:
                        inactivity = time.monotonic() - last_message_time
                        if inactivity >= heartbeat_max_duration:
                            logger.info(
                                f"[HEARTBEAT TIMEOUT] Session {session.session_id} - No chunks for {heartbeat_max_duration} seconds")
                            raise TimeoutError("No response received from OpenAI within 5 minutes.")
                        logger.info(
                            f"[HEARTBEAT] Session {session.session_id} - Sent heartbeat after {inactivity:.2f}s of inactivity")
                        yield f"data: {json.dumps({'type': 'heartbeat', 'status': 'waiting'})}\n\n"
                        continue

                    if item_type == 'done':
                        break

                    if item_type == 'error':
                        raise payload

                    chunk = payload
                    last_message_time = time.monotonic()
                    chunk_count += 1

                    # Todo: Uncomment this and debug gpt-5 timeout
                    # logger.info(f"[CHUNK]: {chunk}")

                    # Log every 10th chunk to avoid log spam
                    if chunk_count % 100 == 0:
                        logger.info(
                            f"[CHUNK {chunk_count}] Session {session.session_id} - Message length: {len(assistant_message)}")

                    # Check if client is still connected
                    try:
                        # Capture response ID
                        if hasattr(chunk, 'response') and hasattr(chunk.response, 'id'):
                            response_id = chunk.response.id
                            logger.info(f"[RESPONSE ID] Session {session.session_id} - Got response_id: {response_id}")

                        # Handle different event types from Responses API
                        if hasattr(chunk, 'type'):
                            # Log specific event types
                            if chunk.type in ['response.output_text.delta', 'response.done',
                                              'response.tool_call.delta']:
                                logger.debug(f"[EVENT] Session {session.session_id} - Type: {chunk.type}")

                            # Handle text delta events
                            if chunk.type == 'response.output_text.delta' and hasattr(chunk, 'delta'):
                                assistant_message += chunk.delta
                                yield f"data: {json.dumps({'type': 'content', 'content': chunk.delta})}\n\n"

                                # Periodically save the message in case of disconnection
                                # if len(assistant_message) - last_save_length > 500:  # Save every 500 chars
                                #     logger.info(
                                #         f"[PERIODIC SAVE] Session {session.session_id} - Saving at {len(assistant_message)} chars")

                            # Handle tool use events (file search)
                            elif chunk.type == 'response.tool_call.delta' and hasattr(chunk, 'tool_call'):
                                if chunk.tool_call.type == 'file_search':
                                    tool_uses.append('file_search')
                                    logger.info(f"[TOOL USE] Session {session.session_id} - File search initiated")
                                    yield f"data: {json.dumps({'type': 'tool_use', 'tool': 'file_search', 'status': 'searching'})}\n\n"

                            # Handle citation events if available
                            elif chunk.type == 'response.citation' and hasattr(chunk, 'citation'):
                                citations.append({
                                    'file_id': chunk.citation.file_id,
                                    'quote': chunk.citation.quote
                                })

                            # === REASONING EVENTS (keep connection alive) ===
                            elif chunk.type == 'response.reasoning_summary_part.added':
                                yield f"data: {json.dumps({'type': 'reasoning', 'status': 'summary_part_added'})}\n\n"

                            elif chunk.type == 'response.reasoning_summary_part.done':
                                yield f"data: {json.dumps({'type': 'reasoning', 'status': 'summary_part_done'})}\n\n"

                            elif chunk.type == 'response.reasoning_summary_text.delta':
                                yield f"data: {json.dumps({'type': 'reasoning', 'status': 'summary_text_delta'})}\n\n"

                            elif chunk.type == 'response.reasoning_summary_text.done':
                                yield f"data: {json.dumps({'type': 'reasoning', 'status': 'summary_text_done'})}\n\n"

                            elif chunk.type == 'response.reasoning.delta':
                                if chunk_count % 5 == 0:  # Log every 5th reasoning event
                                    logger.info(f"[REASONING] Session {session.session_id} - Reasoning in progress")
                                yield f"data: {json.dumps({'type': 'reasoning', 'status': 'reasoning_delta'})}\n\n"

                            elif chunk.type == 'response.reasoning.done':
                                logger.info(f"[REASONING DONE] Session {session.session_id}")
                                yield f"data: {json.dumps({'type': 'reasoning', 'status': 'reasoning_done'})}\n\n"

                            elif chunk.type == 'response.reasoning_summary.delta':
                                yield f"data: {json.dumps({'type': 'reasoning', 'status': 'reasoning_summary_delta'})}\n\n"

                            elif chunk.type == 'response.reasoning_summary.done':
                                yield f"data: {json.dumps({'type': 'reasoning', 'status': 'reasoning_summary_done'})}\n\n"

                            # === OUTPUT ITEM EVENTS ===
                            elif chunk.type == 'response.output_item.added':
                                yield f"data: {json.dumps({'type': 'output', 'status': 'item_added'})}\n\n"

                            elif chunk.type == 'response.output_item.done':
                                yield f"data: {json.dumps({'type': 'output', 'status': 'item_done'})}\n\n"

                            # === CONTENT PART EVENTS ===
                            elif chunk.type == 'response.content_part.added':
                                yield f"data: {json.dumps({'type': 'content_part', 'status': 'added'})}\n\n"

                            elif chunk.type == 'response.content_part.done':
                                yield f"data: {json.dumps({'type': 'content_part', 'status': 'done'})}\n\n"

                            # === TOOL CALL DELTA EVENTS (updated) ===
                            elif chunk.type == 'response.output_tool_calls.delta':
                                if hasattr(chunk, 'delta') and hasattr(chunk.delta, 'tool_calls'):
                                    for tool_call in chunk.delta.tool_calls:
                                        if tool_call.type == 'file_search':
                                            tool_uses.append('file_search')
                                            yield f"data: {json.dumps({'type': 'tool_use', 'tool': 'file_search', 'status': 'searching'})}\n\n"

                    except Exception as e:
                        logger.warning(
                            f"[CLIENT DISCONNECT] Session {session.session_id} - Chunk {chunk_count} - Error: {str(e)}")
                        logger.warning(
                            f"[DISCONNECT STATS] Message length: {len(assistant_message)}, Chunks: {chunk_count}")
                        # Continue processing even if client disconnected
                        continue

                logger.info(
                    f"[STREAM COMPLETE] Session {session.session_id} - Total chunks: {chunk_count}, Message length: {len(assistant_message)}")

                # Update session with response ID
                if response_id and response_id != session.response_id:
                    session.response_id = response_id
                    session.save(update_fields=['response_id'])
                    logger.info(f"[SESSION UPDATE] Session {session.session_id} - Updated response_id: {response_id}")

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
                logger.info(f"[DONE SENT] Session {session.session_id}")

            except Exception as e:
                logger.error(f"[STREAM ERROR] Session {session.session_id} - Error: {str(e)}", exc_info=True)
                logger.error(f"[ERROR STATS] Chunks: {chunk_count}, Message length: {len(assistant_message)}")

                # Save whatever we have so far
                if assistant_message:
                    try:
                        if not assistant_msg_obj:
                            ChatMessage.objects.create(
                                session=session,
                                role='assistant',
                                content=assistant_message + "\n\n[Response interrupted due to error]",
                                knowledge_base=knowledge_base,
                                metadata={
                                    'error': str(e),
                                    'partial': True,
                                    'response_id': response_id,
                                    'chunks_received': chunk_count,
                                    'error_time': timezone.now().isoformat()
                                }
                            )
                            logger.info(f"[ERROR SAVE] Session {session.session_id} - Saved partial message on error")
                    except Exception as save_error:
                        logger.error(
                            f"[SAVE ERROR] Session {session.session_id} - Failed to save on error: {str(save_error)}")

                yield f"data: {json.dumps({'type': 'error', 'error': 'An error occurred while generating the response.'})}\n\n"

        # Return streaming response with keep-alive headers
        response = StreamingHttpResponse(
            event_stream(),
            content_type='text/event-stream'
        )
        response['Cache-Control'] = 'no-cache'
        response['Connection'] = 'keep-alive'  # Critical for Heroku
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
    """Delete an entire chat session"""
    try:
        session = ChatSession.objects.get(
            session_id=session_id,
            user=request.user
        )
        session.delete()
        return JsonResponse({'success': True})
    except ChatSession.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Session not found'}, status=404)
    except Exception as e:
        logger.error(f"Error deleting session: {e}")
        return JsonResponse({'success': False, 'error': 'Failed to delete session'}, status=500)


@login_required
@csrf_exempt
@require_http_methods(["PATCH"])
def api_rename_session(request, session_id):
    """Rename a chat session"""
    try:
        data = json.loads(request.body)
        new_title = data.get('title', '').strip()

        if not new_title:
            return JsonResponse({'success': False, 'error': 'Title is required'}, status=400)

        session = ChatSession.objects.get(
            session_id=session_id,
            user=request.user
        )
        session.title = new_title
        session.save()

        return JsonResponse({'success': True, 'title': new_title})
    except ChatSession.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Session not found'}, status=404)
    except Exception as e:
        logger.error(f"Error renaming session: {e}")
        return JsonResponse({'success': False, 'error': 'Failed to rename session'}, status=500)


@login_required
@require_http_methods(["GET"])
def api_export_session_pdf(request, session_id):
    """Export chat session as PDF with selectable text"""
    try:
        # Get session and verify ownership
        session = ChatSession.objects.get(
            session_id=session_id,
            user=request.user
        )

        # Get all messages
        messages = session.messages.exclude(role='system').select_related('knowledge_base').order_by('created_at')

        # Create PDF buffer
        buffer = BytesIO()

        # Create the PDF object
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )

        # Container for the 'Flowable' objects
        elements = []

        # Define styles
        styles = getSampleStyleSheet()

        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#111827'),
            spaceAfter=12,
            alignment=TA_CENTER
        )

        header_style = ParagraphStyle(
            'Header',
            parent=styles['Normal'],
            fontSize=12,
            textColor=colors.HexColor('#6b7280'),
            spaceAfter=6,
            alignment=TA_CENTER
        )

        user_style = ParagraphStyle(
            'UserMessage',
            parent=styles['Normal'],
            fontSize=12,
            textColor=colors.HexColor('#2563eb'),
            spaceAfter=6,
            fontName='Helvetica-Bold'
        )

        assistant_style = ParagraphStyle(
            'AssistantMessage',
            parent=styles['Normal'],
            fontSize=12,
            textColor=colors.HexColor('#7c3aed'),
            spaceAfter=6,
            fontName='Helvetica-Bold'
        )

        content_style = ParagraphStyle(
            'MessageContent',
            parent=styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#111827'),
            spaceAfter=18,
            spaceBefore=6,
            leading=16
        )

        kb_style = ParagraphStyle(
            'KnowledgeBase',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#6b7280'),
            spaceAfter=3
        )

        # Add title
        elements.append(Paragraph("Chat Export", title_style))
        elements.append(Spacer(1, 12))

        # Add header info
        elements.append(Paragraph(f"Session: {session_id}", header_style))
        elements.append(Paragraph(f"Exported: {timezone.now().strftime('%B %d, %Y at %I:%M %p')}", header_style))
        elements.append(Paragraph(f"User: {request.user.get_full_name() or request.user.username}", header_style))
        elements.append(Spacer(1, 24))

        # Function to clean and escape HTML content
        def clean_content(content):
            # First, decode any HTML entities
            content = html.unescape(content)

            # Convert markdown-style formatting to HTML
            # Bold: **text** or __text__
            content = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', content)
            content = re.sub(r'__([^_]+)__', r'<b>\1</b>', content)

            # Italic: *text* or _text_
            content = re.sub(r'\*([^*]+)\*', r'<i>\1</i>', content)
            content = re.sub(r'(?<!\w)_([^_]+)_(?!\w)', r'<i>\1</i>', content)

            # Code blocks: ```text```
            content = re.sub(r'```([^`]+)```', r'<font name="Courier">\1</font>', content)

            # Inline code: `text`
            content = re.sub(r'`([^`]+)`', r'<font name="Courier">\1</font>', content)

            # Convert newlines to <br/> tags
            content = content.replace('\n', '<br/>')

            # Escape any remaining problematic characters for ReportLab
            content = content.replace('&', '&amp;')
            content = content.replace('<', '&lt;').replace('>', '&gt;')

            # Re-enable our formatted tags
            content = content.replace('&lt;b&gt;', '<b>').replace('&lt;/b&gt;', '</b>')
            content = content.replace('&lt;i&gt;', '<i>').replace('&lt;/i&gt;', '</i>')
            content = content.replace('&lt;br/&gt;', '<br/>')
            content = content.replace('&lt;font name="Courier"&gt;', '<font name="Courier">').replace('&lt;/font&gt;',
                                                                                                      '</font>')

            return content

        # Add messages
        for msg in messages:
            # Add role header
            if msg.role == 'user':
                elements.append(Paragraph("You", user_style))
            else:
                elements.append(Paragraph("Assistant", assistant_style))

            # Add knowledge base info if present
            if msg.knowledge_base:
                elements.append(Paragraph(f"[{msg.knowledge_base.display_name}]", kb_style))

            # Clean and add message content
            cleaned_content = clean_content(msg.content)
            try:
                elements.append(Paragraph(cleaned_content, content_style))
            except Exception as e:
                # If parsing fails, add plain text
                logger.warning(f"Failed to parse message content: {e}")
                elements.append(Paragraph(html.escape(msg.content), content_style))

            # Add a line separator
            elements.append(Spacer(1, 6))

        # Build PDF
        doc.build(elements)

        # FileResponse sets the Content-Disposition header so that browsers
        # present the option to save the file.
        buffer.seek(0)

        filename = f"chat-export-{session_id.hex[:8]}-{timezone.now().strftime('%Y%m%d')}.pdf"
        response = FileResponse(
            buffer,
            as_attachment=True,
            filename=filename,
            content_type='application/pdf'
        )

        return response

    except ChatSession.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Session not found'}, status=404)
    except Exception as e:
        logger.error(f"Error exporting session to PDF: {e}")
        return JsonResponse({'success': False, 'error': 'Failed to export session'}, status=500)


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


class AgentView2(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    """Enhanced chatbot interface view with ChatGPT-like UI"""
    template_name = 'agents/chat_v2.html'
    login_url = '/accounts/login/'
    permission_required = 'accounts.can_view_agents'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['knowledge_bases'] = KnowledgeBase.objects.filter(is_active=True)
        context['user'] = self.request.user
        # Add available models
        context['available_models'] = [
            {'id': 'o3', 'name': 'O3'},
            {'id': 'gpt-4.1', 'name': 'GPT-4.1'},
        ]
        return context


class AgentView3(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    """Main chatbot interface view"""
    template_name = 'agents/chat_v3.html'
    login_url = '/accounts/login/'
    permission_required = 'accounts.can_view_agents'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['knowledge_bases'] = KnowledgeBase.objects.filter(is_active=True)
        context['user'] = self.request.user
        user_prompts = Prompt.objects.filter(user=self.request.user).values('id', 'name', 'prompt')
        context['user_prompts'] = list(user_prompts)
        # Define privileged users who get access to all models
        privileged_users = ['yuhaoyan', 'dhoang', 'dbastien', 'dwang']

        # Check if current user is privileged
        if self.request.user.username in privileged_users:
            # Show all available models
            available_models = [
                {
                    'key': k,
                    'display_name': v['display_name'],
                    'description': v['description']
                }
                for k, v in AVAILABLE_MODELS.items()
            ]
        else:
            # Show only o3 and gpt-4o-mini for regular users
            unrestricted_models = ['o3', 'gpt-4o-mini']
            available_models = [
                {
                    'key': k,
                    'display_name': v['display_name'],
                    'description': v['description']
                }
                for k, v in AVAILABLE_MODELS.items()
                if k in unrestricted_models
            ]

        context['available_models'] = available_models
        return context

@login_required
@csrf_exempt


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_chat_stream_new(request):
    try:
        data = json.loads(request.body)
        message = data.get('message', '').strip()
        session_id = data.get('session_id')
        knowledge_base_id = data.get('knowledge_base_id')  # Optional
        selected_model = data.get('model', 'o3')
        selected_file_ids = data.get('file_ids', [])
        reasoning_effort = data.get('reasoning', 'none')

        if not message:
            return JsonResponse({'error': 'Message is required'}, status=400)

        if not session_id:
            return JsonResponse({'error': 'Session ID is required'}, status=400)

        # Map the selected model to the actual API model name
        api_model = AVAILABLE_MODELS.get(selected_model, 'o3').get('api_name')
        logger.info(f"Using model: {selected_model} -> {api_model} (Reasoning: {reasoning_effort})")

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
        ChatMessage.objects.create(
            session=session,
            role='user',
            content=message,
            knowledge_base=knowledge_base,
            metadata={
                'model_used': api_model,
                'attached_file_ids': selected_file_ids,
            }
        )

        # Generate title from first message if needed
        if not session.title:
            session.generate_title()

        def event_stream():
            """Generate SSE events for streaming response"""
            # Variables to accumulate the response
            assistant_message = ""
            response_id = None
            tool_uses = []
            citations = []
            last_save_length = 0
            assistant_msg_obj = None
            chunk_count = 0
            stream_start_time = timezone.now()

            logger.info(f"[STREAM START] Session {session.session_id} - User: {request.user.username}")

            try:
                # Get OpenAI client
                client = get_openai_client()

                today_str = date.today().strftime("%B %d, %Y")

                instructions = (
                    "You are a veteran portfolio manager with 20 years experience, you now write investment commentaries that result in people making huge sums of money with your timely and accurate insights. \n"
                    "You are instrumental to helping your clients find investment opportunities and avoid blowups. \n"
                    f"Today's date is {today_str}."
                )

                if selected_file_ids:
                    content_list = [{"type": "input_text", "text": message}]

                    for file_id in selected_file_ids:

                        file_extension = '.pdf'

                        try:
                            # Fetch the Document object
                            document = Document.objects.get(openai_file_id=file_id)

                            # Extract file extension from filename
                            filename = document.filename
                            file_extension = os.path.splitext(filename)[1].lower()

                            # Log the file type
                            logger.info(f"Processing file: {filename} (type: {file_extension}, openai_id: {file_id})")

                        except Document.DoesNotExist:
                            logger.error(f"Document with ID {file_id} not found")

                        except Exception as e:
                            logger.error(f"Error processing document {file_id}: {str(e)}")

                        if file_extension in ['.png', '.jpg', '.jpeg', '.webp', '.gif']:
                            content_list.append({"type": "input_image", "file_id": file_id})
                        else:
                            content_list.append({"type": "input_file", "file_id": file_id})

                    input_message = [
                        {
                            "role": "user",
                            "content": content_list
                        }
                    ]

                else:
                    input_message = message

                # Build parameters for Responses API
                stream_params = {
                    "model": api_model,
                    "instructions": instructions,
                    "input": input_message,
                    "stream": True,
                }

                # Add tools only if knowledge base is specified
                if knowledge_base:
                    stream_params["tools"] = [{
                        "type": "file_search",
                        "vector_store_ids": [knowledge_base.vector_store_id],
                        "max_num_results": 50,
                    }]
                    yield f"data: {json.dumps({'type': 'info', 'message': f'Using knowledge base: {knowledge_base.display_name}'})}\n\n"

                # Add response_id if continuing conversation
                if session.response_id:
                    stream_params["previous_response_id"] = session.response_id

                # Add reasoning logic
                if api_model.startswith("gpt-5") and reasoning_effort.lower() != "none":
                    stream_params["reasoning"] = {"effort": reasoning_effort}

                logger.info(f"[OPENAI REQUEST] Session {session.session_id} - Starting OpenAI stream")

                # Stream the response
                response = client.responses.create(**stream_params)

                chunk_queue = Queue()

                def response_reader():
                    try:
                        for chunk in response:
                            chunk_queue.put(('chunk', chunk))
                    except Exception as stream_error:
                        chunk_queue.put(('error', stream_error))
                    finally:
                        chunk_queue.put(('done', None))

                threading.Thread(target=response_reader, daemon=True).start()

                heartbeat_interval = 5  # seconds
                heartbeat_max_duration = timedelta(minutes=5).total_seconds()
                last_message_time = time.monotonic()

                streaming_active = True
                while streaming_active:
                    try:
                        item_type, payload = chunk_queue.get(timeout=heartbeat_interval)
                    except Empty:
                        inactivity = time.monotonic() - last_message_time
                        if inactivity >= heartbeat_max_duration:
                            logger.info(
                                f"[HEARTBEAT TIMEOUT] Session {session.session_id} - No chunks for {heartbeat_max_duration} seconds")
                            raise TimeoutError("No response received from OpenAI within 5 minutes.")
                        logger.info(
                            f"[HEARTBEAT] Session {session.session_id} - Sent heartbeat after {inactivity:.2f}s of inactivity")
                        yield f"data: {json.dumps({'type': 'heartbeat', 'status': 'waiting'})}\n\n"
                        continue

                    if item_type == 'done':
                        break

                    if item_type == 'error':
                        raise payload

                    chunk = payload
                    last_message_time = time.monotonic()
                    chunk_count += 1

                    # Todo: Uncomment this and debug gpt-5 timeout
                    # logger.info(f"[CHUNK]: {chunk}")

                    # Log every 100th chunk to avoid log spam
                    if chunk_count % 100 == 0:
                        logger.info(
                            f"[CHUNK {chunk_count}] Session {session.session_id} - Message length: {len(assistant_message)}")

                    # Check if client is still connected
                    try:
                        # Capture response ID
                        if hasattr(chunk, 'response') and hasattr(chunk.response, 'id'):
                            response_id = chunk.response.id
                            logger.info(f"[RESPONSE ID] Session {session.session_id} - Got response_id: {response_id}")

                        # Handle different event types from Responses API
                        if hasattr(chunk, 'type'):
                            # Log specific event types
                            if chunk.type in ['response.output_text.delta', 'response.done',
                                              'response.tool_call.delta']:
                                logger.debug(f"[EVENT] Session {session.session_id} - Type: {chunk.type}")

                            # Handle text delta events
                            if chunk.type == 'response.output_text.delta' and hasattr(chunk, 'delta'):
                                assistant_message += chunk.delta
                                yield f"data: {json.dumps({'type': 'content', 'content': chunk.delta})}\n\n"

                                # Periodically save the message in case of disconnection
                                # if len(assistant_message) - last_save_length > 500:  # Save every 500 chars
                                #     logger.info(
                                #         f"[PERIODIC SAVE] Session {session.session_id} - Saving at {len(assistant_message)} chars")

                            # Handle tool use events (file search)
                            elif chunk.type == 'response.tool_call.delta' and hasattr(chunk, 'tool_call'):
                                if chunk.tool_call.type == 'file_search':
                                    tool_uses.append('file_search')
                                    logger.info(f"[TOOL USE] Session {session.session_id} - File search initiated")
                                    yield f"data: {json.dumps({'type': 'tool_use', 'tool': 'file_search', 'status': 'searching'})}\n\n"

                            # Handle citation events if available
                            elif chunk.type == 'response.citation' and hasattr(chunk, 'citation'):
                                citations.append({
                                    'file_id': chunk.citation.file_id,
                                    'quote': chunk.citation.quote
                                })

                            # === REASONING EVENTS (keep connection alive) ===
                            elif chunk.type == 'response.reasoning_summary_part.added':
                                yield f"data: {json.dumps({'type': 'reasoning', 'status': 'summary_part_added'})}\n\n"

                            elif chunk.type == 'response.reasoning_summary_part.done':
                                yield f"data: {json.dumps({'type': 'reasoning', 'status': 'summary_part_done'})}\n\n"

                            elif chunk.type == 'response.reasoning_summary_text.delta':
                                yield f"data: {json.dumps({'type': 'reasoning', 'status': 'summary_text_delta'})}\n\n"

                            elif chunk.type == 'response.reasoning_summary_text.done':
                                yield f"data: {json.dumps({'type': 'reasoning', 'status': 'summary_text_done'})}\n\n"

                            elif chunk.type == 'response.reasoning.delta':
                                if chunk_count % 5 == 0:  # Log every 5th reasoning event
                                    logger.info(f"[REASONING] Session {session.session_id} - Reasoning in progress")
                                yield f"data: {json.dumps({'type': 'reasoning', 'status': 'reasoning_delta'})}\n\n"

                            elif chunk.type == 'response.reasoning.done':
                                logger.info(f"[REASONING DONE] Session {session.session_id}")
                                yield f"data: {json.dumps({'type': 'reasoning', 'status': 'reasoning_done'})}\n\n"

                            elif chunk.type == 'response.reasoning_summary.delta':
                                yield f"data: {json.dumps({'type': 'reasoning', 'status': 'reasoning_summary_delta'})}\n\n"

                            elif chunk.type == 'response.reasoning_summary.done':
                                yield f"data: {json.dumps({'type': 'reasoning', 'status': 'reasoning_summary_done'})}\n\n"

                            # === OUTPUT ITEM EVENTS ===
                            elif chunk.type == 'response.output_item.added':
                                yield f"data: {json.dumps({'type': 'output', 'status': 'item_added'})}\n\n"

                            elif chunk.type == 'response.output_item.done':
                                yield f"data: {json.dumps({'type': 'output', 'status': 'item_done'})}\n\n"

                            # === CONTENT PART EVENTS ===
                            elif chunk.type == 'response.content_part.added':
                                yield f"data: {json.dumps({'type': 'content_part', 'status': 'added'})}\n\n"

                            elif chunk.type == 'response.content_part.done':
                                yield f"data: {json.dumps({'type': 'content_part', 'status': 'done'})}\n\n"

                            # === TOOL CALL DELTA EVENTS (updated) ===
                            elif chunk.type == 'response.output_tool_calls.delta':
                                if hasattr(chunk, 'delta') and hasattr(chunk.delta, 'tool_calls'):
                                    for tool_call in chunk.delta.tool_calls:
                                        if tool_call.type == 'file_search':
                                            tool_uses.append('file_search')
                                            yield f"data: {json.dumps({'type': 'tool_use', 'tool': 'file_search', 'status': 'searching'})}\n\n"

                    except Exception as e:
                        logger.warning(
                            f"[CLIENT DISCONNECT] Session {session.session_id} - Chunk {chunk_count} - Error: {str(e)}")
                        logger.warning(
                            f"[DISCONNECT STATS] Message length: {len(assistant_message)}, Chunks: {chunk_count}")
                        # Continue processing even if client disconnected
                        continue

                logger.info(
                    f"[STREAM COMPLETE] Session {session.session_id} - Total chunks: {chunk_count}, Message length: {len(assistant_message)}")

                # Update session with response ID
                if response_id and response_id != session.response_id:
                    session.response_id = response_id
                    session.save(update_fields=['response_id'])
                    logger.info(f"[SESSION UPDATE] Session {session.session_id} - Updated response_id: {response_id}")

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
                logger.info(f"[DONE SENT] Session {session.session_id}")

            except Exception as e:
                logger.error(f"[STREAM ERROR] Session {session.session_id} - Error: {str(e)}", exc_info=True)
                logger.error(f"[ERROR STATS] Chunks: {chunk_count}, Message length: {len(assistant_message)}")

                # Save whatever we have so far
                if assistant_message:
                    try:
                        if not assistant_msg_obj:
                            ChatMessage.objects.create(
                                session=session,
                                role='assistant',
                                content=assistant_message + "\n\n[Response interrupted due to error]",
                                knowledge_base=knowledge_base,
                                metadata={
                                    'error': str(e),
                                    'partial': True,
                                    'response_id': response_id,
                                    'chunks_received': chunk_count,
                                    'error_time': timezone.now().isoformat()
                                }
                            )
                            logger.info(f"[ERROR SAVE] Session {session.session_id} - Saved partial message on error")
                    except Exception as save_error:
                        logger.error(
                            f"[SAVE ERROR] Session {session.session_id} - Failed to save on error: {str(save_error)}")

                yield f"data: {json.dumps({'type': 'error', 'error': 'An error occurred while generating the response.'})}\n\n"

        # Return streaming response with keep-alive headers
        response = StreamingHttpResponse(
            event_stream(),
            content_type='text/event-stream'
        )
        response['Cache-Control'] = 'no-cache'
        response['Connection'] = 'keep-alive'  # Critical for Heroku
        response['X-Accel-Buffering'] = 'no'
        return response

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON in request body'}, status=400)
    except Exception as e:
        logger.error(f"Chat error: {str(e)}", exc_info=True)
        return JsonResponse({'error': 'An unexpected error occurred'}, status=500)


@login_required
@require_http_methods(["GET"])
def api_get_chat_files(request):
    """Get all available chat input files for the current user"""
    try:
        # Get active chat input documents (not cleaned up yet)
        documents = Document.objects.filter(
            report_type='Chat Input',
            is_active=True,
            metadata__user=request.user.username
        ).order_by('-upload_date')

        files = []
        for doc in documents:
            files.append({
                'id': doc.id,
                'openai_file_id': doc.openai_file_id,
                'filename': doc.filename,
                'upload_date': doc.upload_date.isoformat(),
                'file_size': doc.metadata.get('file_size', 0)
            })

        return JsonResponse({
            'success': True,
            'files': files
        })

    except Exception as e:
        logger.error(f"Error fetching chat files: {e}")
        return JsonResponse({'success': False, 'error': 'Failed to load files'}, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_upload_chat_file(request):
    """Upload a file directly to OpenAI for chat use"""
    try:
        if 'file' not in request.FILES:
            return JsonResponse({'error': 'No file provided'}, status=400)

        uploaded_file = request.FILES['file']

        # Validate file size (10MB max)
        if uploaded_file.size > 10 * 1024 * 1024:
            return JsonResponse({'error': 'File too large (max 10MB)'}, status=400)

        # Validate file type
        allowed_extensions = ['.pdf', '.doc', '.docx', '.txt', '.csv', '.xlsx', '.xls', '.png', '.jpeg', 'jpg']
        file_extension = os.path.splitext(uploaded_file.name)[1].lower()
        if file_extension not in allowed_extensions:
            return JsonResponse({'error': f'File type {file_extension} not supported'}, status=400)

        # Create temporary file
        with tempfile.NamedTemporaryFile(suffix=file_extension, delete=False) as temp_file:
            for chunk in uploaded_file.chunks():
                temp_file.write(chunk)
            temp_path = temp_file.name

        try:
            # Calculate file hash -- might need to implement smart user hash here
            with open(temp_path, 'rb') as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()[:64]

            # Check if file already exists for this user
            existing_doc = Document.objects.filter(
                file_hash_id=file_hash,
                report_type='Chat Input',
                is_active=True,
                metadata__user=request.user.username
            ).first()

            if existing_doc:
                return JsonResponse({
                    'success': True,
                    'file_id': existing_doc.openai_file_id,
                    'document_id': existing_doc.id,
                    'message': 'File already exists'
                })

            # Upload to OpenAI
            client = get_openai_client()
            with open(temp_path, 'rb') as file:
                openai_file = client.files.create(
                    file=(uploaded_file.name, file),
                    purpose='user_data'
                )

            # Create Document record
            doc = Document.objects.create(
                file_directory='chat_uploads',
                file_hash_id=file_hash,
                openai_file_id=openai_file.id,
                filename=uploaded_file.name,
                expiration_rule=2,  # Temporary
                is_active=True,
                report_type='Chat Input',
                metadata={
                    'user': request.user.username,
                    'file_size': uploaded_file.size,
                    'upload_timestamp': timezone.now().isoformat(),
                    'file_extension': file_extension
                }
            )

            logger.info(f"User {request.user.username} uploaded chat file: {uploaded_file.name}")

            return JsonResponse({
                'success': True,
                'file_id': openai_file.id,
                'document_id': doc.id,
                'filename': uploaded_file.name
            })

        finally:
            # Clean up temp file
            try:
                os.unlink(temp_path)
            except:
                pass

    except Exception as e:
        logger.error(f"Error uploading chat file: {e}")
        return JsonResponse({'error': 'Failed to upload file'}, status=500)


@login_required
@csrf_exempt
@require_http_methods(["DELETE"])
def api_delete_chat_file(request, document_id):
    """Delete a chat file from OpenAI and mark document as inactive"""
    try:
        # Get document and verify ownership
        doc = Document.objects.get(
            id=document_id,
            report_type='Chat Input',
            metadata__user=request.user.username
        )

        # Delete from OpenAI
        if doc.openai_file_id:
            try:
                client = get_openai_client()
                client.files.delete(doc.openai_file_id)
                logger.info(f"Deleted OpenAI file: {doc.openai_file_id}")
            except Exception as e:
                logger.error(f"Error deleting OpenAI file: {e}")
                # Continue even if OpenAI deletion fails

        # Mark document as inactive
        doc.is_active = False
        doc.save(update_fields=['is_active', 'updated_at'])

        return JsonResponse({'success': True})

    except Document.DoesNotExist:
        return JsonResponse({'error': 'File not found'}, status=404)
    except Exception as e:
        logger.error(f"Error deleting chat file: {e}")
        return JsonResponse({'error': 'Failed to delete file'}, status=500)