# research_summaries/processors/document_vectorizer.py
"""
Document Vectorizer for Research Notes

Process ResearchNotes that have been summarized but not yet vectorized:
- Find ResearchNotes with status 3 or 4 (summarized or advanced summarized) where is_vectorized=False
- For each note, determine which vector stores it should be uploaded to
- Upload to OpenAI and add to appropriate vector stores
- Mark as vectorized when complete
"""
import logging
import time
from typing import Set, Optional

from research_summaries.models import ResearchNote
from agents.models import StockTicker, KnowledgeBase
from utils.file_utils import get_or_upload_file_to_openai
from utils.vector_store import file_exists_in_vector_store
from research_summaries.openai_utils import get_openai_client

logger = logging.getLogger(__name__)


def get_vector_store_ids_for_note(note: ResearchNote) -> Set[int]:
    """
    Determine which vector stores a research note should be uploaded to.

    Returns a set of vector_group_ids that this note should be added to.
    """
    vector_ids = set()

    # Always include the note's original vector_group_id if it has one
    if note.vector_group_id:
        vector_ids.add(note.vector_group_id)

    # If the note has a parsed ticker, find all related vector stores
    if note.parsed_ticker:
        # Find all StockTicker entries where main_ticker matches
        matching_tickers = StockTicker.objects.filter(
            main_ticker=note.parsed_ticker
        ).values_list('vector_id', flat=True)

        # Add all found vector_ids to our set
        vector_ids.update(matching_tickers)

    return vector_ids


def upload_to_vector_store(
        client,
        vector_store_id: str,
        file_id: str,
        attributes: dict
) -> bool:
    """
    Upload a file to a specific vector store with metadata.

    Args:
        client: OpenAI client instance
        vector_store_id: ID of the vector store to upload to
        file_id: OpenAI file ID to upload
        attributes: Dictionary of metadata attributes to attach to the file

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Add file to vector store with metadata
        vector_file = client.vector_stores.files.create(
            vector_store_id=vector_store_id,
            file_id=file_id,
            attributes=attributes
        )

        # Poll for completion
        max_attempts = 20
        for attempt in range(max_attempts):
            status_response = client.vector_stores.files.poll(
                file_id=vector_file.id,
                vector_store_id=vector_store_id
            )

            if status_response.status == 'completed':
                logger.info(f"✅ Added file {file_id} to vector store {vector_store_id} - indexing complete")
                return True
            elif status_response.status == 'failed':
                logger.error(f"❌ File indexing failed for {file_id} in vector store {vector_store_id}")
                return False
            else:
                # Still processing
                if attempt % 6 == 0:  # Log every 30 seconds
                    logger.info(f"⏳ Still indexing file {file_id} in vector store {vector_store_id}...")
                time.sleep(3)  # Wait 5 seconds before checking again

        # Timeout after max attempts
        logger.error(f"⏱️ Timeout: File indexing took too long for {file_id} in vector store {vector_store_id}")
        return False

    except Exception as e:
        logger.error(f"❌ Failed to add file to vector store {vector_store_id}: {e}")
        return False


def vectorize_research_note(note: ResearchNote, client=None) -> bool:
    """
    Vectorize a single research note.

    Returns True if successful, False otherwise.
    """
    if client is None:
        client = get_openai_client()

    try:
        # Ensure we have an OpenAI file ID
        if not note.openai_file_id:
            logger.info(f"📤 Uploading file for {note.file_id} to OpenAI...")

            # Build S3 key from file_directory
            s3_key = note.file_directory

            # Upload file and get OpenAI file ID
            file_id = get_or_upload_file_to_openai(s3_key)

            # Save the OpenAI file ID for future reuse
            note.openai_file_id = file_id
            note.save(update_fields=['openai_file_id'])
        else:
            file_id = note.openai_file_id
            logger.info(f"♻️  Using existing OpenAI file ID: {file_id}")

        # Get all vector stores this note should be uploaded to
        vector_group_ids = get_vector_store_ids_for_note(note)

        if not vector_group_ids:
            logger.warning(f"⚠️  No vector stores found for {note.file_id}")
            return False

        logger.info(f"📊 Found {len(vector_group_ids)} vector stores for {note.file_id}: {vector_group_ids}")

        # Process each vector store
        success_count = 0
        for vector_group_id in vector_group_ids:
            # Find the corresponding KnowledgeBase
            try:
                kb = KnowledgeBase.objects.get(vector_group_id=vector_group_id)
                vector_store_id = kb.vector_store_id
            except KnowledgeBase.DoesNotExist:
                logger.warning(f"⚠️  No KnowledgeBase found for vector_group_id {vector_group_id}")
                continue

            # Check if file already exists in this vector store
            if file_exists_in_vector_store(vector_store_id, note.file_hash_id, client):
                logger.info(f"✓ File already exists in vector store {vector_store_id} (group {vector_group_id})")
                success_count += 1
                continue

            # Create attributes dictionary for metadata
            # Additional fields can be added here as needed
            attributes = {
                "hash_id": note.file_hash_id,
                "report_type": note.report_type or "Unknown",
                "ticker": note.parsed_ticker if note.parsed_ticker else None,
                "source": note.source if note.source else None,
                "author": note.raw_author if note.raw_author else None,
                "date": note.publication_date.isoformat() if note.publication_date else None,
                "timestamp": int(note.publication_date.timestamp()) if note.publication_date else None,
                "title": note.raw_title if note.raw_title else None,
            }

            # Remove None values to keep metadata clean
            attributes = {k: v for k, v in attributes.items() if v is not None}

            # Upload to this vector store
            if upload_to_vector_store(
                    client,
                    vector_store_id,
                    file_id,
                    attributes
            ):
                success_count += 1

        # If we successfully uploaded to at least one vector store, mark as vectorized
        if success_count > 0:
            note.is_vectorized = True
            note.save(update_fields=['is_vectorized', 'updated_at'])
            logger.info(f"✅ Successfully vectorized {note.file_id} to {success_count}/{len(vector_group_ids)} stores")
            return True
        else:
            logger.error(f"❌ Failed to vectorize {note.file_id} to any stores")
            return False

    except Exception as e:
        logger.error(f"❌ Error vectorizing {note.file_id}: {e}")
        return False


def vectorize_documents():
    """
    Main entry point for vectorizing documents.
    Processes all eligible ResearchNotes.
    """
    # Find all notes that are summarized but not vectorized
    eligible_notes = ResearchNote.objects.filter(
        status__in=[3, 4],  # Summarized or Advanced Summarized
        is_vectorized=False,
        vector_group_id__isnull=False  # Ensure vector_group_id is not None
    ).order_by('-file_summary_time')

    count = eligible_notes.count()

    if count == 0:
        logger.info("📭 No documents need vectorization")
        return

    logger.info(f"🚀 Starting vectorization for {count} documents...")

    # Get OpenAI client once for all operations
    client = get_openai_client()

    success_count = 0
    for i, note in enumerate(eligible_notes, 1):
        logger.info(f"\n📄 Processing {i}/{count}: {note.file_id}")

        if vectorize_research_note(note, client):
            success_count += 1

    logger.info(f"\n🏁 Vectorization complete: {success_count}/{count} documents processed successfully")