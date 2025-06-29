from django.core.management.base import BaseCommand
from research_summaries.processors.advanced_document_summarizer import summarize_documents_advanced


class Command(BaseCommand):
    help = 'Advanced summarize research documents using GPT o3-mini for documents marked for advanced processing'

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('Starting advanced document summarization process...')
        )

        summarize_documents_advanced()

        self.stdout.write(
            self.style.SUCCESS('Advanced document summarization process completed.')
        )