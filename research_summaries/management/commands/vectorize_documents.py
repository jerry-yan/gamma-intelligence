# research_summaries/management/commands/vectorize_documents.py
from django.core.management.base import BaseCommand
from research_summaries.processors.document_vectorizer import vectorize_documents


class Command(BaseCommand):
    help = 'Vectorize research documents by uploading them to OpenAI vector stores'

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🚀 Starting document vectorization process...')
        )

        try:
            vectorize_documents()

            self.stdout.write(
                self.style.SUCCESS('✅ Document vectorization process completed.')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Document vectorization failed: {e}')
            )
            raise