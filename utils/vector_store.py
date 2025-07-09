from typing import Optional, Any
from openai import OpenAI
import os
from django.conf import settings


def get_openai_client():
    """Get or create OpenAI client using environment variable."""
    api_key = getattr(settings, 'OPENAI_API_KEY', None) or os.getenv('OPENAI_API_KEY')

    if not api_key:
        raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY in settings or environment variables.")

    return OpenAI(api_key=api_key)


def has_file_with_attribute(
        vector_store_id: str,
        attribute_key: str,
        attribute_value: Any,
        client: Optional[OpenAI] = None
) -> bool:
    """
    Check if a vector store contains at least one file with a specific attribute.

    Parameters
    ----------
    vector_store_id : str
        ID of the vector store to search.
    attribute_key : str
        The attribute key to filter by (e.g., "hash_id", "ticker", "category").
    attribute_value : Any
        The value to match for the given attribute key.
    client : OpenAI, optional
        OpenAI client instance. If None, will attempt to use get_openai_client()
        or create a new client.

    Returns
    -------
    bool
        True if at least one file matches the attribute filter, False otherwise.

    Examples
    --------
    >>> # Check if vector store has a file with hash_id="asd123fwf"
    >>> has_file_with_attribute("vs_123", "hash_id", "asd123fwf")
    True

    >>> # Check if vector store has a file with ticker="NVDA"
    >>> has_file_with_attribute("vs_123", "ticker", "NVDA")
    False
    """
    # Handle client initialization
    if client is None:
        client = get_openai_client()

    try:
        # Search the vector store with attribute filter
        response = client.vector_stores.search(
            vector_store_id=vector_store_id,
            query="*",  # Placeholder query - we rely on the filter
            filters={
                "key": attribute_key,
                "type": "eq",
                "value": attribute_value,
            },
            max_num_results=1  # We only need to know if at least one exists
        )

        # Return True if any results found
        return bool(response.data)

    except Exception as e:
        # Log the error if needed
        print(f"Error checking vector store attributes: {e}")
        return False


# Alternative: More flexible version with multiple filter options
def vector_store_has_files(
        vector_store_id: str,
        filters: dict,
        client: Optional[OpenAI] = None
) -> bool:
    """
    Check if a vector store contains files matching given filters.

    Parameters
    ----------
    vector_store_id : str
        ID of the vector store to search.
    filters : dict
        Filter dictionary with keys: "key", "type", "value"
        type can be: "eq" (equals), "ne" (not equals), etc.
    client : OpenAI, optional
        OpenAI client instance.

    Returns
    -------
    bool
        True if at least one file matches the filters.
    """
    if client is None:
        client = get_openai_client()

    try:
        response = client.vector_stores.search(
            vector_store_id=vector_store_id,
            query="*",
            filters=filters,
            max_num_results=1
        )
        return bool(response.data)
    except Exception as e:
        print(f"Error searching vector store: {e}")
        return False


# Convenience function for common use case
def file_exists_in_vector_store(
        vector_store_id: str,
        hash_id: str,
        client: Optional[OpenAI] = None
) -> bool:
    """
    Check if a file with a specific hash_id exists in the vector store.

    This is a convenience wrapper for the common use case of checking
    by hash_id to avoid duplicate uploads.
    """
    return has_file_with_attribute(vector_store_id, "hash_id", hash_id, client)