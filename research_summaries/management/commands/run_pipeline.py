import time
import subprocess
import sys
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone
from research_summaries.models import ResearchNote


class Command(BaseCommand):
    help = 'Run complete research pipeline continuously with smart sleep logic'

    def ensure_browsers_installed(self):
        """Ensure Playwright browsers are installed"""
        self.stdout.write('🔍 Checking browser installation...')

        try:
            result = subprocess.run([
                sys.executable, "-m", "playwright", "install", "firefox"
            ], capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                self.stdout.write(self.style.SUCCESS('✅ Browsers installed/verified'))
                return True
            else:
                self.stdout.write(self.style.ERROR(f'❌ Browser installation failed: {result.stderr}'))
                return False

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Exception during browser installation: {e}'))
            return False

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🚀 Starting continuous research pipeline...')
        )

        # Install browsers once at startup
        if not self.ensure_browsers_installed():
            self.stdout.write(self.style.ERROR('❌ Failed to install browsers. Exiting.'))
            return

        while True:
            try:
                # Run the pipeline
                start_time = timezone.now()

                self.stdout.write('📧 Processing emails...')
                call_command('process_emails')

                # Check if there are any notes that need processing
                # Status 0: Not Downloaded, 1: Downloaded, 2: Preprocessed
                pending_notes = ResearchNote.objects.filter(status__in=[0, 1, 2])
                pending_count = pending_notes.count()

                if pending_count == 0:
                    elapsed = timezone.now() - start_time
                    self.stdout.write(
                        self.style.SUCCESS(f'✅ Email processing completed in {elapsed.total_seconds():.1f}s')
                    )
                    self.stdout.write(
                        self.style.WARNING('📭 No pending work found - sleeping for 30 minutes...')
                    )
                    time.sleep(30 * 60)  # 30 minutes
                    continue

                self.stdout.write('📥 Downloading files...')
                call_command('download_files_v2')

                self.stdout.write('🧹 Cleaning documents...')
                call_command('clean_documents')

                self.stdout.write('📝 Summarizing documents...')
                call_command('summarize_documents')

                elapsed = timezone.now() - start_time
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Pipeline completed in {elapsed.total_seconds():.1f}s')
                )

                # Short sleep between cycles when there's active work
                self.stdout.write('😴 Sleeping for 5 minutes before next cycle...')
                time.sleep(5 * 60)  # 5 minutes

            except KeyboardInterrupt:
                self.stdout.write('🛑 Pipeline stopped')
                break
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Pipeline error: {e}')
                )
                # Wait 3 minutes before retry
                time.sleep(3 * 60)