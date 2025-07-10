# agents/api_views.py
import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.core.exceptions import ValidationError
from .models import KnowledgeBase
from research_summaries.openai_utils import get_openai_client

logger = logging.getLogger(__name__)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_create_knowledge_base(request):
    """
    API endpoint to create a new KnowledgeBase with OpenAI vector store

    Expected JSON payload:
    {
        "display_name": "My Knowledge Base",
        "vector_group_id": 123,
        "description": "Optional description"
    }
    """
    try:
        # Parse JSON data
        data = json.loads(request.body)

        # Extract and validate required fields
        display_name = data.get('display_name', '').strip()
        vector_group_id = data.get('vector_group_id')
        description = data.get('description', '').strip()

        # Validation
        if not display_name:
            return JsonResponse({
                'success': False,
                'error': 'display_name is required'
            }, status=400)

        if not vector_group_id:
            return JsonResponse({
                'success': False,
                'error': 'vector_group_id is required'
            }, status=400)

        try:
            vector_group_id = int(vector_group_id)
            if vector_group_id <= 0:
                raise ValueError("Must be positive")
        except (ValueError, TypeError):
            return JsonResponse({
                'success': False,
                'error': 'vector_group_id must be a positive integer'
            }, status=400)

        # Check for existing records
        if KnowledgeBase.objects.filter(name=display_name).exists():
            return JsonResponse({
                'success': False,
                'error': f'KnowledgeBase with name "{display_name}" already exists'
            }, status=400)

        if KnowledgeBase.objects.filter(vector_group_id=vector_group_id).exists():
            return JsonResponse({
                'success': False,
                'error': f'KnowledgeBase with vector_group_id {vector_group_id} already exists'
            }, status=400)

        # Create OpenAI vector store
        try:
            client = get_openai_client()
            vector_store = client.vector_stores.create(
                name=display_name,
                chunking_strategy={
                    'type': 'static',
                    'static': {
                        'max_chunk_size_tokens': 4096,
                        'chunk_overlap_tokens': 600,
                    }
                }
            )

            logger.info(f"Created OpenAI vector store: {vector_store.id} for {display_name}")

        except Exception as e:
            logger.error(f"Failed to create OpenAI vector store: {e}")
            return JsonResponse({
                'success': False,
                'error': f'Failed to create vector store: {str(e)}'
            }, status=500)

        # Create KnowledgeBase in database
        try:
            with transaction.atomic():
                knowledge_base = KnowledgeBase.objects.create(
                    name=display_name,
                    display_name=display_name,
                    vector_store_id=vector_store.id,
                    vector_group_id=vector_group_id,
                    description=description,
                    is_active=True
                )

                logger.info(f"Created KnowledgeBase: {knowledge_base.id} - {display_name}")

                return JsonResponse({
                    'success': True,
                    'data': {
                        'id': knowledge_base.id,
                        'name': knowledge_base.name,
                        'display_name': knowledge_base.display_name,
                        'vector_store_id': knowledge_base.vector_store_id,
                        'vector_group_id': knowledge_base.vector_group_id,
                        'description': knowledge_base.description,
                        'is_active': knowledge_base.is_active,
                        'created_at': knowledge_base.created_at.isoformat()
                    },
                    'message': f'KnowledgeBase "{display_name}" created successfully'
                })

        except Exception as e:
            # If database creation fails, try to clean up the OpenAI vector store
            try:
                client.vector_stores.delete(vector_store_id=vector_store.id)
                logger.info(f"Cleaned up OpenAI vector store: {vector_store.id}")
            except Exception as cleanup_error:
                logger.error(f"Failed to cleanup vector store {vector_store.id}: {cleanup_error}")

            logger.error(f"Failed to create KnowledgeBase in database: {e}")
            return JsonResponse({
                'success': False,
                'error': f'Failed to create knowledge base: {str(e)}'
            }, status=500)

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)

    except Exception as e:
        logger.error(f"Unexpected error in create_knowledge_base: {e}")
        return JsonResponse({
            'success': False,
            'error': 'An unexpected error occurred'
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_list_knowledge_bases(request):
    """
    API endpoint to list all active knowledge bases
    """
    try:
        knowledge_bases = KnowledgeBase.objects.filter(is_active=True).values(
            'id', 'name', 'display_name', 'vector_store_id',
            'vector_group_id', 'description', 'created_at'
        )

        return JsonResponse({
            'success': True,
            'data': list(knowledge_bases)
        })

    except Exception as e:
        logger.error(f"Error listing knowledge bases: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to retrieve knowledge bases'
        }, status=500)


@login_required
@csrf_exempt
@require_http_methods(["DELETE"])
def api_delete_knowledge_base(request, kb_id):
    """
    API endpoint to delete a knowledge base and its OpenAI vector store
    """
    try:
        knowledge_base = KnowledgeBase.objects.get(id=kb_id)
        vector_store_id = knowledge_base.vector_store_id
        display_name = knowledge_base.display_name

        # Delete from OpenAI first
        try:
            client = get_openai_client()
            client.vector_stores.delete(vector_store_id=vector_store_id)
            logger.info(f"Deleted OpenAI vector store: {vector_store_id}")
        except Exception as e:
            logger.warning(f"Failed to delete OpenAI vector store {vector_store_id}: {e}")
            # Continue with database deletion even if OpenAI deletion fails

        # Delete from database
        knowledge_base.delete()
        logger.info(f"Deleted KnowledgeBase: {kb_id} - {display_name}")

        return JsonResponse({
            'success': True,
            'message': f'KnowledgeBase "{display_name}" deleted successfully'
        })

    except KnowledgeBase.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'KnowledgeBase not found'
        }, status=404)

    except Exception as e:
        logger.error(f"Error deleting knowledge base {kb_id}: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to delete knowledge base'
        }, status=500)