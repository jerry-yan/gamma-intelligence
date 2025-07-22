# documents/views.py
import os
import tempfile
import hashlib
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from botocore.exceptions import ClientError
from .forms import DocumentUploadForm
from .models import Document
from utils.file_utils import get_s3_client
import fitz  # PyMuPDF
import logging
from datetime import datetime
from utils.file_utils import get_or_upload_file_to_openai
from research_summaries.openai_utils import get_openai_client
from research_summaries.processors.document_vectorizer import upload_to_vector_store

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
@permission_required('accounts.can_view_uploads', raise_exception=True)
def upload_document(request):
    """
    Handle document upload with duplicate check and automatic vectorization.
    Now supports uploading to multiple knowledge bases at once.
    """
    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():

            print(form.cleaned_data)

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

                # Get selected knowledge bases
                knowledge_bases = form.cleaned_data.get('knowledge_bases', [])

                # Get report type and expiration rules
                report_type = form.get_report_type()
                expiration_rule = form.get_expiration_rule()
                is_persistent = True if expiration_rule == 1 else False

                # Check if document already exists anywhere (to reuse S3/OpenAI)
                existing_doc = Document.objects.filter(file_hash_id=file_hash).first()

                # Find which selected knowledge bases already have this document
                already_exists_in = []
                new_knowledge_bases = []

                for kb in knowledge_bases:
                    exists = Document.objects.filter(
                        file_hash_id=file_hash,
                        vector_group_id=kb.vector_group_id
                    ).exists()

                    if exists:
                        already_exists_in.append(kb)
                    else:
                        new_knowledge_bases.append(kb)

                # If document exists in ALL selected knowledge bases, skip entirely
                if knowledge_bases and len(already_exists_in) == len(knowledge_bases):
                    kb_names = [kb.display_name for kb in already_exists_in]
                    messages.error(
                        request,
                        f'This document already exists in all selected knowledge bases: {", ".join(kb_names)}. '
                        f'Please select different knowledge bases or upload a different file.'
                    )
                    return redirect('documents:upload')

                # Notify user about knowledge bases that already have this document
                if already_exists_in:
                    kb_names = [kb.display_name for kb in already_exists_in]
                    messages.info(
                        request,
                        f'Document already exists in: {", ".join(kb_names)}. '
                        f'Skipping these knowledge bases.'
                    )

                # Reuse existing S3 URL and OpenAI file ID if document exists
                if existing_doc:
                    # Reuse existing S3 key and OpenAI file ID
                    s3_key = existing_doc.file_directory
                    s3_url = f"s3://{S3_BUCKET}/{s3_key}"
                    openai_file_id = existing_doc.openai_file_id
                    logger.info(f"♻️  Reusing existing file from S3: {s3_url}")
                    logger.info(f"♻️  Reusing OpenAI file ID: {openai_file_id}")
                else:
                    # Upload to S3 since this is a new file
                    s3_key = f"{S3_USER_DOCUMENTS_PREFIX}/{file_hash}{file_extension}"
                    s3_url = upload_to_s3(temp_path, s3_key)
                    logger.info(f"📤 Uploaded new file to S3: {s3_url}")

                    # Get or upload file to OpenAI
                    openai_file_id = None
                    try:
                        openai_file_id = get_or_upload_file_to_openai(s3_key)
                        logger.info(f"📎 OpenAI file ID: {openai_file_id}")
                    except Exception as e:
                        logger.error(f"Failed to upload to OpenAI: {e}")
                        messages.warning(
                            request,
                            f'File uploaded to S3, but OpenAI upload failed: {str(e)}. '
                            f'Document will be created but may not be vectorized.'
                        )

                # Prepare common document attributes
                common_attrs = {
                    'filename': uploaded_file.name,
                    'file_directory': s3_key,
                    'file_hash_id': file_hash,
                    'openai_file_id': openai_file_id,
                    'publication_date': form.cleaned_data.get('publication_date'),
                    'report_type': report_type,
                    'is_persistent_document': is_persistent,
                    'expiration_rule': expiration_rule,
                    'metadata': form.cleaned_data.get('metadata', {}),
                }

                # Create document entries and vectorize for new knowledge bases only
                created_documents = []
                vectorization_results = []

                # If no knowledge bases selected, create one document without vector_group_id
                if not knowledge_bases:
                    document = Document.objects.create(**common_attrs, vector_group_id=None)
                    created_documents.append(document)
                    logger.info(f"📄 Created document {document.id} without knowledge base")
                    messages.success(
                        request,
                        f'Document uploaded successfully without knowledge base assignment.'
                    )
                else:
                    # Create a document for each NEW knowledge base only
                    for kb in new_knowledge_bases:
                        document = Document.objects.create(
                            **common_attrs,
                            vector_group_id=kb.vector_group_id
                        )
                        created_documents.append(document)
                        logger.info(f"📄 Created document {document.id} for knowledge base: {kb.display_name}")

                        # Try to vectorize if we have an OpenAI file ID
                        if openai_file_id and kb.vector_store_id:
                            try:
                                # Get OpenAI client
                                client = get_openai_client()

                                # Prepare metadata attributes for vector store
                                attributes = {
                                    "hash_id": document.file_hash_id,
                                    "report_type": document.report_type,
                                }

                                # Add optional attributes
                                if document.publication_date:
                                    attributes["date"] = document.publication_date.isoformat()
                                    attributes["timestamp"] = int(datetime.combine(
                                        document.publication_date,
                                        datetime.min.time()
                                    ).timestamp())

                                # Remove any None values
                                attributes = {k: v for k, v in attributes.items() if v is not None}
                                logger.info(f"📋 Prepared {len(attributes)} metadata attributes for {kb.display_name}")

                                # Upload to vector store
                                success = upload_to_vector_store(
                                    client,
                                    kb.vector_store_id,
                                    document.openai_file_id,
                                    attributes
                                )

                                if success:
                                    document.is_vectorized = True
                                    document.save(update_fields=['is_vectorized'])
                                    logger.info(
                                        f"✅ Document {document.id} successfully vectorized to {kb.display_name}")
                                    vectorization_results.append((kb.display_name, True, None))
                                else:
                                    logger.warning(
                                        f"⚠️  Failed to vectorize document {document.id} to {kb.display_name}")
                                    vectorization_results.append((kb.display_name, False, "Vectorization failed"))

                            except Exception as e:
                                logger.error(f"❌ Error during vectorization of document {document.id}: {e}")
                                vectorization_results.append((kb.display_name, False, str(e)))

                # Provide user feedback
                if new_knowledge_bases:
                    success_count = sum(1 for _, success, _ in vectorization_results if success)
                    total_count = len(vectorization_results)

                    if success_count == total_count:
                        messages.success(
                            request,
                            f'Document successfully uploaded to {total_count} new knowledge base(s) and vectorized.'
                        )
                    elif success_count > 0:
                        failed_kbs = [kb_name for kb_name, success, _ in vectorization_results if not success]
                        messages.warning(
                            request,
                            f'Document uploaded to {total_count} new knowledge base(s), but vectorization '
                            f'failed for: {", ".join(failed_kbs)}. These will be processed later.'
                        )
                    else:
                        messages.warning(
                            request,
                            f'Document uploaded to {total_count} new knowledge base(s), but vectorization '
                            f'failed. Documents will be processed later.'
                        )
                elif already_exists_in and not new_knowledge_bases:
                    # All selected KBs already had the document
                    pass  # Error message already shown above

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
@permission_required('accounts.can_view_uploads', raise_exception=True)
def document_list(request):
    """List all documents"""
    documents = Document.objects.all().order_by('-upload_date')
    return render(request, 'documents/list.html', {'documents': documents})