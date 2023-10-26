import datetime

import pytest
from rest_framework.test import APIClient

from commcare_connect.opportunity.models import Assessment, CompletedModule, Opportunity, OpportunityClaim
from commcare_connect.opportunity.tests.factories import (
    LearnModuleFactory,
    OpportunityAccessFactory,
    OpportunityFactory,
)
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


@pytest.mark.django_db
def test_learn_progress_endpoint(mobile_user: User, api_client: APIClient):
    opportunity, opportunity_access = _setup_opportunity_and_access(
        mobile_user, total_budget=1000, end_date=datetime.date.today() + datetime.timedelta(days=100)
    )
    learn_module = LearnModuleFactory(slug="module_1", app=opportunity.learn_app)
    CompletedModule.objects.create(
        module=learn_module,
        user=mobile_user,
        opportunity=opportunity,
        date=datetime.datetime.now(),
        duration=datetime.timedelta(hours=10),
    )
    Assessment.objects.create(
        user=mobile_user,
        app=opportunity.learn_app,
        opportunity=opportunity,
        date=datetime.datetime.now(),
        score=100,
        passing_score=opportunity.learn_app.passing_score,
        passed=True,
    )
    api_client.force_authenticate(mobile_user)
    response = api_client.get(f"/api/opportunity/{opportunity.id}/learn_progress")
    assert response.status_code == 200
    assert "completed_modules" in response.data
    assert len(response.data["completed_modules"]) == 1
    assert "assessments" in response.data
    assert len(response.data["assessments"]) == 1
    assert list(response.data["completed_modules"][0].keys()) == ["module", "date", "duration"]
    assert list(response.data["assessments"][0].keys()) == ["date", "score", "passing_score", "passed"]


def test_opportunity_list_endpoint(
    mobile_user_with_connect_link: User, api_client: APIClient, opportunity: Opportunity
):
    api_client.force_authenticate(mobile_user_with_connect_link)
    response = api_client.get("/api/opportunity/")
    assert response.status_code == 200
    assert len(response.data) == 1
    assert list(response.data[0].keys()) == [
        "id",
        "name",
        "description",
        "date_created",
        "date_modified",
        "organization",
        "learn_app",
        "deliver_app",
        "end_date",
        "max_visits_per_user",
        "daily_max_visits_per_user",
        "budget_per_visit",
        "total_budget",
        "claim",
        "learn_progress",
        "deliver_progress",
        "currency",
    ]
