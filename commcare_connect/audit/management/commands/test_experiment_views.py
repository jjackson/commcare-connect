"""
Management command to verify experiment-based audit views are properly configured.

Usage:
    python manage.py test_experiment_views
"""

from django.core.management.base import BaseCommand
from django.urls import resolve, reverse


class Command(BaseCommand):
    help = "Verify experiment-based audit views are properly configured"

    def handle(self, *args, **options):
        self.stdout.write("=" * 80)
        self.stdout.write(self.style.SUCCESS("EXPERIMENT VIEWS CONFIGURATION TEST"))
        self.stdout.write("=" * 80)

        errors = []
        warnings = []
        tests_passed = 0

        # Test 1: Import all views
        self.stdout.write("\n[1] Testing view imports...")
        try:
            from commcare_connect.audit import experiment_views

            views_to_check = [
                "ExperimentAuditListView",
                "ExperimentAuditDetailView",
                "ExperimentAuditResultUpdateView",
                "ExperimentAssessmentUpdateView",
                "ExperimentAuditCompleteView",
                "ExperimentAuditImageView",
                "ExperimentAuditCreateAPIView",
                "ExperimentAuditPreviewAPIView",
            ]

            for view_name in views_to_check:
                if hasattr(experiment_views, view_name):
                    self.stdout.write(f"    [OK] {view_name}")
                    tests_passed += 1
                else:
                    errors.append(f"Missing view: {view_name}")
                    self.stdout.write(self.style.ERROR(f"    [FAIL] {view_name} not found"))

            if not errors:
                self.stdout.write(self.style.SUCCESS("    All views imported successfully"))

        except ImportError as e:
            errors.append(f"Import error: {e}")
            self.stdout.write(self.style.ERROR(f"    [FAIL] Import failed: {e}"))

        # Test 2: Import models
        self.stdout.write("\n[2] Testing model imports...")
        try:
            from commcare_connect.audit.experiment_models import AuditSessionRecord, AuditTemplateRecord

            self.stdout.write("    [OK] AuditTemplateRecord")
            self.stdout.write("    [OK] AuditSessionRecord")
            tests_passed += 2
            self.stdout.write(self.style.SUCCESS("    All models imported successfully"))

        except ImportError as e:
            errors.append(f"Model import error: {e}")
            self.stdout.write(self.style.ERROR(f"    [FAIL] Import failed: {e}"))

        # Test 3: Import data access layer
        self.stdout.write("\n[3] Testing data access layer import...")
        try:
            from commcare_connect.audit.data_access import AuditDataAccess

            self.stdout.write("    [OK] AuditDataAccess")
            tests_passed += 1
            self.stdout.write(self.style.SUCCESS("    Data access layer imported successfully"))

        except ImportError as e:
            errors.append(f"Data access import error: {e}")
            self.stdout.write(self.style.ERROR(f"    [FAIL] Import failed: {e}"))

        # Test 4: Import blob API
        self.stdout.write("\n[4] Testing blob API import...")
        try:
            from commcare_connect.audit.blob_api import BlobMetadataAPI

            self.stdout.write("    [OK] BlobMetadataAPI")
            tests_passed += 1
            self.stdout.write(self.style.SUCCESS("    Blob API imported successfully"))

        except ImportError as e:
            errors.append(f"Blob API import error: {e}")
            self.stdout.write(self.style.ERROR(f"    [FAIL] Import failed: {e}"))

        # Test 5: Check URL patterns
        self.stdout.write("\n[5] Testing URL routes...")
        url_tests = [
            ("audit:experiment_session_list", "/audit/experiment/"),
            ("audit:experiment_session_detail", "/audit/experiment/1/", {"pk": 1}),
            ("audit:experiment_create", "/audit/experiment/api/create/"),
            ("audit:experiment_preview", "/audit/experiment/api/preview/"),
            ("audit:experiment_result_update", "/audit/experiment/api/1/result/update/", {"session_id": 1}),
            (
                "audit:experiment_assessment_update",
                "/audit/experiment/api/1/assessment/update/",
                {"session_id": 1},
            ),
            ("audit:experiment_complete", "/audit/experiment/api/1/complete/", {"session_id": 1}),
            ("audit:experiment_image", "/audit/experiment/image/test_blob/", {"blob_id": "test_blob"}),
        ]

        for url_name, expected_path, *kwargs in url_tests:
            try:
                kwargs_dict = kwargs[0] if kwargs else {}
                url = reverse(url_name, kwargs=kwargs_dict)

                # Verify it resolves
                resolve(url)

                self.stdout.write(f"    [OK] {url_name} -> {url}")
                tests_passed += 1

            except Exception as e:
                errors.append(f"URL error for {url_name}: {e}")
                self.stdout.write(self.style.ERROR(f"    [FAIL] {url_name}: {e}"))

        if len(errors) == 0:
            self.stdout.write(self.style.SUCCESS("    All URL routes configured correctly"))

        # Test 6: Check ExperimentRecord base
        self.stdout.write("\n[6] Testing ExperimentRecord integration...")
        try:
            from commcare_connect.labs.models import ExperimentRecord

            self.stdout.write("    [OK] ExperimentRecord base model available")
            tests_passed += 1

            # Check that proxy models inherit correctly
            from commcare_connect.audit.experiment_models import AuditSessionRecord

            if issubclass(AuditSessionRecord, ExperimentRecord):
                self.stdout.write("    [OK] AuditSessionRecord inherits from ExperimentRecord")
                tests_passed += 1
            else:
                errors.append("AuditSessionRecord does not inherit from ExperimentRecord")
                self.stdout.write(self.style.ERROR("    [FAIL] Inheritance check failed"))

            self.stdout.write(self.style.SUCCESS("    ExperimentRecord integration verified"))

        except Exception as e:
            errors.append(f"ExperimentRecord integration error: {e}")
            self.stdout.write(self.style.ERROR(f"    [FAIL] {e}"))

        # Test 7: Check for environment variables
        self.stdout.write("\n[7] Checking environment configuration...")
        import os

        env_vars = {
            "COMMCARE_USERNAME": os.getenv("COMMCARE_USERNAME"),
            "COMMCARE_API_KEY": os.getenv("COMMCARE_API_KEY"),
        }

        for var_name, var_value in env_vars.items():
            if var_value:
                self.stdout.write(f"    [OK] {var_name} is set")
            else:
                warnings.append(f"{var_name} not set - blob fetching will fail")
                self.stdout.write(self.style.WARNING(f"    [WARN] {var_name} not set (optional for testing)"))

        # Summary
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(self.style.SUCCESS("TEST SUMMARY"))
        self.stdout.write("=" * 80)
        self.stdout.write(f"Tests passed: {tests_passed}")
        self.stdout.write(f"Errors: {len(errors)}")
        self.stdout.write(f"Warnings: {len(warnings)}")

        if errors:
            self.stdout.write("\n" + self.style.ERROR("ERRORS:"))
            for error in errors:
                self.stdout.write(self.style.ERROR(f"  [X] {error}"))

        if warnings:
            self.stdout.write("\n" + self.style.WARNING("WARNINGS:"))
            for warning in warnings:
                self.stdout.write(self.style.WARNING(f"  [!] {warning}"))

        if not errors:
            self.stdout.write("\n" + self.style.SUCCESS("[SUCCESS] All configuration checks passed!"))
            self.stdout.write("\n" + self.style.SUCCESS("Ready to test in browser:"))
            self.stdout.write("  -> Navigate to: http://localhost:8000/audit/experiment/")
            self.stdout.write("  -> Or create a new audit session")
            self.stdout.write("\nMake sure you have a Connect OAuth token in your browser session.")
            return

        self.stdout.write(
            "\n" + self.style.ERROR("[FAIL] Configuration errors found. Please fix them before testing.")
        )
        raise SystemExit(1)
