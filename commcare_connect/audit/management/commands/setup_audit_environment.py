"""
Management command to set up audit environment using the Connect API facade.

This command provides an interactive way to:
1. Search for programs
2. Select opportunities
3. Choose field workers
4. Set audit parameters
5. Download audit data

This replaces the need for manual management commands and provides a foundation
for the future web UI.
"""

from datetime import date, datetime, timedelta
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from commcare_connect.audit.management.extractors.connect_api_facade import AuditParameters, ConnectAPIFacade


class Command(BaseCommand):
    help = "Interactive setup of audit environment using Connect API facade"

    def add_arguments(self, parser):
        parser.add_argument("--program-search", type=str, help="Search term for programs (name or ID)")
        parser.add_argument("--opportunity-id", type=int, help="Specific opportunity ID to audit")
        parser.add_argument(
            "--output-dir", type=str, default="data", help="Output directory for audit data (default: data)"
        )
        parser.add_argument(
            "--days-back", type=int, default=30, help="Number of days back to include in audit (default: 30)"
        )
        parser.add_argument("--sample-size", type=int, help="Limit number of visits to sample (for testing)")
        parser.add_argument("--include-flagged-only", action="store_true", help="Only include flagged visits")
        parser.add_argument("--include-test-data", action="store_true", help="Include test data in audit")
        parser.add_argument(
            "--auto-select-all-flws",
            action="store_true",
            help="Automatically select all field workers (non-interactive)",
        )

    def handle(self, *args, **options):
        self.stdout.write("🚀 Setting up audit environment...")

        # Initialize facade
        facade = ConnectAPIFacade()

        try:
            # Authenticate
            if not facade.authenticate():
                raise CommandError("❌ Failed to authenticate with data source")

            self.stdout.write("✅ Authentication successful")

            # Step 1: Find program/opportunity
            if options["opportunity_id"]:
                opportunity_id = options["opportunity_id"]
                self.stdout.write(f"📋 Using specified opportunity ID: {opportunity_id}")
            else:
                opportunity_id = self._select_opportunity(facade, options["program_search"])

            if not opportunity_id:
                raise CommandError("❌ No opportunity selected")

            # Step 2: Get field workers
            field_workers = facade.get_field_workers_by_opportunity(opportunity_id)
            if not field_workers:
                raise CommandError(f"❌ No field workers found for opportunity {opportunity_id}")

            self.stdout.write(f"👥 Found {len(field_workers)} field workers")

            # Step 3: Select field workers
            if options["auto_select_all_flws"]:
                selected_flw_ids = [fw.id for fw in field_workers]
                self.stdout.write(f"✅ Auto-selected all {len(selected_flw_ids)} field workers")
            else:
                selected_flw_ids = self._select_field_workers(field_workers)

            if not selected_flw_ids:
                raise CommandError("❌ No field workers selected")

            # Step 4: Set date range
            end_date = date.today()
            start_date = end_date - timedelta(days=options["days_back"])

            # Get actual date range from data
            actual_start, actual_end = facade.get_visit_date_range(opportunity_id)
            if actual_start > start_date:
                start_date = actual_start
            if actual_end < end_date:
                end_date = actual_end

            self.stdout.write(f"📅 Date range: {start_date} to {end_date}")

            # Step 5: Create audit parameters
            params = AuditParameters(
                opportunity_id=opportunity_id,
                flw_ids=selected_flw_ids,
                start_date=start_date,
                end_date=end_date,
                sample_size=options["sample_size"],
                include_flagged_only=options["include_flagged_only"],
                include_test_data=options["include_test_data"],
            )

            # Step 6: Preview visit counts
            self.stdout.write("📊 Getting visit count preview...")
            counts = facade.get_visit_count_preview(params)

            self.stdout.write("📈 Visit counts:")
            for status, count in counts.items():
                self.stdout.write(f"  {status}: {count:,}")

            if counts.get("total", 0) == 0:
                raise CommandError("❌ No visits found with the specified criteria")

            # Step 7: Confirm and download
            if not options["auto_select_all_flws"]:
                confirm = input(f"\n🤔 Download {counts['total']:,} visits? (y/N): ")
                if confirm.lower() != "y":
                    self.stdout.write("❌ Download cancelled")
                    return

            self.stdout.write("💾 Downloading audit data...")
            output_file = facade.download_audit_data(params, options["output_dir"])

            self.stdout.write(self.style.SUCCESS(f"✅ Audit data downloaded to: {output_file}"))

            # Step 8: Show next steps
            self._show_next_steps(output_file, params)

        except Exception as e:
            raise CommandError(f"❌ Error: {str(e)}")

        finally:
            facade.close()

    def _select_opportunity(self, facade: ConnectAPIFacade, search_query: str) -> int:
        """Interactive opportunity selection."""
        if search_query:
            self.stdout.write(f"🔍 Searching programs for: '{search_query}'")
            programs = facade.search_programs(search_query, limit=10)
        else:
            self.stdout.write("📋 Getting recent programs...")
            programs = facade.search_programs("", limit=10)

        if not programs:
            self.stdout.write("❌ No programs found")
            return None

        # Show programs
        self.stdout.write("\n📋 Available programs:")
        for i, program in enumerate(programs, 1):
            self.stdout.write(f"  {i}. {program.name} (ID: {program.id})")
            self.stdout.write(f"     {program.description[:100]}...")

        # Select program
        try:
            choice = int(input(f"\nSelect program (1-{len(programs)}): ")) - 1
            selected_program = programs[choice]
        except (ValueError, IndexError):
            self.stdout.write("❌ Invalid selection")
            return None

        # Get opportunities for selected program
        self.stdout.write(f"🔍 Getting opportunities for: {selected_program.name}")
        opportunities = facade.get_opportunities_by_program(selected_program.id)

        if not opportunities:
            self.stdout.write("❌ No opportunities found for this program")
            return None

        # Show opportunities
        self.stdout.write("\n🎯 Available opportunities:")
        for i, opp in enumerate(opportunities, 1):
            test_indicator = " [TEST]" if opp.is_test else ""
            active_indicator = " [INACTIVE]" if not opp.active else ""
            self.stdout.write(f"  {i}. {opp.name} (ID: {opp.id}){test_indicator}{active_indicator}")
            if opp.deliver_app_domain and opp.deliver_app_cc_app_id:
                self.stdout.write(f"     App: {opp.deliver_app_domain}/{opp.deliver_app_cc_app_id}")

        # Select opportunity
        try:
            choice = int(input(f"\nSelect opportunity (1-{len(opportunities)}): ")) - 1
            return opportunities[choice].id
        except (ValueError, IndexError):
            self.stdout.write("❌ Invalid selection")
            return None

    def _select_field_workers(self, field_workers: list) -> list:
        """Interactive field worker selection."""
        self.stdout.write("\n👥 Available field workers:")
        for i, fw in enumerate(field_workers, 1):
            last_active = fw.last_active.strftime("%Y-%m-%d") if fw.last_active else "Never"
            self.stdout.write(
                f"  {i}. {fw.name} (ID: {fw.id}) - " f"{fw.total_visits} visits, last active: {last_active}"
            )

        self.stdout.write("\nSelection options:")
        self.stdout.write("  'all' - Select all field workers")
        self.stdout.write("  '1,3,5' - Select specific workers by number")
        self.stdout.write("  '1-5' - Select range of workers")

        selection = input("Select field workers: ").strip()

        if selection.lower() == "all":
            return [fw.id for fw in field_workers]

        selected_ids = []

        try:
            # Handle comma-separated list
            if "," in selection:
                indices = [int(x.strip()) - 1 for x in selection.split(",")]
                selected_ids = [field_workers[i].id for i in indices if 0 <= i < len(field_workers)]

            # Handle range
            elif "-" in selection:
                start, end = map(int, selection.split("-"))
                indices = range(start - 1, end)
                selected_ids = [field_workers[i].id for i in indices if 0 <= i < len(field_workers)]

            # Handle single number
            else:
                index = int(selection) - 1
                if 0 <= index < len(field_workers):
                    selected_ids = [field_workers[index].id]

        except (ValueError, IndexError):
            self.stdout.write("❌ Invalid selection")
            return []

        if selected_ids:
            selected_names = [fw.name for fw in field_workers if fw.id in selected_ids]
            self.stdout.write(f"✅ Selected {len(selected_ids)} field workers: {', '.join(selected_names)}")

        return selected_ids

    def _show_next_steps(self, output_file: str, params: AuditParameters):
        """Show next steps after data download."""
        self.stdout.write("\n🎉 Setup complete! Next steps:")
        self.stdout.write(f"1. Review the downloaded data: {output_file}")
        self.stdout.write("2. Create an audit session:")
        self.stdout.write(f"   python manage.py load_audit_uservisits --domain <domain> --app-id <app-id>")
        self.stdout.write("3. Or use the web interface to create an audit session")
        self.stdout.write("\n📊 Audit parameters:")
        self.stdout.write(f"  Opportunity ID: {params.opportunity_id}")
        self.stdout.write(f"  Field Workers: {len(params.flw_ids)} selected")
        self.stdout.write(f"  Date Range: {params.start_date} to {params.end_date}")
        if params.sample_size:
            self.stdout.write(f"  Sample Size: {params.sample_size}")
        if params.include_flagged_only:
            self.stdout.write("  Flagged visits only: Yes")
        if params.include_test_data:
            self.stdout.write("  Include test data: Yes")
