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
                advanced_ready_notes = ResearchNote.objects.filter(status=3, is_advanced_summary=True)
                vectorization_ready_notes = ResearchNote.objects.filter(
                    status__in=[3, 4],
                    is_vectorized=False,
                    vector_group_id__isnull=False  # Ensure vector_group_id is not None
                )

                pending_count = pending_notes.count()
                advanced_count = advanced_ready_notes.count()
                vectorization_count = vectorization_ready_notes.count()

                # Run advanced summarization if there are notes marked for it
                if advanced_count > 0:
                    self.stdout.write(f'🧠 Advanced summarizing {advanced_count} documents with GPT o3-mini...')
                    call_command('summarize_documents_advanced')

                # Run vectorization if there are summarized notes not yet vectorized
                if vectorization_count > 0:
                    self.stdout.write(f'🔮 Vectorizing {vectorization_count} documents...')
                    call_command('vectorize_documents')

                if pending_count == 0:
                    elapsed = timezone.now() - start_time
                    self.stdout.write(
                        self.style.SUCCESS(f'✅ Email processing completed in {elapsed.total_seconds():.1f}s')
                    )
                    self.stdout.write(
                        self.style.WARNING('📭 No pending work found - sleeping for 20 minutes...')
                    )
                    time.sleep(20 * 60)  # 20 minutes
                    continue

                self.stdout.write('🗑️  Cleaning temporary vectorized documents...')
                call_command('clean_temp_documents', hours=12)

                self.stdout.write('📝 Summarizing documents...')
                call_command('summarize_documents')

                self.stdout.write('📥 Downloading files...')
                call_command('download_files')

                self.stdout.write('🧹 Cleaning documents...')
                call_command('clean_documents')

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