from django.core.management.base import BaseCommand
from research_summaries.processors.email_parser import fetch_research_summaries


class Command(BaseCommand):
    help = 'Process emails and extract research summaries'

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('Starting email processing...')
        )

        for update in fetch_research_summaries():
            if update["status"] == "error":
                self.stdout.write(self.style.ERROR(update["message"]))
            elif update["status"] == "success":
                self.stdout.write(self.style.SUCCESS(update["message"]))
            else:
                self.stdout.write(update["message"])

        self.stdout.write(
            self.style.SUCCESS('Email processing completed.')
        )