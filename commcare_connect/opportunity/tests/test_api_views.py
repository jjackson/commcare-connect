import datetime

from rest_framework.test import APIClient

from commcare_connect.opportunity.models import OpportunityClaim
from commcare_connect.opportunity.tests.factories import OpportunityAccessFactory, OpportunityFactory
from commcare_connect.users.models import User
from commcare_connect.users.tests.factories import ConnectIdUserLinkFactory


def _setup_opportunity_and_access(mobile_user: User, total_budget, end_date):
    opportunity = OpportunityFactory(total_budget=total_budget, max_visits_per_user=100, end_date=end_date)
    opportunity_access = OpportunityAccessFactory(opportunity=opportunity, user=mobile_user)
    ConnectIdUserLinkFactory(
        user=mobile_user, commcare_username="test@ccc-test.commcarehq.org", domain=opportunity.deliver_app.cc_domain
    )
    return opportunity, opportunity_access


def test_claim_endpoint_success(mobile_user: User, api_client: APIClient):
    opportunity, opportunity_access = _setup_opportunity_and_access(
        mobile_user, total_budget=1000, end_date=datetime.date.today() + datetime.timedelta(days=100)
    )
    api_client.force_authenticate(mobile_user)
    response = api_client.post(f"/api/opportunity/{opportunity.id}/claim")
    assert response.status_code == 201
    claim = OpportunityClaim.objects.filter(opportunity_access=opportunity_access)
    assert claim.exists()


def test_claim_endpoint_budget_exhausted(mobile_user: User, api_client: APIClient):
    opportunity, opportunity_access = _setup_opportunity_and_access(
        mobile_user, total_budget=0, end_date=datetime.date.today() + datetime.timedelta(days=100)
    )
    api_client.force_authenticate(mobile_user)
    response = api_client.post(f"/api/opportunity/{opportunity.id}/claim")
    assert response.status_code == 200
    assert response.data == "Opportunity cannot be claimed. (Budget Exhausted)"


def test_claim_endpoint_end_date_exceeded(mobile_user: User, api_client: APIClient):
    opportunity, opportunity_access = _setup_opportunity_and_access(
        mobile_user, total_budget=1000, end_date=datetime.date.today() - datetime.timedelta(days=100)
    )
    api_client.force_authenticate(mobile_user)
    response = api_client.post(f"/api/opportunity/{opportunity.id}/claim")
    assert response.status_code == 200
    assert response.data == "Opportunity cannot be claimed. (End date reached)"


def test_claim_endpoint_already_claimed_opportunity(mobile_user: User, api_client: APIClient):
    opportunity, opportunity_access = _setup_opportunity_and_access(
        mobile_user, total_budget=1000, end_date=datetime.date.today() + datetime.timedelta(days=100)
    )
    api_client.force_authenticate(mobile_user)
    response = api_client.post(f"/api/opportunity/{opportunity.id}/claim")
    assert response.status_code == 201
    claim = OpportunityClaim.objects.filter(opportunity_access=opportunity_access)
    assert claim.exists()

    response = api_client.post(f"/api/opportunity/{opportunity.id}/claim")
    assert response.status_code == 200
    assert response.data == "Opportunity is already claimed"
