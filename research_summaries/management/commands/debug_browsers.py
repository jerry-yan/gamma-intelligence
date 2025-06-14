from django.core.management.base import BaseCommand
import subprocess
import sys


class Command(BaseCommand):
    help = 'Debug browser installation and test Playwright'

    def handle(self, *args, **options):
        self.stdout.write('=== Browser Installation Debug ===')

        # Test if Playwright is installed
        try:
            import playwright
            self.stdout.write(f"✅ Playwright installed: {playwright.__version__}")
        except ImportError:
            self.stdout.write("❌ Playwright not installed")
            return

        # Test browser installation
        self.stdout.write('\n🔍 Testing browser installation...')
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                # This will auto-install browsers if they're not present
                browser = p.firefox.launch(headless=True)
                page = browser.new_page()
                page.goto('https://example.com', timeout=15000)
                title = page.title()
                browser.close()

                self.stdout.write(self.style.SUCCESS(f'✅ Firefox test successful! Page title: {title}'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Firefox test failed: {e}'))

            # Try installing browsers
            self.stdout.write('\n📥 Attempting to install browsers...')
            try:
                result = subprocess.run([
                    sys.executable, "-m", "playwright", "install", "firefox"
                ], capture_output=True, text=True, timeout=300)

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
                    self.stdout.write(self.style.ERROR(f'❌ Browser installation failed: {result.stderr}'))

            except Exception as install_error:
                self.stdout.write(self.style.ERROR(f'❌ Installation error: {install_error}'))

        # Test file downloader import
        self.stdout.write('\n🧪 Testing file downloader import...')
        try:
            from research_summaries.processors.file_downloader_2 import ensure_browsers_installed

            if ensure_browsers_installed():
                self.stdout.write(self.style.SUCCESS('✅ File downloader browser check passed'))
            else:
                self.stdout.write(self.style.ERROR('❌ File downloader browser check failed'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ File downloader import failed: {e}'))