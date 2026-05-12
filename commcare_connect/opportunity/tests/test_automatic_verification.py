from http import HTTPStatus

import pytest
from django.urls import reverse

from commcare_connect.opportunity.decorators import block_when_automatic_verification
from commcare_connect.opportunity.filters import DeliverFilterSet
from commcare_connect.opportunity.forms import (
    DeliverUnitFlagsForm,
    OpportunityVerificationFlagsConfigForm,
    VisitExportForm,
)
from commcare_connect.opportunity.models import (
    DeliverUnitFlagRules,
    OpportunityAccess,
    OpportunityVerificationFlags,
    VisitReviewStatus,
    VisitValidationStatus,
)
from commcare_connect.opportunity.tests.factories import DeliverUnitFactory, OpportunityFactory, UserVisitFactory
from commcare_connect.program.tests.factories import ManagedOpportunityFactory, ProgramFactory
from commcare_connect.users.tests.factories import OrganizationFactory


@pytest.mark.django_db
class TestBlockWhenAutomaticVerificationDecorator:
    def _request_with_opp(self, automatic_visit_verification):
        opp = OpportunityFactory(automatic_visit_verification=automatic_visit_verification)
        request = type("R", (), {})()
        request.opportunity = opp
        return request

    def test_passes_through_when_flag_off(self):
        called = {}

        @block_when_automatic_verification
        def view(request):
            called["yes"] = True
            return "ok"

        result = view(self._request_with_opp(False))
        assert called == {"yes": True}
        assert result == "ok"

    def test_blocks_when_flag_on(self):
        @block_when_automatic_verification
        def view(request):
            raise AssertionError("inner view should not run")

        response = view(self._request_with_opp(True))
        assert response.status_code == HTTPStatus.FORBIDDEN
        assert response["HX-Trigger"] == "reload_table"


@pytest.mark.django_db
class TestOpportunityVerificationFlagsConfigForm:
    def test_hides_fields_when_automatic_verification_on(self):
        opp = OpportunityFactory(automatic_visit_verification=True)
        form = OpportunityVerificationFlagsConfigForm(opportunity=opp)
        for field in ("duplicate", "gps", "catchment_areas", "location"):
            assert field not in form.fields

    def test_keeps_fields_when_off(self):
        opp = OpportunityFactory(automatic_visit_verification=False)
        form = OpportunityVerificationFlagsConfigForm(opportunity=opp)
        for field in ("duplicate", "gps", "catchment_areas", "location"):
            assert field in form.fields

    def test_save_forces_falsy_when_flag_on(self):
        opp = OpportunityFactory(automatic_visit_verification=True)
        instance = OpportunityVerificationFlags(
            opportunity=opp, duplicate=True, gps=True, catchment_areas=True, location=42
        )
        form = OpportunityVerificationFlagsConfigForm(
            data={"form_submission_start": "", "form_submission_end": ""},
            instance=instance,
            opportunity=opp,
        )
        assert form.is_valid(), form.errors
        saved = form.save()
        assert saved.duplicate is False
        assert saved.gps is False
        assert saved.catchment_areas is False
        assert saved.location == 0


@pytest.mark.django_db
class TestDeliverUnitFlagsForm:
    def test_hides_check_attachments_when_flag_on(self):
        opp = OpportunityFactory(automatic_visit_verification=True)
        form = DeliverUnitFlagsForm(opportunity=opp)
        assert "check_attachments" not in form.fields

    def test_save_forces_check_attachments_false(self):
        opp = OpportunityFactory(automatic_visit_verification=True)
        deliver_unit = DeliverUnitFactory(app=opp.deliver_app, payment_unit=None)
        instance = DeliverUnitFlagRules(opportunity=opp, deliver_unit=deliver_unit, check_attachments=True)
        form = DeliverUnitFlagsForm(
            data={"deliver_unit": deliver_unit.pk, "duration": 5},
            instance=instance,
            opportunity=opp,
        )
        assert form.is_valid(), form.errors
        saved = form.save()
        assert saved.check_attachments is False


@pytest.mark.django_db
class TestDeliverFilterSet:
    def test_drops_review_pending_and_has_duplicates_when_flag_on(self):
        opp = OpportunityFactory(automatic_visit_verification=True)
        fs = DeliverFilterSet({}, queryset=OpportunityAccess.objects.none(), opportunity=opp)
        assert "review_pending" not in fs.filters
        assert "has_duplicates" not in fs.filters
        # Other filters remain
        assert "last_active" in fs.filters
        assert "has_flags" in fs.filters

    def test_keeps_all_filters_when_flag_off(self):
        opp = OpportunityFactory(automatic_visit_verification=False)
        fs = DeliverFilterSet({}, queryset=OpportunityAccess.objects.none(), opportunity=opp)
        for name in ("review_pending", "has_duplicates", "last_active", "has_flags", "has_overlimit"):
            assert name in fs.filters


