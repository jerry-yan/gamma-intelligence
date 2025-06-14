import os
import time
import tempfile
import subprocess
import sys
from pathlib import Path
from django.utils.timezone import now
from django.conf import settings
from playwright.sync_api import sync_playwright
from research_summaries.models import ResearchNote
import boto3
from botocore.exceptions import ClientError
import logging

logger = logging.getLogger(__name__)

# ── CONSTANTS ────────────────────────────────────────────────────────
MAX_WAIT_SEC = 80  # seconds to wait for PDF
S3_BUCKET = 'gamma-invest'
S3_DOCUMENTS_PREFIX = 'documents/'

# Global flag to track if browsers are installed
_browsers_installed = False


# ── S3 CLIENT ───────────────────────────────────────────────────────
def get_s3_client():
    """Get configured S3 client"""
    return boto3.client(
        's3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME
    )


def ensure_browsers_installed():
    """Ensure Playwright browsers are installed at runtime"""
    global _browsers_installed

    if _browsers_installed:
        logger.info("Browsers already installed in this session")
        return True

    try:
        logger.info("Installing Playwright browsers at runtime...")
        result = subprocess.run([
            sys.executable, "-m", "playwright", "install", "firefox", "--with-deps"
        ], capture_output=True, text=True, timeout=300)

        if result.returncode == 0:
            logger.info("✅ Playwright browsers installed successfully")
            _browsers_installed = True
            return True
        else:
            # Try without --with-deps if that fails
            logger.warning("Installation with deps failed, trying without deps...")
            result = subprocess.run([
                sys.executable, "-m", "playwright", "install", "firefox"
            ], capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                logger.info("✅ Playwright browsers installed successfully (without deps)")
                _browsers_installed = True
                return True
            else:
                logger.error(f"❌ Browser installation failed: {result.stderr}")
                return False

    except Exception as e:
        logger.error(f"❌ Exception during browser installation: {e}")
        return False


def create_playwright_browser_context(playwright, download_dir: Path):
    """Create Playwright browser and context optimized for Heroku"""
    download_dir.mkdir(parents=True, exist_ok=True)

    # Simple Firefox launch with minimal arguments
    browser = playwright.firefox.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
        timeout=60000,
    )

    # Create browser context with download handling
    context = browser.new_context(
        accept_downloads=True,
        viewport={"width": 1024, "height": 768},
        user_agent="Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0",
        downloads_path=str(download_dir),
        ignore_https_errors=True,
    )

    return browser, context


def upload_to_s3(local_file_path: Path, s3_key: str) -> str:
    """Upload file to S3 and return the S3 URL"""
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
        logger.info(f"Successfully uploaded {local_file_path.name} to {s3_url}")
        return s3_url

    except ClientError as e:
        logger.error(f"Failed to upload {local_file_path} to S3: {e}")
        raise


def login_to_alphasense(page):
    """Login to AlphaSense using Playwright"""
    try:
        username = os.getenv('ALPHASENSE_USERNAME')
        password = os.getenv('ALPHASENSE_PASSWORD')

        if not username or not password:
            yield {"status": "error", "message": "❌ AlphaSense credentials not found in environment variables"}
            return False

        yield {"status": "info", "message": "🔐 Navigating to AlphaSense login..."}
        page.goto("https://research.alpha-sense.com/login", timeout=30000)

        # Step 1: Enter username and submit
        yield {"status": "info", "message": "🔐 Entering username..."}
        page.wait_for_selector('input[name="username"]', timeout=20000)
        page.fill('input[name="username"]', username)
        page.click('button[type="submit"]')

        yield {"status": "info", "message": "🔐 Username submitted, waiting for password field..."}

        # Step 2: Wait for password field to appear and fill it
        page.wait_for_selector('input[name="password"]', timeout=20000)
        page.fill('input[name="password"]', password)
        page.click('button[type="submit"]')

        yield {"status": "info", "message": "🔐 Password submitted, waiting for login completion..."}

        # Wait for successful login
        page.wait_for_function("() => !window.location.href.toLowerCase().includes('login')", timeout=30000)

        yield {"status": "success", "message": "✅ Successfully logged in to AlphaSense!"}
        return True

    except Exception as e:
        yield {"status": "error", "message": f"❌ Login failed: {str(e)}"}
        return False


def download_single_file_playwright(page, download_link, download_dir, file_id):
    """Download a single file using Playwright"""
    try:
        initial_files = set(download_dir.glob("*"))

        yield {"status": "info", "message": f"📥 Navigating to download link for {file_id}"}

        try:
            # Set up download promise before navigation
            with page.expect_download(timeout=MAX_WAIT_SEC * 1000) as download_info:
                page.goto(download_link, timeout=30000)

            # Get the download and save it
            download = download_info.value
            suggested_name = download.suggested_filename or f"{file_id}.pdf"
            download_path = download_dir / suggested_name
            download.save_as(download_path)

            yield {"status": "success", "message": f"📄 File downloaded: {download_path.name}"}
            return download_path

        except Exception as download_error:
            yield {"status": "info", "message": f"⚠️ Download promise failed, trying fallback method..."}

            # Fallback: navigate and wait for files to appear
            page.goto(download_link, timeout=30000)

            elapsed_wait = 0
            while elapsed_wait < MAX_WAIT_SEC:
                current_files = set(download_dir.glob("*"))
                new_files = current_files - initial_files

                completed_pdfs = [f for f in new_files if f.suffix.lower() == '.pdf' and not f.name.endswith('.part')]

                if completed_pdfs:
                    new_file = completed_pdfs[0]
                    yield {"status": "success", "message": f"📄 File downloaded (fallback): {new_file.name}"}
                    return new_file

                time.sleep(2)
                elapsed_wait += 2

                if elapsed_wait % 10 == 0:
                    yield {"status": "info",
                           "message": f"⏳ Still waiting (fallback)... ({elapsed_wait}s/{MAX_WAIT_SEC}s)"}

            yield {"status": "error", "message": f"⏱️ Timeout waiting for {file_id} download (fallback method)"}
            return None

    except Exception as e:
        yield {"status": "error", "message": f"❌ Error downloading {file_id}: {str(e)}"}
        return None


