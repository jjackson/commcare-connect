"""
Check if the Connect production API supports compression.

Usage:
    python manage.py check_api_compression --opportunity_id=765
"""

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand

from commcare_connect.labs.integrations.connect.cli import TokenManager


class Command(BaseCommand):
    help = "Check if Connect API supports compression for large downloads"

    def add_arguments(self, parser):
        parser.add_argument(
            "--opportunity_id",
            type=int,
            default=765,
            help="Opportunity ID to test (default: 765)",
        )

    def handle(self, *args, **options):
        opportunity_id = options["opportunity_id"]

        # Load OAuth token
        token_manager = TokenManager()
        token_data = token_manager.load_token()

        if not token_data:
            self.stdout.write(
                self.style.ERROR("No OAuth token found. Run: python -m commcare_connect.labs.oauth_cli.client")
            )
            return

        if token_manager.is_expired():
            self.stdout.write(
                self.style.ERROR("OAuth token expired. Run: python -m commcare_connect.labs.oauth_cli.client")
            )
            return

        access_token = token_data.get("access_token")
        url = f"{settings.CONNECT_PRODUCTION_URL}/export/opportunity/{opportunity_id}/user_visits/"

        self.stdout.write(f"\nTesting compression support for: {url}\n")

        # Test 1: Check what httpx sends by default
        self.stdout.write(self.style.MIGRATE_HEADING("1. Default httpx request headers:"))
        with httpx.Client() as client:
            # Build request to inspect headers
            request = client.build_request("GET", url, headers={"Authorization": f"Bearer {access_token}"})
            for key, value in request.headers.items():
                self.stdout.write(f"   {key}: {value}")

        # Test 2: Make a HEAD request to check response headers
        self.stdout.write(self.style.MIGRATE_HEADING("\n2. HEAD request response headers:"))
        try:
            response = httpx.head(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30.0,
            )
            self.stdout.write(f"   Status: {response.status_code}")
            for key, value in response.headers.items():
                self.stdout.write(f"   {key}: {value}")

            # Check for compression indicators
            content_encoding = response.headers.get("content-encoding")
            transfer_encoding = response.headers.get("transfer-encoding")
            vary = response.headers.get("vary")

            self.stdout.write(self.style.MIGRATE_HEADING("\n3. Compression analysis:"))
            if content_encoding:
                self.stdout.write(self.style.SUCCESS(f"   Content-Encoding: {content_encoding} (COMPRESSED)"))
            else:
                self.stdout.write(self.style.WARNING("   Content-Encoding: Not set (no compression)"))

            if transfer_encoding:
                self.stdout.write(f"   Transfer-Encoding: {transfer_encoding}")

            if vary and "accept-encoding" in vary.lower():
                self.stdout.write(self.style.SUCCESS("   Vary header includes Accept-Encoding (server can compress)"))
            else:
                self.stdout.write(self.style.WARNING("   Vary header does not include Accept-Encoding"))

        except httpx.TimeoutException:
            self.stdout.write(self.style.ERROR("   HEAD request timed out"))

        # Test 3: Make a small streaming request to check actual compression
        self.stdout.write(self.style.MIGRATE_HEADING("\n4. Streaming GET request (first 100KB):"))
        try:
            with httpx.stream(
                "GET",
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept-Encoding": "gzip, deflate, br",
                },
                timeout=60.0,
            ) as response:
                self.stdout.write(f"   Status: {response.status_code}")

                content_encoding = response.headers.get("content-encoding")
                content_length = response.headers.get("content-length")
                transfer_encoding = response.headers.get("transfer-encoding")

                self.stdout.write(f"   Content-Encoding: {content_encoding or 'Not set'}")
                self.stdout.write(f"   Content-Length: {content_length or 'Not set'}")
                self.stdout.write(f"   Transfer-Encoding: {transfer_encoding or 'Not set'}")

                # Read first 100KB to check
                bytes_read = 0
                for chunk in response.iter_bytes(chunk_size=8192):
                    bytes_read += len(chunk)
                    if bytes_read >= 100_000:
                        break

                self.stdout.write(f"   Read {bytes_read:,} bytes")

        except httpx.TimeoutException:
            self.stdout.write(self.style.ERROR("   GET request timed out"))

        # Summary
        self.stdout.write(self.style.MIGRATE_HEADING("\n5. Summary:"))
        if content_encoding in ("gzip", "br", "deflate"):
            self.stdout.write(self.style.SUCCESS(f"   Server IS compressing responses with {content_encoding}"))
        else:
            self.stdout.write(
                self.style.WARNING(
                    "   Server is NOT compressing responses.\n"
                    "   This could significantly slow down large downloads.\n"
                    "   Consider asking the Connect team to enable gzip compression."
                )
            )