@pytest.mark.django_db
class TestVisitExportForm:
    def test_strips_pending_when_flag_on_and_not_review_export(self, organization):
        opp = OpportunityFactory(automatic_visit_verification=True, organization=organization)
        form = VisitExportForm(opportunity=opp, org_slug=organization.slug)
        choices = dict(form.fields["status"].choices)
        assert VisitValidationStatus.pending.value not in choices

    def test_keeps_pending_when_flag_off(self, organization):
        opp = OpportunityFactory(automatic_visit_verification=False, organization=organization)
        form = VisitExportForm(opportunity=opp, org_slug=organization.slug)
        choices = dict(form.fields["status"].choices)
        assert VisitValidationStatus.pending.value in choices

    def test_review_export_unaffected(self, organization):
        opp = OpportunityFactory(automatic_visit_verification=True, organization=organization)
        form = VisitExportForm(opportunity=opp, org_slug=organization.slug, review_export=True)
        # review export uses VisitReviewStatus choices, not VisitValidationStatus
        choices = dict(form.fields["status"].choices)
        assert VisitReviewStatus.pending.value in choices


@pytest.mark.django_db
class TestProgramHomePendingReview:
    def test_pm_home_excludes_auto_verified(self, client, program_manager_org, program_manager_org_user_admin):
        program = ProgramFactory(organization=program_manager_org)
        nm_org = OrganizationFactory()
        manual_opp = ManagedOpportunityFactory(
            organization=nm_org, program=program, automatic_visit_verification=False
        )
        auto_opp = ManagedOpportunityFactory(organization=nm_org, program=program, automatic_visit_verification=True)
        for opp in (manual_opp, auto_opp):
            UserVisitFactory(
                opportunity=opp,
                status=VisitValidationStatus.approved,
                review_status=VisitReviewStatus.pending,
                review_created_on="2026-01-01T00:00:00Z",
            )

        client.force_login(program_manager_org_user_admin)
        response = client.get(reverse("program:home", args=(program_manager_org.slug,)))
        assert response.status_code == HTTPStatus.OK
        pending_review_card = next(
            (a for a in response.context["recent_activities"] if a["title"] == "Pending Review"), None
        )
        assert pending_review_card is not None
        opp_names = {row["opportunity__name"] for row in pending_review_card["rows"]}
        assert manual_opp.name in opp_names
        assert auto_opp.name not in opp_names

    def test_nm_home_excludes_auto_verified(self, client, organization, program_manager_org, org_user_admin):
        program = ProgramFactory(organization=program_manager_org)
        manual_opp = ManagedOpportunityFactory(
            organization=organization, program=program, automatic_visit_verification=False
        )
        auto_opp = ManagedOpportunityFactory(
            organization=organization, program=program, automatic_visit_verification=True
        )
        for opp in (manual_opp, auto_opp):
            UserVisitFactory(opportunity=opp, status=VisitValidationStatus.pending)

        client.force_login(org_user_admin)
        response = client.get(reverse("program:home", args=(organization.slug,)))
        assert response.status_code == HTTPStatus.OK
        pending_review_card = next(
            (a for a in response.context["recent_activities"] if a["title"] == "Pending Review"), None
        )
        assert pending_review_card is not None
        opp_names = {row["opportunity__name"] for row in pending_review_card["rows"]}
        assert manual_opp.name in opp_names
        assert auto_opp.name not in opp_names


@pytest.mark.django_db
class TestAutomaticVerificationBackendGuards:
    def _opp(self, organization):
        return OpportunityFactory(organization=organization, automatic_visit_verification=True)

    def test_approve_visits_returns_403(self, client, organization, org_user_member):
        opp = self._opp(organization)
        client.force_login(org_user_member)
        url = reverse("opportunity:approve_visits", args=(organization.slug, opp.opportunity_id))
        response = client.post(url, data={"visit_ids[]": []})
        assert response.status_code == HTTPStatus.FORBIDDEN
        assert response["HX-Trigger"] == "reload_table"

    def test_reject_visits_returns_403(self, client, organization, org_user_member):
        opp = self._opp(organization)
        client.force_login(org_user_member)
        url = reverse("opportunity:reject_visits", args=(organization.slug, opp.opportunity_id))
        response = client.post(url, data={"visit_ids[]": [], "reason": "x"})
        assert response.status_code == HTTPStatus.FORBIDDEN

    def test_user_visit_review_returns_403(self, client, organization, org_user_member):
        opp = self._opp(organization)
        client.force_login(org_user_member)
        url = reverse("opportunity:user_visit_review", args=(organization.slug, opp.opportunity_id))
        response = client.post(url, data={"review_status": "agree"})
        assert response.status_code == HTTPStatus.FORBIDDEN

    def test_visit_import_returns_403(self, client, organization, org_user_member):
        opp = self._opp(organization)
        client.force_login(org_user_member)
        url = reverse("opportunity:visit_import", args=(organization.slug, opp.opportunity_id))
        response = client.post(url)
        assert response.status_code == HTTPStatus.FORBIDDEN

    def test_review_visit_export_returns_403(self, client, organization, org_user_member):
        opp = self._opp(organization)
        client.force_login(org_user_member)
        url = reverse("opportunity:review_visit_export", args=(organization.slug, opp.opportunity_id))
        response = client.post(url)
        assert response.status_code == HTTPStatus.FORBIDDEN
