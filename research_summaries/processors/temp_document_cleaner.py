"""
Temporary Document Cleaner

Clean up temporary documents that have been vectorized and are older than a specified threshold:
- Find Documents with expiration_rule=2 (temporary), is_vectorized=True
- Check if upload_date is older than the specified hours threshold
- Delete the file from OpenAI using their API
- Mark as not vectorized after successful deletion
"""
import logging
from datetime import timedelta
from django.utils import timezone
from documents.models import Document
from research_summaries.openai_utils import get_openai_client

logger = logging.getLogger(__name__)


def clean_temporary_documents(hours_threshold: int = 12):
    """
    Clean up temporary documents that have been vectorized and are older than the threshold.

    Args:
        hours_threshold: Number of hours after upload to wait before cleaning (default: 24)

    Returns:
        int: Number of documents successfully cleaned
    """
    # Calculate the cutoff time
    cutoff_time = timezone.now() - timedelta(hours=hours_threshold)

    # Find all temporary documents that are vectorized and older than threshold
    temp_docs = Document.objects.filter(
        expiration_rule=2,  # Temporary
        is_vectorized=True,
        upload_date__lt=cutoff_time
    )

    if not temp_docs.exists():
        logger.info("✅ No temporary documents need cleaning.")
        print("✅ No temporary documents need cleaning.")
        return 0

    logger.info(f"🧹 Found {temp_docs.count()} temporary documents to clean (older than {hours_threshold} hours)")
    print(f"🧹 Found {temp_docs.count()} temporary documents to clean (older than {hours_threshold} hours)")

    client = get_openai_client()
    success_count = 0

    for doc in temp_docs:
        try:
            if not doc.openai_file_id:
                logger.warning(
                    f"⚠️  Document {doc.id} ({doc.filename}) has no OpenAI file ID, marking as not vectorized")
                print(f"⚠️  Document {doc.id} ({doc.filename}) has no OpenAI file ID, marking as not vectorized")
                doc.is_vectorized = False
                doc.save(update_fields=['is_vectorized', 'updated_at'])
                continue

            logger.info(f"🗑️  Deleting OpenAI file {doc.openai_file_id} for document {doc.filename}")
            print(f"🗑️  Deleting OpenAI file {doc.openai_file_id} for document {doc.filename}")

            # Delete the file from OpenAI
            try:
                client.files.delete(doc.openai_file_id)
                logger.info(f"✅ Successfully deleted OpenAI file {doc.openai_file_id}")
                print(f"✅ Successfully deleted OpenAI file {doc.openai_file_id}")
            except Exception as e:
                # If the file is already deleted or doesn't exist, we still want to mark it as not vectorized
                error_str = str(e).lower()
                if "no such file" in error_str or "not found" in error_str:
                    logger.info(f"ℹ️  File {doc.openai_file_id} already deleted or not found")
                    print(f"ℹ️  File {doc.openai_file_id} already deleted or not found")
                else:
                    raise

            # Mark as not vectorized
            doc.is_vectorized = False
            doc.save(update_fields=['is_vectorized', 'updated_at'])
            success_count += 1

            logger.info(f"✅ Cleaned temporary document: {doc.filename}")
            print(f"✅ Cleaned temporary document: {doc.filename}")

        except Exception as e:
            logger.error(f"❌ Error cleaning document {doc.id} ({doc.filename}): {e}")
            print(f"❌ Error cleaning document {doc.id} ({doc.filename}): {e}")

    logger.info(
        f"🏁 Temporary document cleanup finished. {success_count}/{temp_docs.count()} documents cleaned successfully.")
    print(f"🏁 Temporary document cleanup finished. {success_count}/{temp_docs.count()} documents cleaned successfully.")

    return success_count


def get_temporary_documents_stats():
    """
    Get statistics about temporary documents.

    Returns:
        dict: Statistics about temporary documents
    """
    total_temp = Document.objects.filter(expiration_rule=2).count()
    vectorized_temp = Document.objects.filter(expiration_rule=2, is_vectorized=True).count()

    # Get counts by age
    now = timezone.now()
    age_stats = {}

    for hours in [6, 12, 24, 48, 72]:
        cutoff = now - timedelta(hours=hours)
        count = Document.objects.filter(
            expiration_rule=2,
            is_vectorized=True,
            upload_date__lt=cutoff
        ).count()
        age_stats[f"older_than_{hours}h"] = count

    return {
        'total_temporary': total_temp,
        'vectorized_temporary': vectorized_temp,
        'age_distribution': age_stats
    }