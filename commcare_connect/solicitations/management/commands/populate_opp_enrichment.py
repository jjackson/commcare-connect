"""
Management command to populate OppOrgEnrichmentRecord to production LabsRecord.

Usage:
    # Push enrichment data to production
    python manage.py populate_opp_enrichment

    # Dry run - show what would be created
    python manage.py populate_opp_enrichment --dry-run
"""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from commcare_connect.labs.integrations.connect.cli.token_manager import TokenManager


class Command(BaseCommand):
    help = "Push OppOrgEnrichmentRecord from JSON fixture to production LabsRecord"

    FIXTURE_PATH = Path(__file__).parent.parent.parent / "fixtures" / "opp_org_enrichment.json"
    EXPERIMENT = "solicitations"
    TYPE = "OppOrgEnrichmentRecord"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without actually creating records",
        )

    def handle(self, *args, **options):
        import httpx

        dry_run = options["dry_run"]

        self.stdout.write("=" * 70)
        self.stdout.write("PUSH OPP ORG ENRICHMENT TO PRODUCTION")
        self.stdout.write("=" * 70)
        self.stdout.write(f"Target: {settings.CONNECT_PRODUCTION_URL}")
        self.stdout.write(f"Dry run: {dry_run}")
        self.stdout.write("")

        # Load fixture
        if not self.FIXTURE_PATH.exists():
            raise CommandError(f"Fixture file not found: {self.FIXTURE_PATH}")

        with open(self.FIXTURE_PATH) as f:
            enrichment_data = json.load(f)

        enrichments = enrichment_data.get("enrichments", [])
        self.stdout.write(f"Loaded {len(enrichments)} enrichment entries from fixture")

        # Count entries with boundary data
        with_boundaries = sum(1 for e in enrichments if e.get("admin_boundaries"))
        self.stdout.write(f"  - {with_boundaries} entries have admin boundary data")
        self.stdout.write("")

        # Get OAuth token
        token_manager = TokenManager()
        access_token = token_manager.get_valid_token()

        if not access_token:
            raise CommandError("No valid OAuth token found. Please run: python manage.py get_cli_token")

        base_url = settings.CONNECT_PRODUCTION_URL.rstrip("/")
        api_url = f"{base_url}/export/labs_record/"
        headers = {"Authorization": f"Bearer {access_token}"}

        # Check if record already exists
        self.stdout.write("Checking for existing record...")
        try:
            response = httpx.get(
                api_url,
                params={
                    "experiment": self.EXPERIMENT,
                    "type": self.TYPE,
                },
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()
            existing_records = response.json()
        except httpx.HTTPError as e:
            raise CommandError(f"Failed to fetch existing records: {e}")

        if dry_run:
            if existing_records:
                self.stdout.write(f"  Would update existing record (ID: {existing_records[0]['id']})")
            else:
                self.stdout.write("  Would create new OppOrgEnrichmentRecord")
        else:
            if existing_records:
                # Update existing record
                record_id = existing_records[0]["id"]
                payload = [
                    {
                        "id": record_id,
                        "experiment": self.EXPERIMENT,
                        "type": self.TYPE,
                        "data": enrichment_data,
                        "public": True,
                    }
                ]
                try:
                    response = httpx.post(
                        api_url,
                        json=payload,
                        headers=headers,
                        timeout=60.0,
                    )
                    response.raise_for_status()
                    self.stdout.write(self.style.SUCCESS(f"  Updated existing record (ID: {record_id})"))
                except httpx.HTTPError as e:
                    raise CommandError(f"Failed to update record: {e}")
            else:
                # Create new record
                payload = [
                    {
                        "experiment": self.EXPERIMENT,
                        "type": self.TYPE,
                        "data": enrichment_data,
                        "public": True,
                    }
                ]
                try:
                    response = httpx.post(
                        api_url,
                        json=payload,
                        headers=headers,
                        timeout=60.0,
                    )
                    response.raise_for_status()
                    self.stdout.write(self.style.SUCCESS("  Created new OppOrgEnrichmentRecord"))
                except httpx.HTTPError as e:
                    raise CommandError(f"Failed to create record: {e}")

        self.stdout.write("")
        self.stdout.write("=" * 70)
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN COMPLETE - no changes made"))
        else:
            self.stdout.write(self.style.SUCCESS("PUSH COMPLETE"))
        self.stdout.write("=" * 70)
