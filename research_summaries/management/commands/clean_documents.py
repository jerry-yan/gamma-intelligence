from django.core.management.base import BaseCommand
from research_summaries.processors.document_cleaner import clean_documents

class Command(BaseCommand):
    help = 'Clean research PDFs by removing disclosure sections'

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('Starting document cleaning process...')
        )

        clean_documents()

        self.stdout.write(
            self.style.SUCCESS('Document cleaning process completed.')
        )