def update_note_in_database(note_id, s3_url):
    """Update note in database"""
    try:
        note = ResearchNote.objects.get(id=note_id)
        note.status = 1
        note.file_directory = s3_url
        note.file_download_time = now()
        note.save(update_fields=["status", "file_directory", "file_download_time"])
        return True
    except Exception as e:
        logger.error(f"Failed to update note {note_id}: {e}")
        return False


def download_documents_playwright():
    """Generator function that yields status updates during file downloading using Playwright"""
    try:
        # Ensure browsers are installed before starting
        yield {"status": "info", "message": "🔍 Checking browser installation..."}
        if not ensure_browsers_installed():
            yield {"status": "error", "message": "❌ Failed to install browsers"}
            return

        yield {"status": "success", "message": "✅ Browsers ready"}

        # Get documents to process
        BATCH_SIZE = 3
        queue_queryset = ResearchNote.objects.filter(status=0).order_by("id")[:BATCH_SIZE]
        queue = list(queue_queryset)
        total_pending = ResearchNote.objects.filter(status=0).count()

        if not queue:
            yield {"status": "info", "message": "✅ No documents to download"}
            return

        yield {"status": "info", "message": f"📑 Processing {len(queue)} files (Playwright/Firefox runtime)"}
        yield {"status": "info", "message": f"📊 Total pending downloads: {total_pending}"}

        downloaded_count = 0
        failed_count = 0

        # Use sync_playwright for the entire batch
        with sync_playwright() as playwright:
            browser = None

            try:
                # Process files one by one
                for i, note in enumerate(queue, 1):
                    yield {"status": "info", "message": f"🔄 Processing {i}/{len(queue)}: {note.file_id}"}

                    if not note.download_link:
                        yield {"status": "warning", "message": f"⚠️ {note.file_id} has no download link - skipped"}
                        continue

                    # Create unique temporary directory for this file
                    with tempfile.TemporaryDirectory(prefix=f"dl_pw_{note.file_id[:8]}_") as temp_dir:
                        temp_path = Path(temp_dir)

                        try:
                            # Create fresh browser for memory efficiency
                            if browser:
                                browser.close()

                            yield {"status": "info", "message": f"🦊 Starting Firefox browser (attempt {i})..."}
                            browser, context = create_playwright_browser_context(playwright, temp_path)
                            page = context.new_page()

                            # Login
                            login_success = True
                            for login_update in login_to_alphasense(page):
                                yield login_update
                                if login_update["status"] == "error":
                                    login_success = False
                                    break

                            if not login_success:
                                yield {"status": "error", "message": f"❌ Could not login"}
                                failed_count += 1
                                continue

                            time.sleep(2)  # Brief pause after login

                            # Download the file
                            pdf_path = None
                            for download_update in download_single_file_playwright(page, note.download_link, temp_path,
                                                                                   note.file_id):
                                yield download_update
                                if download_update["status"] == "success" and "downloaded" in download_update[
                                    "message"]:
                                    pdfs = list(temp_path.glob("*.pdf"))
                                    if pdfs:
                                        pdf_path = pdfs[0]

                            if not pdf_path:
                                yield {"status": "error", "message": f"❌ No PDF file found"}
                                failed_count += 1
                                continue

                            # Upload to S3
                            yield {"status": "info", "message": f"☁️ Uploading to S3..."}
                            s3_key = f"{S3_DOCUMENTS_PREFIX}{note.file_id}/{pdf_path.name}"
                            s3_url = upload_to_s3(pdf_path, s3_key)

                            # Update database
                            if update_note_in_database(note.id, s3_url):
                                downloaded_count += 1
                                yield {"status": "success", "message": f"✅ Successfully processed {note.file_id}"}
                            else:
                                yield {"status": "error", "message": f"❌ Failed to update database for {note.file_id}"}
                                failed_count += 1

                        except Exception as exc:
                            yield {"status": "error", "message": f"❌ Error: {str(exc)[:100]}"}
                            logger.exception(f"Error processing {note.file_id}")
                            failed_count += 1

                        finally:
                            # Clean up page
                            if 'page' in locals():
                                try:
                                    page.close()
                                except:
                                    pass

                        # Force garbage collection between files
                        import gc
                        gc.collect()

            finally:
                # Always clean up browser
                if browser:
                    try:
                        browser.close()
                        yield {"status": "info", "message": f"🧹 Browser closed"}
                    except:
                        pass

        # Get remaining count
        remaining = ResearchNote.objects.filter(status=0).count()

        yield {"status": "success", "message": f"🏁 Completed! Downloaded: {downloaded_count}, Failed: {failed_count}"}

        if remaining > 0:
            yield {"status": "info", "message": f"📋 {remaining} files remaining - click 'Start' again"}

    except Exception as e:
        yield {"status": "error", "message": f"🚨 Critical error: {str(e)[:200]}"}
        logger.exception("Critical error in download_documents_playwright")


# Main entry point
def download_documents():
    """Main entry point - delegates to Playwright implementation"""
    return download_documents_playwright()


# For compatibility with existing management commands and views
download_documents_v2 = download_documents_playwright