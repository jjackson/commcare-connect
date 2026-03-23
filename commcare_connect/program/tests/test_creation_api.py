import datetime

import pytest
from django.utils.timezone import now
from rest_framework.test import APIClient

from commcare_connect.opportunity.models import DeliveryType
from commcare_connect.organization.models import Organization
from commcare_connect.program.models import Program
from commcare_connect.program.tests.factories import ProgramFactory
from commcare_connect.users.models import User


def _add_create_credentials(api_client, user):
    """Add OAuth token with 'create' scope to the API client."""
    token, _ = user.oauth2_provider_accesstoken.get_or_create(
        token=f"create-token-{user.pk}",
        scope="read write create",
        defaults={"expires": now() + datetime.timedelta(hours=1)},
    )
    api_client.credentials(Authorization=f"Bearer {token}")


@pytest.mark.django_db
class TestCreateProgram:
    def _payload(self, org, delivery_type_id):
        return {
            "name": "Test Program",
            "description": "A test program",
            "delivery_type": delivery_type_id,
            "budget": 50000,
            "currency": "USD",
            "country": "USA",
            "start_date": "2026-04-01",
            "end_date": "2026-12-31",
            "organization": org.slug,
        }

    def test_create_program_success(
        self, api_client: APIClient, program_manager_org_user_admin: User, program_manager_org: Organization
    ):
        dt = DeliveryType.objects.create(name="Direct", slug="direct", description="Direct delivery")
        _add_create_credentials(api_client, program_manager_org_user_admin)
        response = api_client.post("/api/program/", self._payload(program_manager_org, dt.id), format="json")
        assert response.status_code == 201
        assert Program.objects.filter(name="Test Program").exists()
        program = Program.objects.get(name="Test Program")
        assert program.organization == program_manager_org
        assert program.slug

    def test_create_program_non_pm_org_forbidden(
        self, api_client: APIClient, org_user_admin: User, organization: Organization
    ):
        dt = DeliveryType.objects.create(name="Direct", slug="direct", description="Direct delivery")
        _add_create_credentials(api_client, org_user_admin)
        response = api_client.post("/api/program/", self._payload(organization, dt.id), format="json")
        assert response.status_code == 403

    def test_create_program_missing_fields(
        self, api_client: APIClient, program_manager_org_user_admin: User, program_manager_org: Organization
    ):
        _add_create_credentials(api_client, program_manager_org_user_admin)
        response = api_client.post(
            "/api/program/", {"name": "Incomplete", "organization": program_manager_org.slug}, format="json"
        )
        assert response.status_code == 400

    def test_create_program_end_date_before_start(
        self, api_client: APIClient, program_manager_org_user_admin: User, program_manager_org: Organization
    ):
        dt = DeliveryType.objects.create(name="Direct", slug="direct", description="Direct delivery")
        payload = self._payload(program_manager_org, dt.id)
        payload["start_date"] = "2026-12-31"
        payload["end_date"] = "2026-01-01"
        _add_create_credentials(api_client, program_manager_org_user_admin)
        response = api_client.post("/api/program/", payload, format="json")
        assert response.status_code == 400


@pytest.mark.django_db
class TestListPrograms:
    def test_list_programs_for_pm_org(
        self, api_client: APIClient, program_manager_org_user_admin: User, program_manager_org: Organization
    ):
        ProgramFactory(organization=program_manager_org)
        ProgramFactory()
        _add_create_credentials(api_client, program_manager_org_user_admin)
        response = api_client.get(f"/api/program/?organization={program_manager_org.slug}")
        assert response.status_code == 200
        assert len(response.data) == 1
