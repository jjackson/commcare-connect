#!/usr/bin/env python
"""
Audit Integration Workflow Script

This script runs the complete audit creation workflow end-to-end with REAL data:
1. Clear database and confirm empty
2. Search for "readers" opportunities
3. Select the top 2 projects with >1000 visits
4. Create a per-FLW audit with last 10 visits per FLW
5. Generate preview
6. Create the audit sessions

This is NOT a test - it's an integration validation script that works with real data.

Requirements:
- Superset connection configured (SUPERSET_* env vars)
- CommCare credentials (COMMCARE_USERNAME, COMMCARE_API_KEY) for image downloads
- Django settings configured

Usage:
    python commcare_connect/audit/run_audit_integration.py
"""

import os
import sys

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Set Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402

from commcare_connect.audit.management.extractors.connect_api_facade import ConnectAPIFacade  # noqa: E402
from commcare_connect.audit.models import AuditSession  # noqa: E402
from commcare_connect.audit.services.audit_creator import create_audit_sessions, preview_audit_sessions  # noqa: E402
from commcare_connect.audit.services.database_manager import reset_audit_database  # noqa: E402
from commcare_connect.opportunity.models import Opportunity, UserVisit  # noqa: E402

User = get_user_model()


def clear_database():
    """Clear all audit-related data from the database using the same function as the UI."""
    print("\n" + "=" * 80)
    print("STEP 1: CLEARING DATABASE")
    print("=" * 80)

    # Count before deletion
    counts_before = {
        "opportunities": Opportunity.objects.count(),
        "visits": UserVisit.objects.count(),
        "audit_sessions": AuditSession.objects.count(),
        "users_with_visits": len(list(UserVisit.objects.values_list("user_id", flat=True).distinct())),
    }

    print("\nBefore deletion:")
    for key, count in counts_before.items():
        print(f"  {key}: {count}")

    # Use the same reset function that the UI uses
    deleted = reset_audit_database()

    print("\nDeleted:")
    for key, count in deleted.items():
        print(f"  {key}: {count}")


def confirm_empty():
    """Confirm the database is empty."""
    counts = {
        "opportunities": Opportunity.objects.count(),
        "visits": UserVisit.objects.count(),
        "audit_sessions": AuditSession.objects.count(),
    }

    print("\nAfter deletion:")
    for key, count in counts.items():
        print(f"  {key}: {count}")

    all_zero = all(count == 0 for count in counts.values())
    if all_zero:
        print("\n[OK] Database is empty and ready for integration test")
    else:
        print("\n[ERROR] WARNING: Database is not completely empty!")
        return False

    return True


def search_readers_opportunities(facade: ConnectAPIFacade):
    """Search for 'readers' opportunities and select top 1 with >1000 visits."""
    print("\n" + "=" * 80)
    print("STEP 2: SEARCHING FOR READERS OPPORTUNITIES")
    print("=" * 80)

    print("\nSearching for 'readers' opportunities...")
    opportunities = facade.search_opportunities("readers", limit=50)

    print(f"Found {len(opportunities)} opportunities matching 'readers'")

    # Filter for high-volume opportunities (>1000 visits)
    high_volume = [opp for opp in opportunities if opp.visit_count and opp.visit_count > 1000]

    if len(high_volume) < 1:
        print("\n[ERROR] No opportunities found with >1000 visits")
        return None

    # Select top 1
    selected = high_volume[:1]

    print(f"\n[OK] Selected {len(selected)} opportunity:")
    for opp in selected:
        print(f"  - ID {opp.id}: {opp.name}")
        print(f"    Visits: {opp.visit_count}")
        print(f"    Domain: {opp.deliver_app_domain}")

    return selected


def generate_preview(facade: ConnectAPIFacade, opportunity_ids: list[int], count_per_flw: int = 10):
    """Generate preview of FLW counts and visit numbers using the audit creation service."""
    print("\n" + "=" * 80)
    print("STEP 3: GENERATING PREVIEW")
    print("=" * 80)

    print(f"\nGenerating preview for last {count_per_flw} visits per FLW...")

    # Build criteria for preview (same format as creation)
    criteria = {
        "type": "last_n_per_flw",
        "granularity": "per_flw",
        "countPerFlw": count_per_flw,
    }

    # Use the same service that the UI uses
    result = preview_audit_sessions(
        facade=facade,
        opportunity_ids=opportunity_ids,
        criteria=criteria,
    )

    if not result.success:
        print(f"\n[ERROR] {result.error}")
        return []

    # Display preview results
    for preview in result.preview_data:
        print(f"\n[OK] Opportunity: {preview['opportunity_name']} (ID: {preview['opportunity_id']})")
        print(f"  Total FLWs: {preview['total_flws']}")
        print(f"  Total visits: {preview['total_visits']}")
        print(f"  Avg visits per FLW: {preview['avg_visits_per_flw']}")
        print(f"  Sessions to create: {preview['sessions_to_create']}")

    return result.preview_data


