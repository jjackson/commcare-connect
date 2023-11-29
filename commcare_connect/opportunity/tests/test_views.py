import pytest
from django.test import Client
from django.urls import reverse

from commcare_connect.opportunity.models import Opportunity, OpportunityAccess, OpportunityClaim
from commcare_connect.opportunity.tests.factories import OpportunityClaimFactory
from commcare_connect.organization.models import Organization
from commcare_connect.users.models import User


@pytest.mark.django_db
def test_add_budget_existing_users(
    organization: Organization, org_user_member: User, opportunity: Opportunity, mobile_user: User, client: Client
):
    opportunity.max_visits_per_user = 100
    opportunity.budget_per_visit = 1
    opportunity.total_budget = 1000
    opportunity.organization = organization
    opportunity.save()
    access = OpportunityAccess.objects.get(opportunity=opportunity, user=mobile_user)
    claim = OpportunityClaimFactory(opportunity_access=access, max_payments=100)
    assert opportunity.total_budget == 1000
    assert opportunity.claimed_budget == 100

    url = reverse("opportunity:add_budget_existing_users", args=(organization.slug, opportunity.pk))
    client.force_login(org_user_member)
    response = client.post(url, data=dict(selected_users=[claim.id], additional_visits=10))
    assert response.status_code == 302
    opportunity = Opportunity.objects.get(pk=opportunity.pk)
    assert opportunity.total_budget == 1010
    assert opportunity.claimed_budget == 110
    assert OpportunityClaim.objects.get(pk=claim.pk).max_payments == 110
