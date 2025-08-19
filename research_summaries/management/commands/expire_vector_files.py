# research_summaries/management/commands/expire_vector_files.py
from django.core.management.base import BaseCommand
from research_summaries.processors.vector_file_expirer import expire_vector_files


class Command(BaseCommand):
    help = 'Expire and delete vector files that have exceeded their retention period'

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🚀 Starting vector file expiration process...')
        )

        expire_vector_files()

        self.stdout.write(
            self.style.SUCCESS('✅ Vector file expiration process completed.')
        )