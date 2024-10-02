from datetime import timedelta

import pytest
from django_celery_beat.utils import now

from commcare_connect.opportunity.models import VisitValidationStatus
from commcare_connect.opportunity.tests.factories import (
    AssessmentFactory,
    CompletedWorkFactory,
    OpportunityAccessFactory,
    UserVisitFactory,
)
from commcare_connect.organization.models import Organization
from commcare_connect.program.helpers import get_annotated_managed_opportunity, get_delivery_performance_report
from commcare_connect.program.tests.factories import ManagedOpportunityFactory, ProgramFactory
from commcare_connect.users.tests.factories import OrganizationFactory, UserFactory


def test_get_annotated_managed_opportunity(program_manager_org: Organization):
    program = ProgramFactory.create(organization=program_manager_org)
    nm_org = OrganizationFactory.create()
    opp = ManagedOpportunityFactory.create(program=program, organization=nm_org)
    users = UserFactory.create_batch(5)
    for index, user in enumerate(users):
        access = OpportunityAccessFactory.create(opportunity=opp, user=user, invited_date=now())
        AssessmentFactory.create(opportunity=opp, user=user, opportunity_access=access)
        visit_status = VisitValidationStatus.pending if index < 3 else VisitValidationStatus.trial
        UserVisitFactory.create(
            user=user,
            opportunity=opp,
            status=visit_status,
            opportunity_access=access,
            visit_date=now() + timedelta(1),
        )

    opps = get_annotated_managed_opportunity(program)
    for opp in opps:
        assert nm_org.slug == opp.organization.slug
        assert opp.workers_passing_assessment == 5
        assert opp.workers_starting_delivery == 3


@pytest.mark.django_db
class TestDeliveryPerformanceReport:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.program_manager_org = OrganizationFactory.create()
        self.program = ProgramFactory.create(organization=self.program_manager_org)
        self.nm_org = OrganizationFactory.create()
        self.opp = ManagedOpportunityFactory.create(program=self.program, organization=self.nm_org)

    def create_user_with_visit(self, visit_status, visit_date, flagged=False, create_completed_work=True):
        user = UserFactory.create()
        access = OpportunityAccessFactory.create(opportunity=self.opp, user=user, invited_date=now())
        UserVisitFactory.create(
            user=user,
            opportunity=self.opp,
            status=visit_status,
            opportunity_access=access,
            visit_date=visit_date,
            flagged=flagged,
        )
        if create_completed_work:
            CompletedWorkFactory.create(opportunity_access=access)
        return user

    def test_basic_delivery_performance(self):
        for _ in range(2):
            self.create_user_with_visit(VisitValidationStatus.pending, now(), True)
        for _ in range(3):
            self.create_user_with_visit(VisitValidationStatus.approved, now(), False)

        opps = get_delivery_performance_report(self.program, None, None)
        assert len(opps) == 1
        assert opps[0].total_workers_starting_delivery == 5
        assert opps[0].active_workers == 5
        assert opps[0].total_payment_units == 5
        assert opps[0].total_payment_units_with_flags == 2
        assert opps[0].total_payment_since_start_date == 5
        assert opps[0].delivery_per_day_per_worker == 1.0
        assert opps[0].records_flagged_percentage == 40.0

    def test_delivery_performance_with_date_range(self):
        start_date = now() - timedelta(10)
        end_date = now() + timedelta(10)

        self.create_user_with_visit(VisitValidationStatus.pending, start_date - timedelta(1))
        self.create_user_with_visit(VisitValidationStatus.pending, start_date + timedelta(1))
        self.create_user_with_visit(VisitValidationStatus.pending, end_date - timedelta(1))
        self.create_user_with_visit(VisitValidationStatus.pending, end_date + timedelta(1))

        opps = get_delivery_performance_report(self.program, start_date, end_date)
        assert opps[0].active_workers == 2
        assert opps[0].total_payment_since_start_date == 2

    def test_delivery_performance_with_flagged_visits(self):
        self.create_user_with_visit(VisitValidationStatus.pending, now())
        self.create_user_with_visit(VisitValidationStatus.pending, now(), flagged=True)

        opps = get_delivery_performance_report(self.program, None, None)
        assert opps[0].total_payment_units_with_flags == 1
        assert opps[0].records_flagged_percentage == 50.0

    def test_delivery_performance_with_no_active_workers(self):
        self.create_user_with_visit(VisitValidationStatus.over_limit, now())
        self.create_user_with_visit(VisitValidationStatus.trial, now())

        opps = get_delivery_performance_report(self.program, None, None)
        assert opps[0].total_workers_starting_delivery == 2
        assert opps[0].active_workers == 2
        assert opps[0].delivery_per_day_per_worker == 1.0

    def test_delivery_performance_with_multiple_opportunities(self):
        opp2 = ManagedOpportunityFactory.create(program=self.program)

        self.create_user_with_visit(VisitValidationStatus.pending, now())

        user = UserFactory.create()
        access = OpportunityAccessFactory.create(opportunity=opp2, user=user, invited_date=now())
        UserVisitFactory.create(
            user=user,
            opportunity=opp2,
            status=VisitValidationStatus.pending,
            opportunity_access=access,
            visit_date=now(),
        )
        CompletedWorkFactory.create(opportunity_access=access)

        opps = get_delivery_performance_report(self.program, None, None)
        assert len(opps) == 2
        assert all(o.active_workers == 1 for o in opps)

    def test_delivery_performance_with_no_completed_work(self):
        self.create_user_with_visit(VisitValidationStatus.pending, now(), create_completed_work=False)

        opps = get_delivery_performance_report(self.program, None, None)
        assert opps[0].total_payment_units == 0
        assert opps[0].delivery_per_day_per_worker == 0

    @pytest.mark.parametrize("visit_status", [VisitValidationStatus.rejected, VisitValidationStatus.approved])
    def test_delivery_performance_excluded_statuses(self, visit_status):
        self.create_user_with_visit(visit_status, now(), flagged=True)

        opps = get_delivery_performance_report(self.program, None, None)
        assert opps[0].total_workers_starting_delivery == 1
        assert opps[0].active_workers == 1
        assert opps[0].total_payment_units_with_flags == 0

    def test_delivery_performance_with_mixed_statuses(self):
        self.create_user_with_visit(VisitValidationStatus.pending, now(), flagged=True)
        self.create_user_with_visit(VisitValidationStatus.approved, now(), flagged=True)
        self.create_user_with_visit(VisitValidationStatus.rejected, now(), flagged=True)
        self.create_user_with_visit(VisitValidationStatus.over_limit, now(), flagged=True)

        opps = get_delivery_performance_report(self.program, None, None)
        assert opps[0].total_workers_starting_delivery == 4
        assert opps[0].active_workers == 4
        assert opps[0].total_payment_units_with_flags == 2
        assert opps[0].records_flagged_percentage == 50.0
