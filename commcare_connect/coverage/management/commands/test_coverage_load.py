"""
Management command to test coverage data loading.

This replicates the same loading process as the web UI but can be run from CLI.
"""
import json
import logging
from datetime import datetime, timedelta
from unittest.mock import Mock

from django.core.management.base import BaseCommand

from commcare_connect.coverage.data_access import CoverageDataAccess
from commcare_connect.labs.integrations.connect.cli import TokenManager

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Test loading coverage data for an opportunity using stored OAuth tokens"

    def add_arguments(self, parser):
        parser.add_argument(
            "--opportunity-id",
            type=int,
            default=575,
            help="Opportunity ID to load coverage data for (default: 575)",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Enable verbose debug logging",
        )
        parser.add_argument(
            "--skip-visits",
            action="store_true",
            help="Skip fetching user visits (test DUs only)",
        )
        parser.add_argument(
            "--commcare-token",
            type=str,
            help="CommCare OAuth access token (alternative to token file)",
        )

    def handle(self, *args, **options):
        opportunity_id = options["opportunity_id"]
        verbose = options["verbose"]
        skip_visits = options["skip_visits"]

        if verbose:
            logging.basicConfig(level=logging.DEBUG)
            logger.setLevel(logging.DEBUG)
        else:
            logging.basicConfig(level=logging.INFO)

        self.stdout.write(self.style.SUCCESS(f"\nTesting Coverage Data Load for Opportunity {opportunity_id}"))
        self.stdout.write("=" * 70)

        # Step 1: Load OAuth tokens
        self.stdout.write("\n[1/5] Loading OAuth Tokens...")
        try:
            # Load Connect OAuth token (from CLI token file)
            connect_token_mgr = TokenManager()
            connect_token_data = connect_token_mgr.load_token()

            if not connect_token_data:
                self.stdout.write(self.style.ERROR("Connect OAuth token not found!"))
                self.stdout.write("Run: python manage.py get_cli_token")
                return

            if connect_token_mgr.is_expired():
                self.stdout.write(self.style.ERROR("Connect OAuth token expired!"))
                self.stdout.write("Run: python manage.py get_cli_token")
                return

            self.stdout.write(
                self.style.SUCCESS(f"  Connect token loaded (expires: {connect_token_data.get('expires_at')})")
            )

            # Load CommCare OAuth token
            commcare_token_provided = options.get("commcare_token")

            if commcare_token_provided:
                # Use token provided via command line
                commcare_token_data = {
                    "access_token": commcare_token_provided,
                    "expires_at": (datetime.now() + timedelta(hours=1)).isoformat(),  # Assume 1 hour validity
                }
                self.stdout.write(self.style.SUCCESS("  CommCare token provided via --commcare-token"))
            else:
                # Load from separate file
                from pathlib import Path

                commcare_token_file = Path.home() / ".commcare-connect" / "commcare_token.json"
                commcare_token_mgr = TokenManager(str(commcare_token_file))
                commcare_token_data = commcare_token_mgr.load_token()

                if not commcare_token_data:
                    self.stdout.write(self.style.ERROR("CommCare OAuth token not found!"))
                    self.stdout.write(f"Expected location: {commcare_token_file}")
                    self.stdout.write("Options:")
                    self.stdout.write("  1. Use --commcare-token <token> to provide token directly")
                    self.stdout.write("  2. Get token from browser at /coverage/token-status/")
                    self.stdout.write("  3. Run: python manage.py export_commcare_token --session-key <key>")
                    return

                if commcare_token_mgr.is_expired():
                    self.stdout.write(self.style.ERROR("CommCare OAuth token expired!"))
                    return

                self.stdout.write(
                    self.style.SUCCESS(f"  CommCare token loaded (expires: {commcare_token_data.get('expires_at')})")
                )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to load tokens: {e}"))
            logger.exception("Token load error:")
            return

        # Step 2: Create mock request with tokens
        self.stdout.write("\n[2/5] Creating mock request...")
        from datetime import datetime

        mock_request = Mock()
        mock_request.session = {
            "labs_oauth": {
                "access_token": connect_token_data.get("access_token"),
                "expires_at": datetime.fromisoformat(connect_token_data.get("expires_at")).timestamp(),
            },
            "commcare_oauth": {
                "access_token": commcare_token_data.get("access_token"),
                "expires_at": datetime.fromisoformat(commcare_token_data.get("expires_at")).timestamp(),
            },
        }
        mock_request.labs_context = {"opportunity_id": opportunity_id}
        self.stdout.write(self.style.SUCCESS("  Mock request created"))

        # Step 3: Fetch opportunity metadata
        self.stdout.write("\n[3/5] Fetching opportunity metadata...")
        try:
            data_access = CoverageDataAccess(mock_request)
            opp_data = data_access.get_opportunity_metadata()
            self.stdout.write(self.style.SUCCESS(f"  Opportunity: {opp_data.get('name')}"))
            self.stdout.write(f"  CommCare Domain: {data_access.commcare_domain}")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to fetch opportunity: {e}"))
            logger.exception("Full error:")
            return

        # Step 4: Fetch delivery units from CommCare
        self.stdout.write("\n[4/5] Fetching delivery units from CommCare...")
        try:
            du_cases = data_access.fetch_delivery_units_from_commcare()
            self.stdout.write(self.style.SUCCESS(f"  Fetched {len(du_cases)} delivery units"))

            if du_cases and verbose:
                sample_du = du_cases[0]
                self.stdout.write(f"\n  Sample DU keys: {list(sample_du.keys())}")
                self.stdout.write(f"  Sample DU case_id: {sample_du.get('case_id')}")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to fetch delivery units: {e}"))
            logger.exception("Full error:")
            return

        # Step 5: Fetch user visits from Connect
        if not skip_visits:
            self.stdout.write("\n[5/5] Fetching user visits from Connect...")
            try:
                visits_df = data_access.fetch_user_visits_from_connect()
                self.stdout.write(self.style.SUCCESS(f"  Fetched {len(visits_df)} user visits"))

                if len(visits_df) > 0:
                    self.stdout.write(f"  Columns: {list(visits_df.columns)}")

                    # Check for problematic form_json
                    if "form_json" in visits_df.columns:
                        self.stdout.write("\n  Checking form_json column...")

                        # Sample first few values
                        for idx, val in enumerate(visits_df["form_json"].head(5)):
                            self.stdout.write(
                                f"    Row {idx}: type={type(val).__name__}, value preview: {str(val)[:100]}"
                            )

                        # Find problematic rows
                        problem_rows = []
                        for idx, val in enumerate(visits_df["form_json"]):
                            if isinstance(val, str) and val:
                                try:
                                    json.loads(val)
                                except json.JSONDecodeError as e:
                                    problem_rows.append((idx, val, str(e)))
                                    if len(problem_rows) <= 3:  # Show first 3 problematic rows
                                        self.stdout.write(self.style.WARNING(f"\n    Problem at row {idx}: {str(e)}"))
                                        self.stdout.write(f"    Value: {val[:200]}")

                        if problem_rows:
                            self.stdout.write(
                                self.style.ERROR(f"\n  Found {len(problem_rows)} rows with invalid JSON")
                            )
                        else:
                            self.stdout.write(self.style.SUCCESS("  All form_json values are valid JSON"))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to fetch user visits: {e}"))
                logger.exception("Full error:")
                return
        else:
            self.stdout.write("\n[5/5] Skipping user visits (--skip-visits flag)")

        # Summary
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("Test completed successfully!"))
        self.stdout.write("\nSummary:")
        self.stdout.write(f"  Opportunity: {opp_data.get('name')}")
        self.stdout.write(f"  Delivery Units: {len(du_cases)}")
        if not skip_visits:
            self.stdout.write(f"  User Visits: {len(visits_df)}")
