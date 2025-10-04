"""
Management command to load data from Superset using the new extractor architecture.
"""
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from commcare_connect.audit.management.extractors.sql_queries import (
    SQL_ALL_DATA_QUERY,
    SQL_CONNECT_LOCATION_ANALYSIS,
    SQL_FAKE_DATA_PARTY,
)
from commcare_connect.audit.management.extractors.superset_extractor import SupersetExtractor


class Command(BaseCommand):
    help = "Load data from Superset using predefined SQL queries"

    def add_arguments(self, parser):
        parser.add_argument(
            "--query",
            type=str,
            choices=["location", "fake_data", "all_data"],
            default="location",
            help="Which predefined query to execute (default: location)",
        )
        parser.add_argument(
            "--output-dir", type=str, default="data", help="Output directory for CSV files (default: data)"
        )
        parser.add_argument("--filename", type=str, help="Custom filename for output (without .csv extension)")
        parser.add_argument("--resume", action="store_true", help="Resume from existing file if it exists")
        parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    def handle(self, *args, **options):
        # Validate environment variables
        required_env_vars = ["SUPERSET_URL", "SUPERSET_USERNAME", "SUPERSET_PASSWORD"]
        missing_vars = [var for var in required_env_vars if not os.getenv(var)]

        if missing_vars:
            raise CommandError(
                f"Missing required environment variables: {', '.join(missing_vars)}\n"
                "Please set these in your .env file or environment."
            )

        # Select query based on argument
        query_map = {
            "location": ("Connect Location Analysis", SQL_CONNECT_LOCATION_ANALYSIS),
            "fake_data": ("Fake Data Party", SQL_FAKE_DATA_PARTY),
            "all_data": ("All Data Query", SQL_ALL_DATA_QUERY),
        }

        query_name, sql_query = query_map[options["query"]]

        # Set up output file
        output_dir = Path(options["output_dir"])
        output_dir.mkdir(exist_ok=True)

        if options["filename"]:
            output_file = output_dir / f"{options['filename']}.csv"
        else:
            # Generate filename based on query type
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = output_dir / f"superset_{options['query']}_{timestamp}.csv"

        self.stdout.write(f"🚀 Starting Superset data extraction...")
        self.stdout.write(f"📋 Query: {query_name}")
        self.stdout.write(f"📁 Output: {output_file}")

        if options["resume"] and output_file.exists():
            self.stdout.write(f"🔄 Resume mode enabled - will continue from existing file")

        try:
            # Initialize extractor
            extractor = SupersetExtractor()

            # Authenticate
            if not extractor.authenticate():
                raise CommandError("❌ Authentication failed")

            self.stdout.write("✅ Authentication successful")

            # Execute query with file output for memory efficiency
            result = extractor.execute_query(
                sql_query=sql_query, verbose=options["verbose"], output_file=str(output_file), resume=options["resume"]
            )

            if result is not None:
                # result is a summary DataFrame when using output_file
                total_rows = result.iloc[0]["total_rows"] if len(result) > 0 else 0
                self.stdout.write(self.style.SUCCESS(f"✅ Successfully extracted {total_rows:,} rows to {output_file}"))
            else:
                raise CommandError("❌ Query execution failed - no data returned")

        except Exception as e:
            raise CommandError(f"❌ Error during extraction: {str(e)}")

        finally:
            # Clean up
            if "extractor" in locals():
                extractor.close()
                self.stdout.write("🔚 Extractor closed")

        self.stdout.write(self.style.SUCCESS(f"🎉 Data extraction completed successfully!"))
