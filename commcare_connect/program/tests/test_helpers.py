from datetime import timedelta

import pytest
from django.urls import reverse
from django_celery_beat.utils import now

from commcare_connect.opportunity.models import VisitValidationStatus
from commcare_connect.opportunity.tests.factories import AssessmentFactory, OpportunityAccessFactory, UserVisitFactory
from commcare_connect.program.tests.factories import ManagedOpportunityFactory, ProgramFactory
from commcare_connect.program.tests.test_views import BaseProgramTest
from commcare_connect.users.tests.factories import OrganizationFactory, UserFactory


class TestFunnelPerformanceTable(BaseProgramTest):
    @pytest.mark.django_db
    class TestProgramListView(BaseProgramTest):
        @pytest.fixture(autouse=True)
        def test_setup(self):
            self.program = ProgramFactory.create(organization=self.organization)
            self.list_url = reverse(
                "program:funnel_performance_table", kwargs={"org_slug": self.organization.slug, "pk": self.program.id}
            )

            nm_org = OrganizationFactory.create()
            opp = ManagedOpportunityFactory.create(program=self.program, organization=nm_org)
            users = UserFactory.create_batch(5)
            for index, user in enumerate(users):
                access = OpportunityAccessFactory.create(opportunity=opp, user=user, invited_date=now())
                AssessmentFactory.create(opportunity=opp, user=user, opportunity_access=access)
                visit_status = VisitValidationStatus.pending if index < 9 else VisitValidationStatus.trial
                UserVisitFactory.create(
                    user=user,
                    opportunity=opp,
                    status=visit_status,
                    opportunity_access=access,
                    visit_date=now() + timedelta(3),
                )
