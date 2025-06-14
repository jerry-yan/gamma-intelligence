from django.core.management.base import BaseCommand
import glob
import os
import subprocess


class Command(BaseCommand):
    help = 'Debug browser installation locations'

    def handle(self, *args, **options):
        self.stdout.write('=== Browser Installation Debug ===')

        # Check environment
        env_vars = [
            'FIREFOX_EXECUTABLE_PATH',
            'PLAYWRIGHT_BROWSERS_PATH',
            'NODE_PATH',
            'PATH',
            'HOME',
            'TMPDIR'
        ]

        for var in env_vars:
            value = os.getenv(var, 'Not set')
            self.stdout.write(f"{var}: {value}")

        self.stdout.write('\n=== Searching for Firefox executables ===')

        # Use find command to search more thoroughly
        try:
            result = subprocess.run([
                'find', '/app', '-name', '*firefox*', '-type', 'f'
            ], capture_output=True, text=True, timeout=30)

            if result.stdout:
                self.stdout.write("Found Firefox-related files in /app:")
                for line in result.stdout.strip().split('\n')[:20]:  # First 20 results
                    self.stdout.write(f"  {line}")

            # Also search in tmp and cache directories
            for search_dir in ['/tmp', '/app/.cache', '/app/.npm', '/app/.config']:
                if os.path.exists(search_dir):
                    result = subprocess.run([
                        'find', search_dir, '-name', '*firefox*', '-type', 'f'
                    ], capture_output=True, text=True, timeout=10)

                    if result.stdout:
                        self.stdout.write(f"\nFound Firefox-related files in {search_dir}:")
                        for line in result.stdout.strip().split('\n')[:10]:
                            self.stdout.write(f"  {line}")

        except Exception as e:
            self.stdout.write(f"Error searching: {e}")

        # Test manual installation
        self.stdout.write('\n=== Testing manual browser installation ===')
        try:
            result = subprocess.run([
                'npx', 'playwright', 'install', 'firefox'
            ], capture_output=True, text=True, timeout=120)

            self.stdout.write(f"Installation result: {result.returncode}")
            if result.stdout:
                self.stdout.write(f"STDOUT: {result.stdout}")
            if result.stderr:
                self.stdout.write(f"STDERR: {result.stderr}")

        except Exception as e:
            self.stdout.write(f"Manual installation failed: {e}")