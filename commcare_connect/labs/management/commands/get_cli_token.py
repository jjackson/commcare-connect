"""
Django management command to obtain OAuth token via CLI flow.

Usage:
    python manage.py get_cli_token

Or with custom settings:
    python manage.py get_cli_token --port 8888 --save-to my_token.json
"""

import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from commcare_connect.labs.oauth_cli import TokenManager, get_oauth_token


class Command(BaseCommand):
    help = "Obtain an OAuth access token for CLI/script usage via browser authorization"

    def add_arguments(self, parser):
        parser.add_argument(
            "--client-id",
            type=str,
            help="OAuth client ID (defaults to CLI_OAUTH_CLIENT_ID from settings)",
        )
        parser.add_argument(
            "--client-secret",
            type=str,
            help="OAuth client secret (optional, for confidential clients)",
        )
        parser.add_argument(
            "--production-url",
            type=str,
            help="Production URL (defaults to CONNECT_PRODUCTION_URL from settings)",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=8765,
            help="Local port for OAuth callback (default: 8765)",
        )
        parser.add_argument(
            "--scope",
            type=str,
            default="export",
            help='OAuth scopes to request (default: "export")',
        )
        parser.add_argument(
            "--save-to",
            type=str,
            help="Save token to specified file (e.g., .oauth_token)",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Suppress output (only print token)",
        )

    def handle(self, *args, **options):
        # Get configuration from options or settings
        client_id = options.get("client_id") or getattr(settings, "CLI_OAUTH_CLIENT_ID", None)
        production_url = options.get("production_url") or getattr(settings, "CONNECT_PRODUCTION_URL", None)

        # Only load client_secret if explicitly provided via command line
        # For public clients (recommended for CLI), don't use client_secret - use PKCE instead
        client_secret = options.get("client_secret")

        if not client_id:
            raise CommandError(
                "OAuth client ID not provided. " "Set CLI_OAUTH_CLIENT_ID in settings or use --client-id"
            )

        if not production_url:
            raise CommandError(
                "Production URL not provided. " "Set CONNECT_PRODUCTION_URL in settings or use --production-url"
            )

        # Get OAuth token
        token_data = get_oauth_token(
            client_id=client_id,
            production_url=production_url,
            client_secret=client_secret,  # Will be None for public clients
            port=options["port"],
            scope=options["scope"],
            verbose=not options["quiet"],
        )

        if not token_data:
            raise CommandError("Failed to obtain OAuth token")

        # Always save to default TokenManager location
        token_manager = TokenManager()
        if token_manager.save_token(token_data):
            if not options["quiet"]:
                self.stdout.write(self.style.SUCCESS(f"\nToken saved to: {token_manager.token_file}"))
        else:
            self.stderr.write(self.style.ERROR("Failed to save token"))

        # Also save to custom file if requested
        if options["save_to"]:
            token_manager_custom = TokenManager(token_file=options["save_to"])
            if token_manager_custom.save_token(token_data):
                if not options["quiet"]:
                    self.stdout.write(self.style.SUCCESS(f"Also saved to: {options['save_to']}"))
            else:
                self.stderr.write(self.style.ERROR(f"Failed to save token to: {options['save_to']}"))

        # Print token (useful for piping to other commands)
        if options["quiet"]:
            self.stdout.write(token_data["access_token"])
        else:
            self.stdout.write("\n" + "=" * 70)
            self.stdout.write("Usage Examples:")
            self.stdout.write("=" * 70)
            self.stdout.write("\n# Set as environment variable:")
            self.stdout.write(f'export OAUTH_TOKEN="{token_data["access_token"]}"')
            self.stdout.write("\n# Use in Python:")
            self.stdout.write("import os")
            self.stdout.write('token = os.getenv("OAUTH_TOKEN")')
            self.stdout.write("\n# Use with httpx/requests:")
            self.stdout.write('headers = {"Authorization": f"Bearer {token}"}')
            self.stdout.write("")
