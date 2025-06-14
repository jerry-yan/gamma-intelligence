from django.core.management.base import BaseCommand
import subprocess
import sys


class Command(BaseCommand):
    help = 'Debug browser installation and test Playwright'

    def handle(self, *args, **options):
        self.stdout.write('=== Browser Installation Debug ===')

        # Test if Playwright is installed
        try:
            from playwright.sync_api import sync_playwright
            self.stdout.write("✅ Playwright sync_api imported successfully")
        except ImportError as e:
            self.stdout.write(f"❌ Playwright not installed: {e}")
            return

        # Test browser installation directly
        self.stdout.write('\n🔍 Testing Firefox browser...')
        try:
            with sync_playwright() as p:
                self.stdout.write("🦊 Attempting to launch Firefox...")
                browser = p.firefox.launch(headless=True)
                self.stdout.write("✅ Firefox launched successfully")

                page = browser.new_page()
                self.stdout.write("📄 Created new page")

                page.goto('https://example.com', timeout=15000)
                self.stdout.write("🌐 Navigated to example.com")

                title = page.title()
                self.stdout.write(f"📋 Page title: {title}")

                browser.close()
                self.stdout.write("🔒 Browser closed")

                self.stdout.write(self.style.SUCCESS('✅ Firefox test completely successful!'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Firefox test failed: {e}'))

            # Try installing browsers
            self.stdout.write('\n📥 Attempting to install browsers...')
            try:
                self.stdout.write("Running: python -m playwright install firefox")
                result = subprocess.run([
                    sys.executable, "-m", "playwright", "install", "firefox"
                ], capture_output=True, text=True, timeout=300)

                self.stdout.write(f"Return code: {result.returncode}")
                if result.stdout:
                    self.stdout.write(f"STDOUT: {result.stdout}")
                if result.stderr:
                    self.stdout.write(f"STDERR: {result.stderr}")

                if result.returncode == 0:
                    self.stdout.write(self.style.SUCCESS('✅ Browser installation completed'))

                    # Test again
                    self.stdout.write('🔄 Testing again after installation...')
                    with sync_playwright() as p:
                        browser = p.firefox.launch(headless=True)
                        page = browser.new_page()
                        page.goto('https://example.com', timeout=15000)
                        title = page.title()
                        browser.close()

                        self.stdout.write(
                            self.style.SUCCESS(f'✅ Firefox test successful after installation! Page title: {title}'))

                else:
                    self.stdout.write(self.style.ERROR('❌ Browser installation failed'))

            except Exception as install_error:
                self.stdout.write(self.style.ERROR(f'❌ Installation error: {install_error}'))

        # Test file downloader import
        self.stdout.write('\n🧪 Testing file downloader import...')
        try:
            from research_summaries.processors.file_downloader_2 import ensure_browsers_installed
            self.stdout.write("✅ File downloader imported successfully")

            if ensure_browsers_installed():
                self.stdout.write(self.style.SUCCESS('✅ File downloader browser check passed'))
            else:
                self.stdout.write(self.style.ERROR('❌ File downloader browser check failed'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ File downloader import failed: {e}'))