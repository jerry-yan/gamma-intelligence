# research_summaries/processors/vector_file_expirer.py
"""
Vector File Expirer

Process ResearchNotes and Documents to expire vector files that have exceeded their retention period:
- Find active ResearchNotes and Documents with vector_group_id and openai_file_id
- Check if created_at + retention_days < current_time
- Delete expired files from OpenAI
- Mark as not vectorized and inactive after successful deletion
"""
import logging
from datetime import timedelta, datetime, time
from django.utils import timezone
from research_summaries.models import ResearchNote
from documents.models import Document
from agents.models import KnowledgeBase
from research_summaries.openai_utils import get_openai_client

logger = logging.getLogger(__name__)


def expire_vector_files():
    """
    Main function to expire vector files for both ResearchNotes and Documents.

    Returns:
        dict: Statistics about the expiration process
    """
    client = get_openai_client()

    # Track statistics
    stats = {
        'research_checked': 0,
        'research_expired': 0,
        'research_deleted': 0,
        'document_checked': 0,
        'document_expired': 0,
        'document_deleted': 0,
        'errors': 0
    }

    logger.info("🚀 Starting vector file expiration process...")
    print("🚀 Starting vector file expiration process...")

    # Process ResearchNotes
    expire_research_notes(client, stats)

    # Process Documents
    expire_documents(client, stats)

    # Log summary
    log_summary(stats)

    return stats


def expire_research_notes(client, stats):
    """
    Process ResearchNote objects for expiration.

    Args:
        client: OpenAI client instance
        stats: Dictionary to track statistics
    """
    # Get active research notes with vector_group_id, openai_file_id, and publication_date
    research_notes = ResearchNote.objects.filter(
        is_active=True,
        is_vectorized=True,
        vector_group_id__isnull=False,
        openai_file_id__isnull=False,
        publication_date__isnull=False
    ).exclude(
        openai_file_id__exact=''
    ).select_related()

    logger.info(f"📋 Found {research_notes.count()} active research notes to check")
    print(f"📋 Processing ResearchNotes... Found {research_notes.count()} active notes to check")

    for note in research_notes:
        stats['research_checked'] += 1

        try:
            # Get the associated KnowledgeBase
            try:
                kb = KnowledgeBase.objects.get(vector_group_id=note.vector_group_id)
            except KnowledgeBase.DoesNotExist:
                logger.warning(
                    f"No KnowledgeBase found for vector_group_id {note.vector_group_id} "
                    f"(ResearchNote: {note.file_id})"
                )
                print(
                    f"⚠️  No KnowledgeBase found for vector_group_id {note.vector_group_id} (ResearchNote: {note.file_id})")
                continue

            # Calculate expiration date (use end of publication day + retention days)
            # Set time to 23:59:59 for the publication date to give maximum flexibility
            pub_datetime = datetime.combine(
                note.publication_date,
                time.max
            )
            if timezone.is_naive(pub_datetime):
                pub_datetime = timezone.make_aware(pub_datetime)

            expiration_date = pub_datetime + timedelta(days=kb.file_retention)
            current_time = timezone.now()

            # Check if expired
            if current_time > expiration_date:
                stats['research_expired'] += 1

                days_expired = (current_time - expiration_date).days
                logger.info(
                    f"ResearchNote {note.file_id} expired {days_expired} days ago "
                    f"(pub_date: {note.publication_date}, retention: {kb.file_retention} days, KB: {kb.display_name})"
                )

                # Delete from OpenAI
                if delete_openai_file(client, note.openai_file_id, f'ResearchNote {note.file_id}'):
                    # Update the record
                    note.is_vectorized = False
                    note.is_active = False
                    note.save(update_fields=['is_vectorized', 'is_active', 'updated_at'])

                    stats['research_deleted'] += 1
                    logger.info(f"Successfully deleted and deactivated ResearchNote {note.file_id}")
                    print(f"✅ Deleted and deactivated ResearchNote {note.file_id}")
                else:
                    stats['errors'] += 1

        except Exception as e:
            stats['errors'] += 1
            logger.error(f"Error processing ResearchNote {note.file_id}: {e}", exc_info=True)
            print(f"❌ Error processing ResearchNote {note.file_id}: {e}")