def create_per_flw_audits(
    facade: ConnectAPIFacade,
    opportunity_ids: list[int],
    count_per_flw: int = 10,
    auditor_username: str = "integration_test",
):
    """Create per-FLW audit sessions with last N visits per FLW using the audit creation service."""
    print("\n" + "=" * 80)
    print("STEP 4: CREATING PER-FLW AUDITS")
    print("=" * 80)

    # Build criteria for per-FLW audit
    criteria = {
        "type": "last_n_per_flw",
        "granularity": "per_flw",
        "countPerFlw": count_per_flw,
    }

    print(f"\nCreating per-FLW audits with last {count_per_flw} visits per FLW...")

    # Use the same service that the UI uses
    result = create_audit_sessions(
        facade=facade,
        opportunity_ids=opportunity_ids,
        criteria=criteria,
        auditor_username=auditor_username,
        limit_flws=None,  # No limit - run full workflow like UI
    )

    if not result.success:
        print(f"\n[ERROR] {result.error}")
        return []

    # Print results
    print(f"\n[OK] Created {result.sessions_created} audit sessions")

    # Print final stats
    stats = result.stats
    print("\n" + "=" * 80)
    print("FINAL STATISTICS")
    print("=" * 80)
    print(f"Opportunities created: {stats.get('opportunities_created', 0)}")
    print(f"Users created: {stats.get('users_created', 0)}")
    print(f"Visits created: {stats.get('visits_created', 0)}")
    print(f"Audit sessions created: {stats.get('audit_sessions_created', 0)}")
    print(f"Attachments downloaded: {stats.get('attachments_downloaded', 0)}")

    return result.sessions


def verify_audits(sessions: list):
    """Verify that audits were created correctly."""
    print("\n" + "=" * 80)
    print("STEP 5: VERIFICATION")
    print("=" * 80)

    print(f"\nVerifying {len(sessions)} audit sessions...")

    all_valid = True

    for session in sessions:
        # Refresh from database
        session.refresh_from_db()

        # Check status
        if session.status != AuditSession.Status.IN_PROGRESS:
            print(f"  [ERROR] Session {session.id}: Wrong status ({session.status})")
            all_valid = False
            continue

        # Count visits explicitly assigned to this session
        visit_count = session.visits.count()

        if visit_count == 0:
            print(f"  [ERROR] Session {session.id}: No visits found")
            all_valid = False
        else:
            print(f"  [OK] Session {session.id} ({session.flw_username}): {visit_count} visits")

    if all_valid:
        print("\n[OK] All audit sessions created successfully!")
    else:
        print("\n[ERROR] Some audit sessions have issues")

    return all_valid


def main():
    """Run the complete integration workflow."""
    print("\n" + "=" * 80)
    print("AUDIT INTEGRATION WORKFLOW")
    print("=" * 80)
    print("\nThis script will:")
    print("1. Clear the database")
    print("2. Search for 'readers' opportunities")
    print("3. Select top 1 project with >1000 visits")
    print("4. Create per-FLW audits with last 2 visits per FLW")
    print("5. Download images (if credentials configured)")
    print("6. Verify the results")

    # Initialize facade
    facade = ConnectAPIFacade()
    if not facade.authenticate():
        print("\n[ERROR] Failed to authenticate with data source")
        print("Check SUPERSET_* environment variables")
        return 1

    try:
        # Step 1: Clear database
        clear_database()
        if not confirm_empty():
            return 1

        # Step 2: Search for opportunities
        selected_opportunities = search_readers_opportunities(facade)
        if not selected_opportunities:
            print("\n[ERROR] Could not find suitable opportunities")
            return 1

        opportunity_ids = [opp.id for opp in selected_opportunities]

        # Step 3: Generate preview
        generate_preview(facade, opportunity_ids, count_per_flw=2)

        # Step 4: Create per-FLW audits
        sessions = create_per_flw_audits(facade, opportunity_ids, count_per_flw=2)

        # Step 5: Verify
        success = verify_audits(sessions)

        # Final message
        print("\n" + "=" * 80)
        if success:
            print("[SUCCESS] INTEGRATION WORKFLOW COMPLETED SUCCESSFULLY")
        else:
            print("[ERROR] INTEGRATION WORKFLOW COMPLETED WITH ERRORS")
        print("=" * 80)

        return 0 if success else 1

    finally:
        facade.close()


if __name__ == "__main__":
    sys.exit(main())
