from django.core.management.base import BaseCommand
from EDGAR_bot.core import jobs

class Command(BaseCommand):
    help = "Run one EDGAR‑bot cycle and exit."

    def handle(self, *args, **opts):
        jobs.main()
