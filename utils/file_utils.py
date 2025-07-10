# utils/file_utils.py
"""
Utility functions for managing OpenAI file uploads and reuse
"""
import os
import boto3
import tempfile
from django.conf import settings
from research_summaries.openai_utils import get_openai_client


def get_s3_client():
    """Initialize S3 client with credentials"""
    return boto3.client(
        's3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME
    )


def download_pdf_from_s3(s3_key: str) -> str:
    """Download PDF from S3 to temporary file and return path"""
    s3_client = get_s3_client()
    bucket_name = settings.AWS_STORAGE_BUCKET_NAME

    # Create temporary file
    temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    temp_path = temp_file.name
    temp_file.close()

    try:
        s3_client.download_file(bucket_name, s3_key, temp_path)
        return temp_path
    except Exception as e:
        # Clean up on error
        try:
            os.unlink(temp_path)
        except:
            pass
        raise e


def get_or_upload_file_to_openai(s3_key: str, existing_file_id: str = None) -> str:
    """
    Check if an OpenAI file_id already exists for reuse.
    If it does, return the existing file_id.
    If not, upload the file from S3 to OpenAI and return the new file_id.

    Args:
        s3_key (str): The S3 key/path to the file
        existing_file_id (str, optional): Existing OpenAI file ID if available

    Returns:
        str: OpenAI file ID
    """
    # Reuse existing file if available
    if existing_file_id:
        print(f"♻️  Reusing existing OpenAI file: {existing_file_id}")
        return existing_file_id

    client = get_openai_client()

    # Clean up the s3_key if it's a full URL
    clean_s3_key = s3_key
    if s3_key.startswith('https://'):
        clean_s3_key = s3_key.split('amazonaws.com/')[-1]
    elif s3_key.startswith('s3://'):
        clean_s3_key = s3_key.split('/', 3)[-1]

    print(f"📥 Downloading file from S3...")
    temp_pdf_path = download_pdf_from_s3(clean_s3_key)

    try:
        # Upload file to OpenAI
        print(f"📤 Uploading file to OpenAI...")
        file_response = client.files.create(
            file=open(temp_pdf_path, 'rb'),
            purpose="user_data"
        )
        file_id = file_response.id

        print(f"💾 Generated new OpenAI file ID: {file_id}")

        return file_id
    finally:
        # Clean up temporary file
        if os.path.exists(temp_pdf_path):
            try:
                os.unlink(temp_pdf_path)
            except Exception as e:
                print(f"⚠️  Failed to delete temp file {temp_pdf_path}: {e}")