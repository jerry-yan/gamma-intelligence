import subprocess
import sys
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Install Playwright browsers'

    def add_arguments(self, parser):
        parser.add_argument(
            '--with-deps',
            action='store_true',
            help='Install with system dependencies (may fail on Heroku)',
        )

    def handle(self, *args, **options):
        self.stdout.write('🔍 Installing Playwright browsers...')

        cmd = [sys.executable, "-m", "playwright", "install", "firefox"]

        if options['with_deps']:
            cmd.append("--with-deps")
            self.stdout.write('Including system dependencies...')

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minutes timeout
            )

            if result.returncode == 0:
                self.stdout.write(self.style.SUCCESS('✅ Browser installation successful'))
                if result.stdout:
                    self.stdout.write(result.stdout)
            else:
                self.stdout.write(self.style.ERROR('❌ Browser installation failed'))
                if result.stderr:
                    self.stdout.write(result.stderr)

                # If --with-deps failed, try without
                if options['with_deps']:
                    self.stdout.write('Retrying without system dependencies...')
                    retry_cmd = [sys.executable, "-m", "playwright", "install", "firefox"]
                    retry_result = subprocess.run(
                        retry_cmd,
                        capture_output=True,
                        text=True,
                        timeout=600
                    )

                    if retry_result.returncode == 0:
                        self.stdout.write(self.style.SUCCESS('✅ Browser installation successful (without deps)'))
                    else:
                        self.stdout.write(self.style.ERROR('❌ Browser installation failed completely'))
                        if retry_result.stderr:
                            self.stdout.write(retry_result.stderr)

        except subprocess.TimeoutExpired:
            self.stdout.write(self.style.ERROR('❌ Browser installation timed out'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Exception during installation: {e}'))

        # Test the installation
        self.stdout.write('\n🧪 Testing browser installation...')
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.firefox.launch(headless=True)
                page = browser.new_page()
                page.goto('https://example.com', timeout=10000)
                title = page.title()
                browser.close()

                self.stdout.write(self.style.SUCCESS(f'✅ Browser test successful! Page title: {title}'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Browser test failed: {e}'))