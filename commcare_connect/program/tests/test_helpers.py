from datetime import timedelta

from django_celery_beat.utils import now

from commcare_connect.opportunity.models import VisitValidationStatus
from commcare_connect.opportunity.tests.factories import AssessmentFactory, OpportunityAccessFactory, UserVisitFactory
from commcare_connect.organization.models import Organization
from commcare_connect.program.helpers import get_annotated_managed_opportunity
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


def test_delivery_performance(program_manager_org: Organization):
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
