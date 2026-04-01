import datetime

import pytest
from django.urls import reverse
from django.utils.timezone import now

from commcare_connect.opportunity.tests.factories import AssignedTaskFactory, OpportunityAccessFactory, TaskFactory


def _add_export_credentials(api_client, user):
    token, _ = user.oauth2_provider_accesstoken.get_or_create(
        token="export-token",
        scope="read write export",
        defaults={"expires": now() + datetime.timedelta(hours=1)},
    )
    api_client.credentials(**{**getattr(api_client, "_credentials", {}), "Authorization": f"Bearer {token}"})


def _add_v2_header(api_client):
    api_client.credentials(
        **{**getattr(api_client, "_credentials", {}), "HTTP_ACCEPT": "application/json; version=2.0"}
    )


@pytest.fixture
def v2_export_client(api_client, org_user_member):
    _add_export_credentials(api_client, org_user_member)
    _add_v2_header(api_client)
    return api_client


@pytest.mark.django_db
class TestTaskDataView:
    def test_returns_task_list(self, v2_export_client, opportunity):
        task = TaskFactory(opportunity=opportunity)
        url = reverse("data_export:task_data", kwargs={"opp_id": opportunity.id})
        response = v2_export_client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        result = data["results"][0]
        assert result["id"] == task.id
        assert result["name"] == task.name

    def test_returns_404_for_unauthorized_opportunity(self, api_client, opportunity, user):
        _add_export_credentials(api_client, user)
        _add_v2_header(api_client)
        url = reverse("data_export:task_data", kwargs={"opp_id": opportunity.id})
        response = api_client.get(url)
        assert response.status_code == 404


@pytest.mark.django_db
class TestAssignedTaskDataView:
    def test_returns_assigned_task_list(self, v2_export_client, opportunity):
        opp_access = OpportunityAccessFactory(opportunity=opportunity)
        task = TaskFactory(opportunity=opportunity)
        assigned_task = AssignedTaskFactory(task=task, opportunity_access=opp_access)
        url = reverse("data_export:assigned_task_data", kwargs={"opp_id": opportunity.id})
        response = v2_export_client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        result = data["results"][0]
        assert result["id"] == assigned_task.id
        assert result["task_id"] == task.id
        assert result["task_name"] == task.name
        assert result["username"] == opp_access.user.username

    def test_returns_404_for_unauthorized_opportunity(self, api_client, opportunity, user):
        _add_export_credentials(api_client, user)
        _add_v2_header(api_client)
        url = reverse("data_export:assigned_task_data", kwargs={"opp_id": opportunity.id})
        response = api_client.get(url)
        assert response.status_code == 404
