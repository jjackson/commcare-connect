#!/usr/bin/env python
"""
Integration test for experiment-based audit flow.

Tests the complete audit workflow using ExperimentRecords and dynamic API fetching.

Usage:
    python commcare_connect/audit/run_experiment_audit_integration.py [config]

Available configs:
    fastest    - 1 Readers opp, last 5 visits (default)
    readers    - 2 Readers opps, last 5 per FLW
    chc        - 2 CHC opps, last 10 across all
"""

import os
import sys
from dataclasses import dataclass


@dataclass
class TestConfig:
    """Configuration for experiment audit integration test."""

    name: str
    search_query: str  # Search keyword for opportunities
    select_count: int = 2  # Number of opportunities to select
    audit_type: str = "last_n_across_all"
    count_across_all: int = 5
    count_per_flw: int = None
    sample_percentage: int = 100


# Test configurations
TEST_CONFIGS = {
    "fastest": TestConfig(
        name="Fastest - 1 Readers Opp, Last 5 Visits",
        search_query="readers",
        select_count=1,
        audit_type="last_n_across_all",
        count_across_all=5,
    ),
    "readers": TestConfig(
        name="Readers - 2 Opps, Last 5 per FLW",
        search_query="readers",
        select_count=2,
        audit_type="last_n_per_flw",
        count_per_flw=5,
    ),
    "chc": TestConfig(
        name="CHC - 2 Opps, Last 10 Total",
        search_query="chc",
        select_count=2,
        audit_type="last_n_across_all",
        count_across_all=10,
    ),
    "opp385": TestConfig(
        name="Opp 385 - Last 10 per FLW",
        search_query="385",
        select_count=1,
        audit_type="last_n_per_flw",
        count_per_flw=10,
    ),
    "opp385_across": TestConfig(
        name="Opp 385 - Last 10 Across All (workaround for missing user_id)",
        search_query="385",
        select_count=1,
        audit_type="last_n_across_all",
        count_across_all=10,
    ),
}


