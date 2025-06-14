import time
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone
from research_summaries.models import ResearchNote


class Command(BaseCommand):
    help = 'Run complete research pipeline continuously with smart sleep logic'

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🚀 Starting continuous research pipeline...')
        )

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
                # call_command('download_files')
                call_command('download_documents_playwright')

                self.stdout.write('🧹 Cleaning documents...')
                call_command('clean_documents')

                self.stdout.write('📝 Summarizing documents...')
                call_command('summarize_documents')

                elapsed = timezone.now() - start_time
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Pipeline completed in {elapsed.total_seconds():.1f}s')
                )

                # Short sleep between cycles when there's active work
                self.stdout.write('😴 Sleeping for 1 minute before next cycle...')
                time.sleep(60)  # 5 minutes

            except KeyboardInterrupt:
                self.stdout.write('🛑 Pipeline stopped')
                break
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Pipeline error: {e}')
                )
                # Wait 3 minutes before retry
                time.sleep(3 * 60)