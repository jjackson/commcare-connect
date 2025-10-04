#!/usr/bin/env python3
"""
Test script for Phase 1 audit implementation
Run this to verify the basic structure is working
"""


def test_imports():
    """Test that all our modules can be imported"""
    try:
        from commcare_connect.audit.commcare_extractor import CommCareExtractor
        from commcare_connect.audit.helpers import get_approved_visits_for_audit
        from commcare_connect.audit.models import AuditResult, AuditSession
        from commcare_connect.audit.views import AuditSessionListView

        print("✓ All imports successful")
        return True
    except ImportError as e:
        print(f"X Import error: {e}")
        return False


def test_model_structure():
    """Test that models have expected fields and methods"""
    from commcare_connect.audit.models import AuditResult, AuditSession

    # Check AuditSession fields
    expected_fields = [
        "auditor_username",
        "flw_username",
        "opportunity_name",
        "domain",
        "app_id",
        "start_date",
        "end_date",
        "status",
        "overall_result",
        "notes",
        "kpi_notes",
    ]

    session_fields = [f.name for f in AuditSession._meta.fields]
    for field in expected_fields:
        if field not in session_fields:
            print(f"❌ Missing field in AuditSession: {field}")
            return False

    # Check AuditResult fields
    expected_fields = ["audit_session", "visit", "result", "notes"]
    result_fields = [f.name for f in AuditResult._meta.fields]
    for field in expected_fields:
        if field not in result_fields:
            print(f"❌ Missing field in AuditResult: {field}")
            return False

    print("✅ Model structure looks good")
    return True


def test_management_commands():
    """Test that management commands exist"""
    import os
    from pathlib import Path

    commands_dir = Path(__file__).parent / "management" / "commands"

    expected_commands = ["load_audit_data.py", "clear_audit_data.py"]

    for command in expected_commands:
        if not (commands_dir / command).exists():
            print(f"❌ Missing management command: {command}")
            return False

    print("✅ Management commands exist")
    return True


def test_commcare_extractor():
    """Test CommCare extractor basic functionality"""
    try:
        from commcare_connect.audit.commcare_extractor import CommCareExtractor

        # Test initialization (should fail without credentials, but that's expected)
        try:
            extractor = CommCareExtractor(domain="test")
        except ValueError as e:
            if "Missing required credentials" in str(e):
                print("✅ CommCare extractor properly validates credentials")
                return True
            else:
                print(f"❌ Unexpected error: {e}")
                return False

        print("⚠️ CommCare extractor initialized without credentials (unexpected)")
        return False

    except Exception as e:
        print(f"❌ Error testing CommCare extractor: {e}")
        return False


def main():
    """Run all tests"""
    print("Testing Phase 1 Audit Implementation")
    print("=" * 50)

    tests = [test_imports, test_model_structure, test_management_commands, test_commcare_extractor]

    passed = 0
    total = len(tests)

    for test in tests:
        print(f"\n📋 Running {test.__name__}...")
        if test():
            passed += 1
        else:
            print(f"   Test failed!")

    print("\n" + "=" * 50)
    print(f"📊 Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 Phase 1 implementation looks good!")
        print("\n💡 Next steps:")
        print("   1. Run migrations: python manage.py makemigrations audit")
        print("   2. Apply migrations: python manage.py migrate")
        print("   3. Test data loading: python manage.py load_audit_data --help")
        print("   4. Access audit interface: /audit/")
    else:
        print("❌ Some tests failed. Please fix issues before proceeding.")


if __name__ == "__main__":
    main()
