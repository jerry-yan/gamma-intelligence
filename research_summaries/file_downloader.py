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
    """Create Chrome webdriver configured for Heroku with memory optimization"""
    download_dir.mkdir(parents=True, exist_ok=True)

    opts = Options()

    # Heroku-specific options with memory optimization
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-web-security")
    opts.add_argument("--disable-features=VizDisplayCompositor")

    # Memory optimization arguments
    opts.add_argument("--memory-pressure-off")
    opts.add_argument("--max_old_space_size=256")
    opts.add_argument("--disable-background-timer-throttling")
    opts.add_argument("--disable-renderer-backgrounding")
    opts.add_argument("--disable-backgrounding-occluded-windows")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-plugins")
    opts.add_argument("--disable-images")  # Don't load images to save memory
    # Note: Don't disable JavaScript as it's needed for login

    # Reduce window size to save memory
    opts.add_argument("--window-size=800,600")
    opts.add_argument("--remote-debugging-port=9222")

    # Download preferences - each file gets its own directory
    opts.add_experimental_option("prefs", {
        "download.default_directory": str(download_dir.absolute()),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": False,  # Disable to save memory
        "plugins.always_open_pdf_externally": True,
        "profile.default_content_setting_values": {
            "images": 2,  # Block images
            "plugins": 2,  # Block plugins
            "popups": 2,  # Block popups
            "geolocation": 2,  # Block location sharing
            "notifications": 2,  # Block notifications
            "media_stream": 2,  # Block media stream
        }
    })

    # Anti-detection (minimal)
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])

    # Simplified user agent
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    # For Heroku, Chrome binary path might need to be specified
    chrome_binary = os.getenv('GOOGLE_CHROME_BIN')
    if chrome_binary:
        opts.binary_location = chrome_binary

    # Initialize ChromeDriver with service if needed
    try:
        from selenium.webdriver.chrome.service import Service
        chromedriver_path = os.getenv('CHROMEDRIVER_PATH', '/usr/bin/chromedriver')

        if os.path.exists(chromedriver_path):
            service = Service(chromedriver_path)
            return webdriver.Chrome(service=service, options=opts)
        else:
            return webdriver.Chrome(options=opts)
    except Exception:
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


def login_to_alphasense(driver):
    """
    Login to AlphaSense using two-step process (username first, then password)
    """
    try:
        username = os.getenv('ALPHASENSE_USERNAME')
        password = os.getenv('ALPHASENSE_PASSWORD')

        if not username or not password:
            yield {"status": "error", "message": "❌ AlphaSense credentials not found in environment variables"}
            return False

        yield {"status": "info", "message": "🔐 Navigating to AlphaSense login..."}
        driver.get("https://research.alpha-sense.com/login")

        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        wait = WebDriverWait(driver, 20)

        # Step 1: Enter username and submit
        yield {"status": "info", "message": "🔐 Entering username..."}
        username_field = wait.until(EC.presence_of_element_located((By.NAME, "username")))
        username_field.clear()
        username_field.send_keys(username)

        # Click submit after username
        submit_button = driver.find_element(By.XPATH, "//button[@type='submit']")
        submit_button.click()

        yield {"status": "info", "message": "🔐 Username submitted, waiting for password field..."}

        # Step 2: Wait for password field to appear and fill it
        password_field = wait.until(EC.presence_of_element_located((By.NAME, "password")))
        password_field.clear()
        password_field.send_keys(password)

        # Click submit again for final login
        final_submit_button = driver.find_element(By.XPATH, "//button[@type='submit']")
        final_submit_button.click()

        yield {"status": "info", "message": "🔐 Password submitted, waiting for login completion..."}

        # Wait for successful login (URL changes away from login page)
        wait.until(lambda d: "login" not in d.current_url.lower())

        yield {"status": "success", "message": "✅ Successfully logged in to AlphaSense!"}
        return True

    except Exception as e:
        yield {"status": "error", "message": f"❌ Login failed: {str(e)}"}
        return False