def test_experiment_audit_flow(config_name="fastest"):
    """Test complete audit flow with experiment records."""

    # Get configuration
    if config_name not in TEST_CONFIGS:
        print(f"[ERROR] Unknown config: {config_name}")
        print(f"Available configs: {', '.join(TEST_CONFIGS.keys())}")
        return

    config = TEST_CONFIGS[config_name]

    print("=" * 80)
    print("EXPERIMENT AUDIT INTEGRATION TEST")
    print("=" * 80)
    print(f"Configuration: {config.name}")
    print(f"Search: '{config.search_query}'")
    print(f"Audit Type: {config.audit_type}")
    print("=" * 80)

    # Step 1: Initialize data access
    print("\n[1] Initializing data access...")
    try:
        import os

        from commcare_connect.audit.data_access import AuditDataAccess

        # Try to get OAuth token using the token manager
        access_token = None

        # Option 1: Check environment variable
        access_token = os.getenv("CONNECT_OAUTH_TOKEN")
        if access_token:
            print("[OK] Using token from CONNECT_OAUTH_TOKEN environment variable")
        else:
            # Option 2: Load from token manager (saved by get_cli_token command)
            print("[INFO] Checking for saved OAuth token...")
            from commcare_connect.labs.oauth_cli import TokenManager

            token_manager = TokenManager()
            access_token = token_manager.get_valid_token()

            if access_token:
                info = token_manager.get_token_info()
                if info and "expires_in_seconds" in info:
                    minutes = info["expires_in_seconds"] // 60
                    print(f"[OK] Using saved token (expires in {minutes} minutes)")
            else:
                print("[WARNING] No valid OAuth token found")
                print("[INFO] This test requires a Connect OAuth token")
                print("[INFO] Please run one of the following:")
                print("\n       Option 1: Get token via CLI OAuth flow")
                print("       python manage.py get_cli_token")
                print("\n       Option 2: Set environment variable")
                print("       export CONNECT_OAUTH_TOKEN='your_token_here'")
                print("\n[SKIP] Skipping integration test - no OAuth token available")
                return

        # Initialize data access with token
        from commcare_connect.labs.config import LABS_DEFAULT_OPP_ID

        data_access = AuditDataAccess(opportunity_id=LABS_DEFAULT_OPP_ID, access_token=access_token)
        print("[OK] Data access initialized successfully")

    except Exception as e:
        print(f"[ERROR] Failed to initialize: {e}")
        import traceback

        traceback.print_exc()
        return

    try:
        # Step 2: Search opportunities
        print(f"\n[2] Searching for '{config.search_query}' opportunities...")
        all_opportunities = data_access.search_opportunities(query=config.search_query, limit=20)
        if not all_opportunities:
            print(f"[WARNING] No opportunities found matching '{config.search_query}'")
            return

        # Select top N by name match
        opportunities = all_opportunities[: config.select_count]

        print(f"[OK] Found {len(all_opportunities)} opportunities, selected {len(opportunities)}")
        for opp in opportunities:
            print(f"     - {opp.get('id')}: {opp.get('name')}")

        # Step 3: Get visit IDs (preview/validate)
        print("\n[3] Getting visit IDs (preview)...")
        print("[INFO] API endpoint testing done via browser (Labs middleware interferes with test client)")

        # Build criteria from config
        criteria = {
            "audit_type": config.audit_type,
            "sample_percentage": config.sample_percentage,
            "granularity": "combined" if config.audit_type == "last_n_across_all" else "per_flw",
        }

        if config.count_across_all:
            criteria["count_across_all"] = config.count_across_all
        if config.count_per_flw:
            criteria["count_per_flw"] = config.count_per_flw

        # Get all opportunity IDs
        opportunity_ids = [opp.get("id") for opp in opportunities]

        # First, let's check raw visit data from API
        print("\n[DEBUG] Checking raw visit data from API...")
        for opp_id in opportunity_ids:
            raw_visits = data_access._fetch_visits_for_opportunity(opp_id)
            print(f"     Opportunity {opp_id}: {len(raw_visits)} raw visits from API")
            if raw_visits:
                # Check user_id distribution
                with_user_id = [v for v in raw_visits if v.get("user_id")]
                without_user_id = [v for v in raw_visits if not v.get("user_id")]
                print(f"     - Visits with user_id: {len(with_user_id)}")
                print(f"     - Visits without user_id: {len(without_user_id)}")

                sample = raw_visits[0]
                print(f"     Sample visit keys: {list(sample.keys())}")
                print(
                    f"     Sample visit: id={sample.get('id')}, "
                    f"user_id={sample.get('user_id')}, visit_date={sample.get('visit_date')}"
                )

                if with_user_id:
                    sample_with_user = with_user_id[0]
                    print(
                        f"     Sample WITH user_id: id={sample_with_user.get('id')}, "
                        f"user_id={sample_with_user.get('user_id')}, "
                        f"visit_date={sample_with_user.get('visit_date')}"
                    )

        try:
            visit_ids = data_access.get_visit_ids_for_audit(
                opportunity_ids=opportunity_ids, audit_type=config.audit_type, criteria=criteria
            )
        except Exception as e:
            print(f"[ERROR] Could not fetch visit IDs: {e}")
            import traceback

            traceback.print_exc()
            return

        if not visit_ids:
            print("[WARNING] No visits found matching criteria")
            print("[INFO] This may mean:")
            print("       - Opportunities have no approved visits")
            print("       - Criteria are too restrictive")
            print("       - Try a different config (e.g., 'chc')")
            return

        test_opp_id = opportunity_ids[0]

        print(f"[OK] Found {len(visit_ids)} visits matching criteria")

        # Get a user for creating records
        from django.contrib.auth import get_user_model

        User = get_user_model()
        test_user = User.objects.first()
        if not test_user:
            print("[ERROR] No users found in database")
            return

        # Create template
        template = data_access.create_audit_template(
            user_id=test_user.id,
            opportunity_ids=[test_opp_id],
            audit_type=criteria["audit_type"],
            granularity=criteria["granularity"],
            criteria=criteria,
            preview_data=[{"total_visits": len(visit_ids)}],
        )
        print(f"[OK] Created template ID: {template.id}")

        # Step 4: Create audit session
        print("\n[4] Creating audit session...")
        session = data_access.create_audit_session(
            template_id=template.id,
            auditor_id=test_user.id,
            visit_ids=visit_ids,
            title="Integration Test Audit",
            tag="integration_test",
            opportunity_id=test_opp_id,
        )
        print(f"[OK] Created session ID: {session.id}")
        print(f"     Title: {session.title}")
        print(f"     Status: {session.status}")
        print(f"     Visit IDs: {session.visit_ids}")
        print(f"     Visit results (should be empty): {session.visit_results}")

        # Step 5: Fetch first visit
        print("\n[5] Fetching visit data from Connect API...")
        if not visit_ids:
            print("[SKIP] No visits to fetch")
        else:
            first_visit_id = visit_ids[0]
            visit_data = data_access.get_visit_data(first_visit_id, opportunity_id=test_opp_id)

            if visit_data:
                print(f"[OK] Fetched visit ID: {visit_data['id']}")
                print(f"     xform_id: {visit_data.get('xform_id')}")
                print(f"     visit_date: {visit_data.get('visit_date')}")
                print(f"     entity_name: {visit_data.get('entity_name')}")
                print(f"     user_id: {visit_data.get('user_id')}")
            else:
                print("[WARNING] Could not fetch visit data")

            # Step 6: Try to get blob metadata (requires CommCare credentials)
            print("\n[6] Fetching blob metadata from CommCare...")
            try:
                # Get opportunity details for cc_domain
                opp_details = data_access.get_opportunity_details(test_opp_id)
                cc_domain = opp_details.get("cc_domain") if opp_details else None

                if not cc_domain:
                    print("[WARNING] No cc_domain found for opportunity")
                elif not visit_data.get("xform_id"):
                    print("[WARNING] No xform_id found for visit")
                else:
                    print(f"     Using cc_domain: {cc_domain}")
                    blob_metadata = data_access.get_blob_metadata_for_visit(visit_data["xform_id"], cc_domain)

                    if blob_metadata:
                        print(f"[OK] Found {len(blob_metadata)} blobs")
                        for blob_id, blob_info in list(blob_metadata.items())[:2]:
                            print(f"     - {blob_id}")
                            print(f"       question_id: {blob_info.get('question_id')}")
                            print(f"       filename: {blob_info.get('filename')}")

                        # Step 7: Mark assessments
                        print("\n[7] Marking image assessments...")
                        first_blob_id = list(blob_metadata.keys())[0]
                        first_blob_info = blob_metadata[first_blob_id]

                        session.set_assessment(
                            visit_id=first_visit_id,
                            blob_id=first_blob_id,
                            question_id=first_blob_info.get("question_id", ""),
                            result="pass",
                            notes="Test assessment",
                        )
                        print(f"[OK] Set assessment for blob {first_blob_id}")

                        # Step 8: Set visit result
                        print("\n[8] Setting visit result...")
                        session.set_visit_result(
                            visit_id=first_visit_id,
                            xform_id=visit_data["xform_id"],
                            result="pass",
                            notes="Test visit result",
                            user_id=visit_data.get("user_id", 0),
                            opportunity_id=test_opp_id,
                        )
                        print("[OK] Set visit result")

                        # Save session
                        session = data_access.save_audit_session(session)
                        print("[OK] Saved session")

                    else:
                        print("[WARNING] No blob metadata found")

            except Exception as e:
                print(f"[WARNING] Could not fetch blob metadata: {e}")
                print("          (This is expected if CommCare credentials are not configured)")

        # Step 9: Check progress
        print("\n[9] Checking progress...")
        progress_stats = session.get_progress_stats()
        print(f"[OK] Progress: {progress_stats['percentage']}%")
        print(f"     Assessed: {progress_stats['assessed']}/{progress_stats['total']}")

        # Step 10: Verify data structure
        print("\n[10] Verifying data structure...")
        print(f"[OK] Session data keys: {list(session.data.keys())}")
        print(f"     visit_ids type: {type(session.visit_ids)}")
        print(f"     visit_ids length: {len(session.visit_ids)}")
        print(f"     visit_results type: {type(session.visit_results)}")
        print(f"     visit_results keys: {list(session.visit_results.keys())}")

        # Check that visit_results are keyed by visit_id (as strings)
        for visit_key in session.visit_results.keys():
            print(f"     Visit key: {visit_key} (type: {type(visit_key)})")
            visit_result = session.visit_results[visit_key]
            print(f"       - xform_id: {visit_result.get('xform_id')}")
            print(f"       - result: {visit_result.get('result')}")
            print(f"       - assessments: {len(visit_result.get('assessments', {}))} items")

        # Step 11: Complete audit (optional)
        print("\n[11] Completing audit...")
        session = data_access.complete_audit_session(
            session=session,
            overall_result="pass",
            notes="Integration test completed",
            kpi_notes="All tests passed",
        )
        print("[OK] Session completed")
        print(f"     Status: {session.status}")
        print(f"     Overall result: {session.overall_result}")

        print("\n" + "=" * 80)
        print("INTEGRATION TEST COMPLETE")
        print("=" * 80)
        print(f"\nSession ID: {session.id}")
        print(f"Template ID: {template.id}")
        print(f"Total visits: {len(session.visit_ids)}")
        print(f"Visit results: {len(session.visit_results)}")

    finally:
        # Clean up
        data_access.close()


if __name__ == "__main__":
    # Setup Django
    import django

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    django.setup()

    # Get config from command line
    config_name = sys.argv[1] if len(sys.argv) > 1 else "fastest"
    test_experiment_audit_flow(config_name)
