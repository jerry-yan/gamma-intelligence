from django.core.management.base import BaseCommand
from research_summaries.processors.file_downloader_2 import download_documents


class Command(BaseCommand):
    help = 'Download research files from AlphaSense using Playwright/Firefox (v2)'

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('Starting file download process (Playwright/Firefox)...')
        )

        for update in download_documents():
            if update["status"] == "error":
                self.stdout.write(self.style.ERROR(update["message"]))
            elif update["status"] == "success":
                self.stdout.write(self.style.SUCCESS(update["message"]))
            else:
                self.stdout.write(update["message"])

        self.stdout.write(
            self.style.SUCCESS('File download process completed (Playwright/Firefox).')
        )