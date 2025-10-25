from django.core.management.base import BaseCommand
from EDGAR_bot.core.scheduler_v2 import main as scheduler_v2_main

class Command(BaseCommand):
    help = "Start the APScheduler loop for continuous EDGAR crawling with earnings/cooldown periods."

    def handle(self, *args, **opts):
        scheduler_v2_main()