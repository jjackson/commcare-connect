"""
Management command to scaffold enrichment data for opportunities.

This command fetches opportunities from prod, filters by min_visits,
and creates a scaffolding JSON file with all known data pre-populated.

Usage:
    # Default: min_visits=50
    python manage.py scaffold_opp_enrichment

    # Custom min_visits threshold
    python manage.py scaffold_opp_enrichment --min-visits=100

    # Include inactive opportunities
    python manage.py scaffold_opp_enrichment --include-inactive
"""

import json
from pathlib import Path

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from commcare_connect.labs.integrations.connect.cli.token_manager import TokenManager


class Command(BaseCommand):
    help = "Scaffold enrichment data for opportunities from prod"

    OUTPUT_PATH = Path(__file__).parent.parent.parent / "fixtures" / "opp_org_enrichment_temp_scaffolding.json"

    def add_arguments(self, parser):
        parser.add_argument(
            "--min-visits",
            type=int,
            default=50,
            help="Minimum visit count threshold (default: 50)",
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help="Include inactive/ended opportunities",
        )

    def handle(self, *args, **options):
        min_visits = options["min_visits"]
        include_inactive = options["include_inactive"]

        self.stdout.write("=" * 70)
        self.stdout.write("SCAFFOLD OPPORTUNITY ENRICHMENT DATA")
        self.stdout.write("=" * 70)
        self.stdout.write(f"Min visits: {min_visits}")
        self.stdout.write(f"Include inactive: {include_inactive}")
        self.stdout.write(f"Output file: {self.OUTPUT_PATH}")
        self.stdout.write("")

        # Get OAuth token
        token_manager = TokenManager()
        access_token = token_manager.get_valid_token()

        if not access_token:
            raise CommandError("No valid OAuth token found. Please run: python manage.py get_cli_token")

        # Fetch data from prod
        self.stdout.write("Fetching data from prod...")
        url = f"{settings.CONNECT_PRODUCTION_URL}/export/opp_org_program_list/"
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            response = httpx.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as e:
            raise CommandError(f"Failed to fetch data from prod: {e}")

        opportunities = data.get("opportunities", [])
        programs = data.get("programs", [])
        organizations = data.get("organizations", [])

        self.stdout.write(f"  Found {len(opportunities)} opportunities")
        self.stdout.write(f"  Found {len(programs)} programs")
        self.stdout.write(f"  Found {len(organizations)} organizations")
        self.stdout.write("")

        # Build lookup maps
        program_map = {p["id"]: p for p in programs}
        org_map = {o["slug"]: o for o in organizations}

        # Filter and build enrichment scaffolding
        enrichments = []
        for opp in opportunities:
            visit_count = opp.get("visit_count", 0)

            # Apply min_visits filter
            if visit_count < min_visits:
                continue

            # Apply active filter
            if not include_inactive and not opp.get("is_active", False):
                continue

            opp_id = opp.get("id")
            opp_name = opp.get("name", "")
            org_slug = opp.get("organization", "")
            program_id = opp.get("program")
            end_date = opp.get("end_date", "")
            is_active = opp.get("is_active", False)

            # Get program info
            program = program_map.get(program_id, {}) if program_id else {}
            program_name = program.get("name", "")
            delivery_type_slug = program.get("delivery_type", "")

            # Get org info
            org = org_map.get(org_slug, {})
            org_name = org.get("name", org_slug)

            # Build enrichment entry with all known data as comments
            enrichment = {
                "opportunity_id": opp_id,
                "_opp_name": opp_name,  # Reference info (not used by system)
                "_org_slug": org_slug,  # Reference info
                "_org_name": org_name,  # Reference info
                "_program_name": program_name,  # Reference info
                "_visit_count": visit_count,  # Reference info
                "_end_date": end_date,  # Reference info
                "_is_active": is_active,  # Reference info
                # Fields to populate:
                "delivery_type_slug": delivery_type_slug,  # Pre-filled from program if available
                "opp_country": "",  # TODO: Fill in country
                "amount_raised": 0,  # TODO: Fill in amount raised
                "budget_goal": 0,  # TODO: Fill in budget goal
                "visits_target": 0,  # TODO: Fill in visits target
                "org_photo_url": "",  # TODO: Fill in org photo URL
                "opp_description": "",  # TODO: Fill in opportunity description
            }

            enrichments.append(enrichment)

        # Sort by visit count descending (most active first)
        enrichments.sort(key=lambda x: x["_visit_count"], reverse=True)

        self.stdout.write(f"Filtered to {len(enrichments)} opportunities (min_visits={min_visits})")
        self.stdout.write("")

        # Build output structure
        output = {"enrichments": enrichments}

        # Write to file
        self.stdout.write(f"Writing to {self.OUTPUT_PATH}...")
        with open(self.OUTPUT_PATH, "w") as f:
            json.dump(output, f, indent=2)

        self.stdout.write("")
        self.stdout.write("=" * 70)
        self.stdout.write(self.style.SUCCESS("SCAFFOLDING COMPLETE"))
        self.stdout.write("=" * 70)
        self.stdout.write("")
        self.stdout.write("Next steps:")
        self.stdout.write("  1. Open the scaffolding file and fill in the TODO fields")
        self.stdout.write("  2. Remove the underscore-prefixed reference fields (optional)")
        self.stdout.write("  3. Copy the enrichments to opp_org_enrichment.json")
        self.stdout.write("  4. Run: python manage.py populate_opp_enrichment --target=api")
        self.stdout.write("")

        # Print summary
        self.stdout.write("Summary by delivery type:")
        dt_counts = {}
        for e in enrichments:
            dt = e.get("delivery_type_slug") or "(none)"
            dt_counts[dt] = dt_counts.get(dt, 0) + 1

        for dt, count in sorted(dt_counts.items(), key=lambda x: -x[1]):
            self.stdout.write(f"  {dt}: {count} opportunities")
