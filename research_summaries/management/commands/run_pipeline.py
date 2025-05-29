import time
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone


class Command(BaseCommand):
    help = 'Run complete research pipeline continuously every 2 hours'

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

                self.stdout.write('📥 Downloading files...')
                call_command('download_files')

                self.stdout.write('🧹 Cleaning documents...')
                call_command('clean_documents')

                self.stdout.write('📝 Summarizing documents...')
                call_command('summarize_documents')

                elapsed = timezone.now() - start_time
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Pipeline completed in {elapsed.total_seconds():.1f}s')
                )

                # Wait 2 hours
                self.stdout.write('😴 Sleeping for 1 minute...')
                time.sleep(60) # sleep 1 minute
                # time.sleep(2 * 60 * 60)  # 2 hours in seconds

            except KeyboardInterrupt:
                self.stdout.write('🛑 Pipeline stopped')
                break
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Pipeline error: {e}')
                )
                # Wait 10 minutes before retry
                time.sleep(600)