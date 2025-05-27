import os
import time
import tempfile
import shutil
from pathlib import Path
from django.core.management.base import BaseCommand
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


class Command(BaseCommand):
    help = 'Create Chrome profile with AlphaSense login for Heroku deployment'

    def handle(self, *args, **options):
        # Get the project root directory
        BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
        CHROME_PROFILE_DIR = BASE_DIR / "chrome_profile_heroku"

        self.stdout.write(self.style.SUCCESS("Creating Chrome profile for Heroku deployment..."))

        # Create profile directory
        CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

        # Create a temporary download directory
        temp_dir = Path(tempfile.mkdtemp())

        try:
            driver = self.make_chrome(temp_dir, CHROME_PROFILE_DIR)
            driver.get("https://research.alpha-sense.com/login")

            self.stdout.write("=" * 60)
            self.stdout.write("MANUAL STEP: Log in to AlphaSense in the Chrome window that opened.")
            self.stdout.write("After logging in successfully, close the Chrome window.")
            self.stdout.write("The session will be saved to chrome_profile_heroku/ directory.")
            self.stdout.write("=" * 60)

            # Wait for user to close the browser
            try:
                while driver.service.is_connectable():
                    time.sleep(1)
            except:
                pass
            finally:
                try:
                    driver.quit()
                except:
                    pass

            self.stdout.write(self.style.SUCCESS("✅ Chrome profile created successfully!"))
            self.stdout.write(f"📁 Profile saved to: {CHROME_PROFILE_DIR}")
            self.stdout.write("🚀 You can now commit this profile to your repo and deploy to Heroku.")

        finally:
            # Clean up temp directory
            shutil.rmtree(temp_dir, ignore_errors=True)

    def make_chrome(self, download_dir: Path, profile_dir: Path) -> webdriver.Chrome:
        """Create Chrome webdriver for profile creation"""
        download_dir.mkdir(parents=True, exist_ok=True)
        profile_dir.mkdir(parents=True, exist_ok=True)

        opts = Options()

        # Don't use headless for profile creation - we need to see the login page
        # opts.add_argument("--headless=new")  # Comment this out for profile creation

        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1920,1080")

        # Use Chrome profile directory for persistent cookies/session
        opts.add_argument(f"--user-data-dir={profile_dir}")

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

        return webdriver.Chrome(options=opts)