def expire_documents(client, stats):
    """
    Process Document objects for expiration.

    Args:
        client: OpenAI client instance
        stats: Dictionary to track statistics
    """
    # Get active documents with vector_group_id, openai_file_id, and publication_date
    documents = Document.objects.filter(
        is_active=True,
        is_vectorized=True,
        vector_group_id__isnull=False,
        openai_file_id__isnull=False,
        publication_date__isnull=False
    ).exclude(
        openai_file_id__exact=''
    )

    logger.info(f"📄 Found {documents.count()} active documents to check")
    print(f"📄 Processing Documents... Found {documents.count()} active documents to check")

    for doc in documents:
        stats['document_checked'] += 1

        try:
            # Get the associated KnowledgeBase
            try:
                kb = KnowledgeBase.objects.get(vector_group_id=doc.vector_group_id)
            except KnowledgeBase.DoesNotExist:
                logger.warning(
                    f"No KnowledgeBase found for vector_group_id {doc.vector_group_id} "
                    f"(Document: {doc.filename})"
                )
                print(
                    f"⚠️  No KnowledgeBase found for vector_group_id {doc.vector_group_id} (Document: {doc.filename})")
                continue

            # Calculate expiration date (use end of publication day + retention days)
            # Set time to 23:59:59 for the publication date to give maximum flexibility
            pub_datetime = datetime.combine(
                doc.publication_date,
                time.max
            )
            if timezone.is_naive(pub_datetime):
                pub_datetime = timezone.make_aware(pub_datetime)

            expiration_date = pub_datetime + timedelta(days=kb.file_retention)
            current_time = timezone.now()

            # Check if expired
            if current_time > expiration_date:
                stats['document_expired'] += 1

                days_expired = (current_time - expiration_date).days
                logger.info(
                    f"Document {doc.filename} expired {days_expired} days ago "
                    f"(pub_date: {doc.publication_date}, retention: {kb.file_retention} days, KB: {kb.display_name})"
                )

                # Delete from OpenAI
                if delete_openai_file(client, doc.openai_file_id, f'Document {doc.filename}'):
                    # Update the record
                    doc.is_vectorized = False
                    doc.is_active = False
                    doc.save(update_fields=['is_vectorized', 'is_active', 'updated_at'])

                    stats['document_deleted'] += 1
                    logger.info(f"Successfully deleted and deactivated Document {doc.filename}")
                    print(f"✅ Deleted and deactivated Document {doc.filename}")
                else:
                    stats['errors'] += 1

        except Exception as e:
            stats['errors'] += 1
            logger.error(f"Error processing Document {doc.filename}: {e}", exc_info=True)
            print(f"❌ Error processing Document {doc.filename}: {e}")


def delete_openai_file(client, file_id, description):
    """
    Delete a file from OpenAI.

    Args:
        client: OpenAI client instance
        file_id: OpenAI file ID to delete
        description: Description of the file for logging

    Returns:
        bool: True if successful or file already deleted, False on error
    """
    try:
        client.files.delete(file_id)
        logger.info(f"✅ Successfully deleted OpenAI file {file_id} for {description}")
        return True

    except Exception as e:
        error_str = str(e).lower()

        # If the file is already deleted or doesn't exist, consider it success
        if "no such file" in error_str or "not found" in error_str:
            logger.info(f"ℹ️  File {file_id} already deleted or not found for {description}")
            print(f"   ℹ️  File {file_id} already deleted or not found")
            return True
        else:
            logger.error(f"Failed to delete OpenAI file {file_id} for {description}: {e}")
            print(f"   ❌ Failed to delete file {file_id}: {e}")
            return False


def log_summary(stats):
    """
    Log summary statistics.

    Args:
        stats: Dictionary containing statistics
    """
    total_checked = stats['research_checked'] + stats['document_checked']
    total_expired = stats['research_expired'] + stats['document_expired']
    total_deleted = stats['research_deleted'] + stats['document_deleted']

    logger.info("=" * 60)
    logger.info("📊 EXPIRATION SUMMARY")
    logger.info(
        f"ResearchNotes - Checked: {stats['research_checked']}, Expired: {stats['research_expired']}, Deleted: {stats['research_deleted']}")
    logger.info(
        f"Documents - Checked: {stats['document_checked']}, Expired: {stats['document_expired']}, Deleted: {stats['document_deleted']}")
    logger.info(f"Totals - Checked: {total_checked}, Expired: {total_expired}, Deleted: {total_deleted}")

    if stats['errors'] > 0:
        logger.error(f"Errors encountered: {stats['errors']}")

    logger.info("=" * 60)

    print("\n" + "=" * 60)
    print("📊 EXPIRATION SUMMARY")
    print("=" * 60)

    if stats['research_checked'] > 0:
        print(f"\n📋 ResearchNotes:")
        print(f"   Checked: {stats['research_checked']}")
        print(f"   Expired: {stats['research_expired']}")
        print(f"   Deleted: {stats['research_deleted']}")

    if stats['document_checked'] > 0:
        print(f"\n📄 Documents:")
        print(f"   Checked: {stats['document_checked']}")
        print(f"   Expired: {stats['document_expired']}")
        print(f"   Deleted: {stats['document_deleted']}")

    print(f"\n📈 Totals:")
    print(f"   Total Checked: {total_checked}")
    print(f"   Total Expired: {total_expired}")
    print(f"   Total Deleted: {total_deleted}")

    if stats['errors'] > 0:
        print(f"   ❌ Errors: {stats['errors']}")

    print("=" * 60)

    if total_deleted > 0:
        logger.info(f"✅ Successfully expired and deleted {total_deleted} vector files")
        print(f"\n✅ Successfully expired and deleted {total_deleted} vector files")
    else:
        logger.info("ℹ️  No files needed expiration")
        print("\nℹ️  No files needed expiration")