def download_single_file(driver, download_link, download_dir, file_id):
    """
    Download a single file to its specific directory
    """
    try:
        # Get initial file count in the specific download directory
        initial_files = set(download_dir.glob("*"))

        yield {"status": "info", "message": f"📥 Navigating to download link for {file_id}"}
        driver.get(download_link)

        # Wait for new file to appear in the download directory
        yield {"status": "info", "message": f"⏳ Waiting for PDF download (max {MAX_WAIT_SEC}s)"}
        elapsed_wait = 0

        while elapsed_wait < MAX_WAIT_SEC:
            current_files = set(download_dir.glob("*"))
            new_files = current_files - initial_files

            if new_files:
                # Found a new file!
                new_file = list(new_files)[0]
                yield {"status": "success", "message": f"📄 File downloaded: {new_file.name}"}
                return new_file

            time.sleep(2)
            elapsed_wait += 2

            if elapsed_wait % 10 == 0:  # Update every 10 seconds
                yield {"status": "info", "message": f"⏳ Still waiting... ({elapsed_wait}s/{MAX_WAIT_SEC}s)"}

        yield {"status": "error", "message": f"⏱️ Timeout waiting for {file_id} download"}
        return None

    except Exception as e:
        yield {"status": "error", "message": f"❌ Error downloading {file_id}: {str(e)}"}
        return None


def download_documents():
    """
    Generator function that yields status updates during file downloading
    Memory-optimized version that processes one file at a time
    """
    try:
        queue = ResearchNote.objects.filter(status=0).order_by("id")

        if not queue.exists():
            yield {"status": "info", "message": "✅ No documents to download"}
            return

        yield {"status": "info", "message": f"📑 Found {queue.count()} research notes to download"}

        downloaded_count = 0
        failed_count = 0

        # Process each file individually to minimize memory usage
        for i, note in enumerate(queue, 1):
            yield {"status": "info", "message": f"🔄 Processing {i}/{queue.count()}: {note.file_id}"}

            if not note.download_link:
                yield {"status": "warning", "message": f"⚠️ {note.file_id} has no download link - skipped"}
                continue

            # Create unique temporary directory for this specific file
            with tempfile.TemporaryDirectory(prefix=f"download_{note.file_id}_") as temp_dir:
                temp_path = Path(temp_dir)
                driver = None
                start_ts = time.time()

                try:
                    # Create fresh driver instance for each file to avoid memory buildup
                    yield {"status": "info", "message": f"🌐 Starting Chrome browser for {note.file_id}"}
                    driver = make_chrome(temp_path)

                    # Login for this file
                    login_success = True
                    for login_update in login_to_alphasense(driver):
                        yield login_update
                        if login_update["status"] == "error":
                            login_success = False
                            break

                    if not login_success:
                        yield {"status": "error", "message": f"❌ Could not login for {note.file_id}"}
                        failed_count += 1
                        continue

                    time.sleep(2)  # Brief pause after login

                    # Download the file to its specific directory
                    pdf_path = None
                    for download_update in download_single_file(driver, note.download_link, temp_path, note.file_id):
                        yield download_update
                        if download_update["status"] == "success" and "File downloaded:" in download_update["message"]:
                            # Extract the file path from successful download
                            pdfs = list(temp_path.glob("*.pdf"))
                            if pdfs:
                                pdf_path = pdfs[0]

                    if not pdf_path:
                        yield {"status": "error", "message": f"❌ No PDF file found for {note.file_id}"}
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
                    # Always clean up driver immediately to free memory
                    if driver:
                        try:
                            driver.quit()
                            yield {"status": "info", "message": f"🧹 Cleaned up browser for {note.file_id}"}
                        except:
                            pass

                    # Force garbage collection to free memory
                    import gc
                    gc.collect()

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