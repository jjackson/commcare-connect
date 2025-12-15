"""
Management command to populate DeliveryTypeDescription records from JSON fixture.

Usage:
    # Populate local database directly
    python manage.py populate_delivery_types --target=local

    # Populate via API (uses CONNECT_PRODUCTION_URL from settings)
    python manage.py populate_delivery_types --target=api

    # Clear existing records before populating
    python manage.py populate_delivery_types --target=local --clear

    # Dry run - show what would be created
    python manage.py populate_delivery_types --target=local --dry-run
"""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from commcare_connect.labs.integrations.connect.cli.token_manager import TokenManager
from commcare_connect.opportunity.models import LabsRecord


class Command(BaseCommand):
    help = "Populate DeliveryTypeDescription records from JSON fixture"

    FIXTURE_PATH = Path(__file__).parent.parent.parent / "fixtures" / "delivery_type_descriptions.json"
    EXPERIMENT = "solicitations"
    TYPE = "DeliveryTypeDescriptionRecord"

    def add_arguments(self, parser):
        parser.add_argument(
            "--target",
            type=str,
            choices=["local", "api"],
            default="local",
            help="Target environment: 'local' for direct DB, 'api' for API calls (default: local)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing DeliveryTypeDescription records before populating",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without actually creating records",
        )

    def handle(self, *args, **options):
        target = options["target"]
        clear = options["clear"]
        dry_run = options["dry_run"]

        self.stdout.write("=" * 70)
        self.stdout.write("POPULATE DELIVERY TYPE DESCRIPTIONS")
        self.stdout.write("=" * 70)
        self.stdout.write(f"Target: {target}")
        self.stdout.write(f"Clear existing: {clear}")
        self.stdout.write(f"Dry run: {dry_run}")
        self.stdout.write("")

        # Load fixture
        if not self.FIXTURE_PATH.exists():
            raise CommandError(f"Fixture file not found: {self.FIXTURE_PATH}")

        with open(self.FIXTURE_PATH) as f:
            delivery_types = json.load(f)

        self.stdout.write(f"Loaded {len(delivery_types)} delivery types from fixture")
        self.stdout.write("")

        if target == "local":
            self._populate_local(delivery_types, clear, dry_run)
        else:
            self._populate_api(delivery_types, clear, dry_run)

        self.stdout.write("")
        self.stdout.write("=" * 70)
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN COMPLETE - no changes made"))
        else:
            self.stdout.write(self.style.SUCCESS("POPULATION COMPLETE"))
        self.stdout.write("=" * 70)

    def _populate_local(self, delivery_types: list, clear: bool, dry_run: bool):
        """Populate directly to local database."""
        self.stdout.write("[LOCAL] Populating local database...")
        self.stdout.write("")

        # Clear existing if requested
        if clear:
            existing = LabsRecord.objects.filter(experiment=self.EXPERIMENT, type=self.TYPE)
            count = existing.count()
            if dry_run:
                self.stdout.write(f"  Would delete {count} existing records")
            else:
                existing.delete()
                self.stdout.write(f"  Deleted {count} existing records")
            self.stdout.write("")

        # Create new records
        for dt in delivery_types:
            slug = dt["slug"]
            name = dt["name"]

            if dry_run:
                self.stdout.write(f"  Would create: {name} ({slug})")
            else:
                # Check if already exists by slug
                existing = LabsRecord.objects.filter(
                    experiment=self.EXPERIMENT,
                    type=self.TYPE,
                    data__slug=slug,
                ).first()

                if existing:
                    # Update existing
                    existing.data = dt
                    existing.public = True
                    existing.save()
                    self.stdout.write(f"  Updated: {name} ({slug})")
                else:
                    # Create new
                    LabsRecord.objects.create(
                        experiment=self.EXPERIMENT,
                        type=self.TYPE,
                        data=dt,
                        public=True,
                    )
                    self.stdout.write(f"  Created: {name} ({slug})")

    def _populate_api(self, delivery_types: list, clear: bool, dry_run: bool):
        """Populate via API calls to production/labs."""
        import httpx

        self.stdout.write(f"[API] Populating via API: {settings.CONNECT_PRODUCTION_URL}")
        self.stdout.write("")

        # Get OAuth token
        token_manager = TokenManager()
        access_token = token_manager.get_valid_token()

        if not access_token:
            raise CommandError("No valid OAuth token found. Please run: python manage.py get_cli_token")

        base_url = settings.CONNECT_PRODUCTION_URL.rstrip("/")
        api_url = f"{base_url}/export/labs_record/"
        headers = {"Authorization": f"Bearer {access_token}"}

        # Clear existing if requested
        if clear:
            self.stdout.write("  Fetching existing records to delete...")
            try:
                response = httpx.get(
                    api_url,
                    params={
                        "experiment": self.EXPERIMENT,
                        "type": self.TYPE,
                        "public": "true",
                    },
                    headers=headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                existing_records = response.json()

                if existing_records:
                    if dry_run:
                        self.stdout.write(f"  Would delete {len(existing_records)} existing records")
                    else:
                        # Delete via API
                        delete_payload = [{"id": r["id"]} for r in existing_records]
                        delete_response = httpx.request(
                            "DELETE",
                            api_url,
                            json=delete_payload,
                            headers=headers,
                            timeout=30.0,
                        )
                        delete_response.raise_for_status()
                        self.stdout.write(f"  Deleted {len(existing_records)} existing records")
                else:
                    self.stdout.write("  No existing records to delete")
            except httpx.HTTPError as e:
                raise CommandError(f"Failed to fetch/delete existing records: {e}")

            self.stdout.write("")

        # Create new records
        for dt in delivery_types:
            slug = dt["slug"]
            name = dt["name"]

            if dry_run:
                self.stdout.write(f"  Would create: {name} ({slug})")
            else:
                payload = [
                    {
                        "experiment": self.EXPERIMENT,
                        "type": self.TYPE,
                        "data": dt,
                        "public": True,
                    }
                ]

                try:
                    response = httpx.post(
                        api_url,
                        json=payload,
                        headers=headers,
                        timeout=30.0,
                    )
                    response.raise_for_status()
                    self.stdout.write(f"  Created: {name} ({slug})")
                except httpx.HTTPError as e:
                    self.stdout.write(self.style.ERROR(f"  Failed to create {name} ({slug}): {e}"))
