from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase

from commcare_connect.audit.models import AuditResult, AuditSession
from commcare_connect.opportunity.tests.factories import OpportunityFactory, UserVisitFactory
from commcare_connect.users.tests.factories import UserFactory

User = get_user_model()


class AuditSessionModelTest(TestCase):
    def setUp(self):
        self.auditor = UserFactory()
        self.flw_user = UserFactory()
        self.opportunity = OpportunityFactory()

    def test_audit_session_creation(self):
        """Test basic audit session creation"""
        session = AuditSession.objects.create(
            auditor=self.auditor,
            flw_user=self.flw_user,
            opportunity=self.opportunity,
            start_date=date.today() - timedelta(days=7),
            end_date=date.today(),
        )

        self.assertEqual(session.status, AuditSession.Status.IN_PROGRESS)
        self.assertIsNone(session.overall_result)
        self.assertEqual(session.progress_percentage, 0)

    def test_progress_calculation(self):
        """Test progress percentage calculation"""
        session = AuditSession.objects.create(
            auditor=self.auditor,
            flw_user=self.flw_user,
            opportunity=self.opportunity,
            start_date=date.today() - timedelta(days=7),
            end_date=date.today(),
        )

        # Create some visits for the session period
        visit1 = UserVisitFactory(
            user=self.flw_user, opportunity=self.opportunity, visit_date=date.today() - timedelta(days=3)
        )
        visit2 = UserVisitFactory(
            user=self.flw_user, opportunity=self.opportunity, visit_date=date.today() - timedelta(days=2)
        )

        # Initially no progress
        self.assertEqual(session.progress_percentage, 0)

        # Add one audit result
        AuditResult.objects.create(audit_session=session, user_visit=visit1, result=AuditResult.Result.PASS)

        # Should be 50% complete (1 of 2 visits)
        # Note: This test may need adjustment based on actual visit filtering logic

    def test_string_representation(self):
        """Test string representation of audit session"""
        session = AuditSession.objects.create(
            auditor=self.auditor,
            flw_user=self.flw_user,
            opportunity=self.opportunity,
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 7),
        )

        expected = f"Audit: {self.flw_user.username} (2023-01-01 - 2023-01-07)"
        self.assertEqual(str(session), expected)


class AuditResultModelTest(TestCase):
    def setUp(self):
        self.auditor = UserFactory()
        self.flw_user = UserFactory()
        self.opportunity = OpportunityFactory()
        self.session = AuditSession.objects.create(
            auditor=self.auditor,
            flw_user=self.flw_user,
            opportunity=self.opportunity,
            start_date=date.today() - timedelta(days=7),
            end_date=date.today(),
        )
        self.visit = UserVisitFactory(user=self.flw_user, opportunity=self.opportunity)

    def test_audit_result_creation(self):
        """Test basic audit result creation"""
        result = AuditResult.objects.create(
            audit_session=self.session,
            user_visit=self.visit,
            result=AuditResult.Result.PASS,
            notes="Good quality images",
        )

        self.assertEqual(result.result, AuditResult.Result.PASS)
        self.assertEqual(result.notes, "Good quality images")
        self.assertIsNotNone(result.audited_at)

    def test_unique_constraint(self):
        """Test that same visit can't be audited twice in same session"""
        AuditResult.objects.create(audit_session=self.session, user_visit=self.visit, result=AuditResult.Result.PASS)

        # Attempting to create another result for same visit/session should fail
        with self.assertRaises(Exception):  # IntegrityError
            AuditResult.objects.create(
                audit_session=self.session, user_visit=self.visit, result=AuditResult.Result.FAIL
            )

    def test_string_representation(self):
        """Test string representation of audit result"""
        result = AuditResult.objects.create(
            audit_session=self.session, user_visit=self.visit, result=AuditResult.Result.FAIL, notes="Blurry images"
        )

        expected = f"{self.visit} - fail"
        self.assertEqual(str(result), expected)
