import os
import time
import tempfile
import shutil
from pathlib import Path
from django.utils.timezone import now
from django.conf import settings
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from research_summaries.models import ResearchNote
import boto3
from botocore.exceptions import ClientError
import logging

logger = logging.getLogger(__name__)

# ── CONSTANTS ────────────────────────────────────────────────────────
MAX_WAIT_SEC = 80  # seconds to wait for PDF
MIN_CYCLE_SEC = 12  # min time per iteration
S3_BUCKET = 'gamma-invest'
S3_DOCUMENTS_PREFIX = 'documents/'

# Chrome profile directory - included in repo for Heroku
BASE_DIR = Path(__file__).resolve().parent.parent
CHROME_PROFILE_DIR = BASE_DIR / "chrome_profile_heroku"


# ── S3 CLIENT ───────────────────────────────────────────────────────
def get_s3_client():
    """Get configured S3 client"""
    return boto3.client(
        's3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME
    )


# ── CHROME OPTIONS FOR HEROKU ───────────────────────────────────────
def make_chrome(download_dir: Path) -> webdriver.Chrome:
    """Create Chrome webdriver configured for Heroku"""
    download_dir.mkdir(parents=True, exist_ok=True)

    # Ensure chrome profile directory exists
    CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    opts = Options()

    # Heroku-specific options
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-web-security")
    opts.add_argument("--disable-features=VizDisplayCompositor")
    opts.add_argument("--window-size=1920,1080")

    # Use Chrome profile directory for persistent cookies/session
    opts.add_argument(f"--user-data-dir={CHROME_PROFILE_DIR}")

    # Download preferences
    opts.add_experimental_option("prefs", {
        "download.default_directory": str(download_dir),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "plugins.always_open_pdf_externally": True
    })

    # Anti-detection
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    # User agent
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    return webdriver.Chrome(options=opts)


def upload_to_s3(local_file_path: Path, s3_key: str) -> str:
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
        logger.info(f"Successfully uploaded {local_file_path.name} to {s3_url}")
        return s3_url

    except ClientError as e:
        logger.error(f"Failed to upload {local_file_path} to S3: {e}")
        raise


def download_documents():
    """
    Generator function that yields status updates during file downloading
    """
    try:
        queue = ResearchNote.objects.filter(status=0).order_by("id")

        if not queue.exists():
            yield {"status": "info", "message": "✅ No documents to download"}
            return

        yield {"status": "info", "message": f"📑 Found {queue.count()} research notes to download"}

        downloaded_count = 0
        failed_count = 0

        for i, note in enumerate(queue, 1):
            yield {"status": "info", "message": f"🔄 Processing {i}/{queue.count()}: {note.file_id}"}

            if not note.download_link:
                yield {"status": "warning", "message": f"⚠️ {note.file_id} has no download link - skipped"}
                continue

            # Create temporary directory for this download
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                driver = None
                start_ts = time.time()

                try:
                    yield {"status": "info", "message": f"🌐 Opening browser for {note.file_id}"}
                    driver = make_chrome(temp_path)

                    yield {"status": "info", "message": f"📥 Navigating to download link"}
                    driver.get(note.download_link)

                    # Wait for PDF download
                    yield {"status": "info", "message": f"⏳ Waiting for PDF download (max {MAX_WAIT_SEC}s)"}
                    elapsed_wait = 0
                    pdf_path = None

                    while elapsed_wait < MAX_WAIT_SEC:
                        pdfs = list(temp_path.glob("*.pdf"))
                        if pdfs:
                            pdf_path = pdfs[0]
                            yield {"status": "success", "message": f"📄 PDF downloaded: {pdf_path.name}"}
                            break

                        time.sleep(2)
                        elapsed_wait += 2

                        if elapsed_wait % 10 == 0:  # Update every 10 seconds
                            yield {"status": "info", "message": f"⏳ Still waiting... ({elapsed_wait}s/{MAX_WAIT_SEC}s)"}

                    if not pdf_path:
                        yield {"status": "error", "message": f"⏱️ Timeout waiting for {note.file_id} download"}
                        failed_count += 1
                        continue

                    # Upload to S3
                    yield {"status": "info", "message": f"☁️ Uploading {pdf_path.name} to S3"}

                    # Create S3 key: documents/file_id/filename.pdf
                    s3_key = f"{S3_DOCUMENTS_PREFIX}{note.file_id}/{pdf_path.name}"
                    s3_url = upload_to_s3(pdf_path, s3_key)

                    # Update database
                    note.status = 1
                    note.file_directory = s3_url
                    note.file_download_time = now()
                    note.save(update_fields=[
                        "status", "file_directory", "file_download_time"
                    ])

                    downloaded_count += 1
                    yield {"status": "success", "message": f"✅ Successfully processed {note.file_id}"}
                    yield {"status": "success", "message": f"📂 Saved to: {s3_url}"}

                except Exception as exc:
                    yield {"status": "error", "message": f"❌ Error with {note.file_id}: {str(exc)}"}
                    logger.exception(f"Error processing {note.file_id}")
                    failed_count += 1

                finally:
                    if driver:
                        try:
                            driver.quit()
                        except:
                            pass

                # Rate limiting
                total_elapsed = time.time() - start_ts
                if total_elapsed < MIN_CYCLE_SEC:
                    sleep_time = MIN_CYCLE_SEC - total_elapsed
                    yield {"status": "info", "message": f"😴 Rate limiting: sleeping {sleep_time:.1f}s"}
                    time.sleep(sleep_time)

        yield {"status": "success", "message": f"🏁 Download task finished!"}
        yield {"status": "success", "message": f"📊 Downloaded: {downloaded_count}, Failed: {failed_count}"}

    except Exception as e:
        yield {"status": "error", "message": f"🚨 Critical error in download process: {str(e)}"}
        logger.exception("Critical error in download_documents")