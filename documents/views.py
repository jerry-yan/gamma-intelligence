# documents/views.py
import os
import tempfile
import hashlib
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from botocore.exceptions import ClientError
import logging
from .forms import DocumentUploadForm
from .models import Document
from utils.file_utils import get_s3_client
import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# Constants
S3_BUCKET = 'gamma-invest'
S3_USER_DOCUMENTS_PREFIX = 'user_documents'


def extract_first_page_content(pdf_path):
    """Extract text and image content from the first page of a PDF"""
    doc = fitz.open(pdf_path)
    page = doc.load_page(0)
    text = page.get_text()

    images = page.get_images(full=True)
    image_bytes = b''
    for img_index, img in enumerate(images):
        xref = img[0]
        try:
            base_image = doc.extract_image(xref)
            image_bytes += base_image["image"]
        except:
            pass

    doc.close()
    combined_content = text.encode('utf-8') + image_bytes
    return combined_content


def hash_content(content):
    """Generate SHA256 hash of content"""
    return hashlib.sha256(content).hexdigest()


def extract_first_page_from_docx(docx_path):
    """Extract content from first page of DOCX file"""
    try:
        from docx import Document as DocxDocument
        doc = DocxDocument(docx_path)

        # Get text from first few paragraphs (approximating first page)
        first_page_text = ""
        char_count = 0
        for paragraph in doc.paragraphs:
            first_page_text += paragraph.text + "\n"
            char_count += len(paragraph.text)
            # Approximate first page as ~3000 characters
            if char_count > 3000:
                break

        return first_page_text.encode('utf-8')

    except Exception as e:
        # If docx parsing fails, return hash of entire file
        with open(docx_path, 'rb') as f:
            return f.read()[:10000]  # First 10KB


def extract_first_page_from_text(text_path):
    """Extract content from first part of text file"""
    with open(text_path, 'rb') as f:
        # Read first 10KB or entire file if smaller
        return f.read(10000)


def extract_first_page_from_excel(excel_path):
    """Extract content from first sheet of Excel file"""
    try:
        import pandas as pd
        # Read first sheet, first 100 rows
        df = pd.read_excel(excel_path, nrows=100)
        return df.to_string().encode('utf-8')
    except Exception as e:
        # If parsing fails, return hash of entire file
        with open(excel_path, 'rb') as f:
            return f.read()[:10000]  # First 10KB


def get_file_hash(file_path, file_extension):
    """Get hash of first page/section based on file type"""
    ext = file_extension.lower()

    if ext == '.pdf':
        content = extract_first_page_content(file_path)
    elif ext in ['.doc', '.docx']:
        content = extract_first_page_from_docx(file_path)
    elif ext in ['.txt', '.csv']:
        content = extract_first_page_from_text(file_path)
    elif ext in ['.xls', '.xlsx']:
        content = extract_first_page_from_excel(file_path)
    else:
        # For unknown types, hash first 10KB
        with open(file_path, 'rb') as f:
            content = f.read(10000)

    return hash_content(content)


def upload_to_s3(local_file_path, s3_key):
    """
    Upload file to S3 and return the S3 URL
    """
    try:
        s3_client = get_s3_client()

        with open(local_file_path, 'rb') as file:
            s3_client.upload_fileobj(
                file,
                S3_BUCKET,
                s3_key,
                ExtraArgs={
                    'ContentType': 'application/pdf',
                    'ServerSideEncryption': 'AES256'
                }
            )

        # Return S3 URL
        s3_url = f"s3://{S3_BUCKET}/{s3_key}"
        logger.info(f"Successfully uploaded {local_file_path} to {s3_url}")
        return s3_url

    except ClientError as e:
        logger.error(f"Failed to upload {local_file_path} to S3: {e}")
        raise


@login_required
def upload_document(request):
    """Handle document upload"""
    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = request.FILES['file']

            # Create temporary file
            file_extension = os.path.splitext(uploaded_file.name)[1]
            with tempfile.NamedTemporaryFile(suffix=file_extension, delete=False) as temp_file:
                # Write uploaded file to temp file
                for chunk in uploaded_file.chunks():
                    temp_file.write(chunk)
                temp_path = temp_file.name

            try:
                # Get file hash
                file_hash = get_file_hash(temp_path, file_extension)

                # Check if file already exists
                existing_doc = Document.objects.filter(file_hash_id=file_hash).first()

                if existing_doc:
                    # Reuse existing file's S3 location
                    document = form.save(commit=False)
                    document.filename = uploaded_file.name
                    document.file_hash_id = file_hash
                    document.file_directory = existing_doc.file_directory
                    document.save()

                    messages.success(
                        request,
                        f'Document "{uploaded_file.name}" linked to existing file (hash: {file_hash[:8]}...)'
                    )
                else:
                    # Upload new file to S3
                    s3_key = f"{S3_USER_DOCUMENTS_PREFIX}/{file_hash}/{uploaded_file.name}"
                    s3_url = upload_to_s3(temp_path, s3_key)

                    # Create document record
                    document = form.save(commit=False)
                    document.filename = uploaded_file.name
                    document.file_hash_id = file_hash
                    document.file_directory = s3_url
                    document.save()

                    messages.success(
                        request,
                        f'Document "{uploaded_file.name}" uploaded successfully with hash {file_hash[:8]}...'
                    )

                return redirect('documents:upload')

            except Exception as e:
                messages.error(request, f'Error uploading document: {str(e)}')
            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_path)
                except:
                    pass
    else:
        form = DocumentUploadForm()

    return render(request, 'documents/upload.html', {'form': form})


@login_required
def document_list(request):
    """List all documents"""
    documents = Document.objects.all().order_by('-upload_date')
    return render(request, 'documents/list.html', {'documents': documents})