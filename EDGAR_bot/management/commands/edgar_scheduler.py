from django.core.management.base import BaseCommand
from EDGAR_bot.core.scheduler import main as scheduler_main

class Command(BaseCommand):
    help = "Start the APScheduler loop for continuous EDGAR crawling."

    def handle(self, *args, **opts):
        scheduler_main()
