from django.core.management.base import BaseCommand
import glob
import os


class Command(BaseCommand):
    help = 'Debug browser installation locations'

    def handle(self, *args, **options):
        self.stdout.write('=== Browser Installation Debug ===')

        # Check environment
        env_vars = [
            'FIREFOX_EXECUTABLE_PATH',
            'PLAYWRIGHT_BROWSERS_PATH',
            'NODE_PATH',
            'PATH'
        ]

        for var in env_vars:
            value = os.getenv(var, 'Not set')
            self.stdout.write(f"{var}: {value}")

        # Search for browsers in common locations
        search_patterns = [
            "/app/node_modules/playwright*/**/*firefox*",
            "/app/.cache/**/*firefox*",
            "/app/.playwright/**/*firefox*",
            "/app/node_modules/**/*firefox*"
        ]

        for pattern in search_patterns:
            matches = glob.glob(pattern, recursive=True)
            if matches:
                self.stdout.write(f"\nFound in {pattern}:")
                for match in matches[:10]:  # Show first 10 matches
                    self.stdout.write(f"  {match}")

        # Test if we can find executable
        from research_summaries.processors.file_downloader_2 import get_browser_executable_path
        executable = get_browser_executable_path()

        if executable:
            self.stdout.write(self.style.SUCCESS(f"\n✅ Found executable: {executable}"))
        else:
            self.stdout.write(self.style.ERROR(f"\n❌ No executable found"))