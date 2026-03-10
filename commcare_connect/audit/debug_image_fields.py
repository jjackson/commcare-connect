#!/usr/bin/env python
"""
Debug script: inspect raw visit data to diagnose missing ORS/MUAC images.

Shows what the Connect API actually returns for the `images` blob column
vs what's in form_json for photo fields. Run this to determine whether
images exist as Connect blobs or only as CommCareHQ form attachments.

Usage:
    python commcare_connect/audit/debug_image_fields.py <opp_id> [limit]

Examples:
    python commcare_connect/audit/debug_image_fields.py 814
    python commcare_connect/audit/debug_image_fields.py 814 20
"""

import os
import sys


# Photo fields to look for in form_json
PHOTO_FIELDS_TO_CHECK = [
    # (form_json path using / separator, description)
    ("service_delivery/ors_group/ors_photo", "ORS filename"),
    ("service_delivery/ors_group/photo_link_ors", "ORS CommCareHQ URL"),
    ("service_delivery/muac_group/muac_display_group_1/muac_photo", "MUAC filename"),
    ("service_delivery/muac_group/muac_photo_link", "MUAC CommCareHQ URL"),
    ("anthropometric/upload_weight_image", "Scale filename"),
]


def _get_nested(data: dict, path: str):
    """Navigate nested dict using / separator path."""
    keys = path.split("/")
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _build_filename_map(data: dict, path: str = "") -> dict:
    """Replicates analysis_config._build_filename_map for local use."""
    SKIP_KEYS = frozenset({"@xmlns", "@name", "@uiVersion", "@version", "meta", "#type", "attachments"})
    result = {}
    if not isinstance(data, dict):
        return result
    for key, value in data.items():
        if key in SKIP_KEYS:
            continue
        current_path = f"{path}/{key}" if path else key
        if isinstance(value, str):
            result[value] = current_path
        elif isinstance(value, dict):
            result.update(_build_filename_map(value, current_path))
    return result


def debug_image_fields(opp_id: int, limit: int = 10):
    print("=" * 80)
    print(f"IMAGE FIELD DEBUG — Opportunity {opp_id}")
    print("=" * 80)

    # Get OAuth token
    print("\n[1] Getting OAuth token...")
    from commcare_connect.labs.integrations.connect.cli import TokenManager

    access_token = os.getenv("CONNECT_OAUTH_TOKEN")
    if access_token:
        print("[OK] Using CONNECT_OAUTH_TOKEN env var")
    else:
        token_manager = TokenManager()
        access_token = token_manager.get_valid_token()
        if access_token:
            print("[OK] Using saved token from TokenManager")
        else:
            print("[ERROR] No valid OAuth token. Run: python manage.py get_cli_token")
            return

    # Fetch raw visits
    print(f"\n[2] Fetching up to {limit} visits for opp {opp_id} (full form_json)...")

    from commcare_connect.audit.run_audit_integration import MockRequest
    from commcare_connect.audit.data_access import AuditDataAccess

    request = MockRequest(access_token=access_token, opportunity_id=opp_id)
    data_access = AuditDataAccess(opportunity_id=opp_id, request=request)

    try:
        # Use pipeline to get slim visits first to find IDs, then fetch full
        slim_visits = data_access.fetch_visits_slim(opportunity_id=opp_id)
        print(f"[OK] Total visits available: {len(slim_visits)}")

        if not slim_visits:
            print("[WARNING] No visits found for this opportunity")
            return

        # Take only the last `limit` visits
        sample_visits = slim_visits[-limit:]
        visit_ids = [v["id"] for v in sample_visits if v.get("id")]
        print(f"[OK] Inspecting last {len(visit_ids)} visits: {visit_ids}")

        # Fetch full visits with form_json
        full_visits = data_access.fetch_visits_for_ids(visit_ids, opportunity_id=opp_id)
        print(f"[OK] Fetched {len(full_visits)} visits with form_json")

    except Exception as e:
        print(f"[ERROR] Failed to fetch visits: {e}")
        import traceback
        traceback.print_exc()
        return
    finally:
        data_access.close()

    # Inspect each visit
    print("\n" + "=" * 80)
    print("VISIT INSPECTION")
    print("=" * 80)

    visits_with_connect_images = 0
    visits_with_ors_url = 0
    visits_with_muac_url = 0

    for i, visit in enumerate(full_visits):
        visit_id = visit.get("id")
        username = visit.get("username", "?")
        visit_date = visit.get("visit_date", "?")
        connect_images = visit.get("images", [])

        print(f"\n--- Visit {visit_id} | {username} | {visit_date} ---")

        # Show Connect blob images
        if connect_images:
            visits_with_connect_images += 1
            print(f"  Connect blobs ({len(connect_images)}):")
            for img in connect_images:
                print(f"    blob_id: {img.get('blob_id', '')[:30]}...")
                print(f"    name:    {img.get('name', '')}")
        else:
            print("  Connect blobs: NONE (images array is empty)")

        # Check form_json fields
        form_json = visit.get("form_json", {})
        form_data = form_json.get("form", form_json)

        print("  form_json photo fields:")
        any_found = False
        for path, label in PHOTO_FIELDS_TO_CHECK:
            value = _get_nested(form_data, path)
            if value:
                any_found = True
                truncated = str(value)[:80] + ("..." if len(str(value)) > 80 else "")
                print(f"    [{label}] {path}")
                print(f"      => {truncated}")
                if "photo_link_ors" in path and value:
                    visits_with_ors_url += 1
                if "muac_photo_link" in path and value:
                    visits_with_muac_url += 1
        if not any_found:
            print("    (none of the expected photo fields found)")

        # Show filename map keys that look like images
        filename_map = _build_filename_map(form_data)
        image_like = {v: k for k, v in filename_map.items() if k.endswith(".jpg") or k.endswith(".png") or k.endswith(".jpeg")}
        if image_like:
            print(f"  filename_map image entries ({len(image_like)}):")
            for path, filename in image_like.items():
                print(f"    {path} => '{filename}'")
            # Check if Connect blobs match any of these
            if connect_images:
                for img in connect_images:
                    blob_name = img.get("name", "")
                    mapped_path = filename_map.get(blob_name)
                    print(f"  MATCH CHECK: blob '{blob_name}' -> question_id = '{mapped_path}'")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Visits inspected:              {len(full_visits)}")
    print(f"Visits WITH Connect blobs:     {visits_with_connect_images}")
    print(f"Visits with ORS URL in form:   {visits_with_ors_url}")
    print(f"Visits with MUAC URL in form:  {visits_with_muac_url}")
    print()
    if visits_with_connect_images == 0 and visits_with_ors_url > 0:
        print("DIAGNOSIS: Images are CommCareHQ attachments ONLY, NOT in Connect blob system.")
        print("           The current audit pipeline cannot find them via blob_id.")
        print("           Need to use photo_link_ors / muac_photo_link from form_json.")
    elif visits_with_connect_images > 0:
        print("DIAGNOSIS: Connect blobs exist. Check if blob names match form_json photo fields.")
    else:
        print("DIAGNOSIS: No images found at all (no blobs, no ORS/MUAC URL fields).")
        print("           Check that the right opportunity ID is being used.")
    print("=" * 80)


if __name__ == "__main__":
    import django

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    django.setup()

    if len(sys.argv) < 2:
        print("Usage: python commcare_connect/audit/debug_image_fields.py <opp_id> [limit]")
        print("  opp_id : Connect opportunity ID to inspect")
        print("  limit  : number of recent visits to sample (default: 10)")
        sys.exit(1)

    opp_id = int(sys.argv[1])
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    debug_image_fields(opp_id, limit)
