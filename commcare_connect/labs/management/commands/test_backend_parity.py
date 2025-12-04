"""
Test that both analysis backends produce identical results.

This is a manual integration test that uses real data and OAuth.
Run with: python manage.py test_backend_parity --opportunity-id <ID>

Requires:
- Valid OAuth session (run labs server and log in first)
- Or use CLI token: python manage.py get_cli_token
"""

import logging

from django.core.management.base import BaseCommand

from commcare_connect.custom_analysis.chc_nutrition.analysis_config import CHC_NUTRITION_CONFIG
from commcare_connect.labs.analysis.pipeline import run_analysis_pipeline
from commcare_connect.labs.integrations.connect.cli import create_cli_request

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Test that python_redis and sql backends produce identical results"

    def add_arguments(self, parser):
        parser.add_argument(
            "--opportunity-id",
            type=int,
            required=True,
            help="Opportunity ID to test with",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Show detailed comparison",
        )

    def handle(self, *args, **options):
        opportunity_id = options["opportunity_id"]
        verbose = options["verbose"]

        self.stdout.write(f"\nTesting backend parity for opportunity {opportunity_id}")
        self.stdout.write("=" * 60)

        # Create request with CLI token
        self.stdout.write("\nCreating CLI request...")
        request = create_cli_request(opportunity_id)

        # Run with python_redis backend
        self.stdout.write("\n[1/2] Running with python_redis backend...")
        from django.conf import settings

        original_backend = getattr(settings, "LABS_ANALYSIS_BACKEND", "python_redis")

        try:
            settings.LABS_ANALYSIS_BACKEND = "python_redis"
            result_redis = run_analysis_pipeline(request, CHC_NUTRITION_CONFIG, opportunity_id)
            self.stdout.write(self.style.SUCCESS(f"  -> {len(result_redis.rows)} FLWs"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  -> Error: {e}"))
            return

        # Run with sql backend
        self.stdout.write("\n[2/2] Running with sql backend...")
        try:
            settings.LABS_ANALYSIS_BACKEND = "sql"
            result_sql = run_analysis_pipeline(request, CHC_NUTRITION_CONFIG, opportunity_id)
            self.stdout.write(self.style.SUCCESS(f"  -> {len(result_sql.rows)} FLWs"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  -> Error: {e}"))
            return
        finally:
            settings.LABS_ANALYSIS_BACKEND = original_backend

        # Compare results
        self.stdout.write("\nComparing results...")
        self.stdout.write("-" * 60)

        differences = self._compare_results(result_redis, result_sql, verbose)

        if differences:
            self.stdout.write(self.style.ERROR(f"\nFAILED: {len(differences)} differences found"))
            for diff in differences[:10]:  # Show first 10
                self.stdout.write(f"  - {diff}")
            if len(differences) > 10:
                self.stdout.write(f"  ... and {len(differences) - 10} more")
        else:
            self.stdout.write(self.style.SUCCESS("\nPASSED: Results are identical!"))

        # Summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("Summary:")
        self.stdout.write(f"  FLWs (redis):  {len(result_redis.rows)}")
        self.stdout.write(f"  FLWs (sql):    {len(result_sql.rows)}")
        self.stdout.write(f"  Differences:   {len(differences)}")

    def _compare_results(self, result_redis, result_sql, verbose: bool) -> list[str]:
        """Compare two FLWAnalysisResults and return list of differences."""
        differences = []

        # Compare row counts
        if len(result_redis.rows) != len(result_sql.rows):
            differences.append(f"Row count mismatch: redis={len(result_redis.rows)}, sql={len(result_sql.rows)}")

        # Build lookup by username
        redis_by_user = {row.username: row for row in result_redis.rows}
        sql_by_user = {row.username: row for row in result_sql.rows}

        # Check for missing users
        redis_users = set(redis_by_user.keys())
        sql_users = set(sql_by_user.keys())

        for user in redis_users - sql_users:
            differences.append(f"User {user} in redis but not sql")

        for user in sql_users - redis_users:
            differences.append(f"User {user} in sql but not redis")

        # Compare matching users
        for username in redis_users & sql_users:
            redis_row = redis_by_user[username]
            sql_row = sql_by_user[username]

            # Compare standard fields
            for field in ["total_visits", "approved_visits", "pending_visits", "rejected_visits", "flagged_visits"]:
                redis_val = getattr(redis_row, field, None)
                sql_val = getattr(sql_row, field, None)
                if redis_val != sql_val:
                    differences.append(f"{username}.{field}: redis={redis_val}, sql={sql_val}")

            # Compare custom fields
            redis_custom = redis_row.custom_fields or {}
            sql_custom = sql_row.custom_fields or {}

            all_keys = set(redis_custom.keys()) | set(sql_custom.keys())
            for key in all_keys:
                redis_val = redis_custom.get(key)
                sql_val = sql_custom.get(key)

                # Handle floating point comparison
                if isinstance(redis_val, float) and isinstance(sql_val, float):
                    if abs(redis_val - sql_val) > 0.001:
                        differences.append(f"{username}.custom_fields.{key}: redis={redis_val}, sql={sql_val}")
                elif redis_val != sql_val:
                    # Truncate long values
                    r_str = str(redis_val)[:50]
                    s_str = str(sql_val)[:50]
                    differences.append(f"{username}.custom_fields.{key}: redis={r_str}, sql={s_str}")

            if verbose and not differences:
                self.stdout.write(f"  {username}: OK")

        return differences
