from django.core.management.base import BaseCommand
from research_summaries.processors.document_summarizer import summarize_documents


class Command(BaseCommand):
    help = 'Summarize research documents using OpenAI'

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('Starting document summarization process...')
        )

        summarize_documents()

        self.stdout.write(
            self.style.SUCCESS('Document summarization process completed.')
        )