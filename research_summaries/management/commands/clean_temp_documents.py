# research_summaries/management/commands/clean_temp_documents.py
from django.core.management.base import BaseCommand, CommandError
from research_summaries.processors.temp_document_cleaner import clean_temporary_documents, get_temporary_documents_stats


class Command(BaseCommand):
    help = 'Clean up temporary documents that have been vectorized and are older than specified hours'

    def add_arguments(self, parser):
        parser.add_argument(
            '--hours',
            type=int,
            default=12,
            help='Number of hours after upload to wait before cleaning (default: 12)'
        )
        parser.add_argument(
            '--stats-only',
            action='store_true',
            help='Only show statistics without cleaning any documents'
        )

    def handle(self, *args, **options):
        hours_threshold = options['hours']
        stats_only = options['stats_only']

        if hours_threshold < 1:
            raise CommandError('Hours threshold must be at least 1')

        self.stdout.write(
            self.style.SUCCESS('🧹 Starting temporary document cleanup process...')
        )

        # Show statistics first
        stats = get_temporary_documents_stats()
        self.stdout.write(
            self.style.WARNING(f'\n📊 Temporary Document Statistics:')
        )
        self.stdout.write(f'   Total temporary documents: {stats["total_temporary"]}')
        self.stdout.write(f'   Vectorized temporary documents: {stats["vectorized_temporary"]}')
        self.stdout.write(f'\n   Age distribution of vectorized temporary documents:')
        for age_key, count in stats['age_distribution'].items():
            self.stdout.write(f'     {age_key}: {count}')

        if stats_only:
            self.stdout.write(
                self.style.SUCCESS('\n✅ Statistics displayed (--stats-only mode)')
            )
            return

        # Perform cleanup
        self.stdout.write(
            self.style.WARNING(f'\n🔄 Cleaning documents older than {hours_threshold} hours...')
        )

        try:
            cleaned_count = clean_temporary_documents(hours_threshold)

            if cleaned_count > 0:
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Successfully cleaned {cleaned_count} temporary documents.')
                )
            else:
                self.stdout.write(
                    self.style.WARNING('ℹ️  No documents needed cleaning.')
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Cleanup failed: {e}')
            )
            raise