import datetime

import pytest
from django.utils.timezone import now
from rest_framework.test import APIClient

from commcare_connect.organization.models import Organization
from commcare_connect.users.models import User


def _add_create_credentials(api_client, user):
    """Add OAuth token with 'create' scope to the API client. Mirrors _add_export_credentials pattern."""
    token, _ = user.oauth2_provider_accesstoken.get_or_create(
        token=f"create-token-{user.pk}",
        scope="read write create",
        defaults={"expires": now() + datetime.timedelta(hours=1)},
    )
    api_client.credentials(Authorization=f"Bearer {token}")


@pytest.mark.django_db
class TestOrgPermissions:
    def test_unauthenticated_rejected(self, api_client: APIClient):
        response = api_client.get("/api/lookups/delivery_types/")
        assert response.status_code == 401

    def test_no_create_scope_rejected(
        self, api_client: APIClient, program_manager_org_user_admin: User, program_manager_org: Organization
    ):
        """Token without 'create' scope cannot access creation endpoints."""
        api_client.force_authenticate(program_manager_org_user_admin)
        response = api_client.post(
            "/api/program/",
            {
                "name": "Test",
                "description": "Test",
                "delivery_type": 1,
                "budget": 1000,
                "currency": "USD",
                "country": "USA",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
                "organization": program_manager_org.slug,
            },
            format="json",
        )
        assert response.status_code == 403

    def test_non_pm_org_rejected(self, api_client: APIClient, org_user_admin: User, organization: Organization):
        """Non-program-manager org admin cannot access creation endpoints."""
        _add_create_credentials(api_client, org_user_admin)
        response = api_client.post(
            "/api/program/",
            {
                "name": "Test",
                "description": "Test",
                "delivery_type": 1,
                "budget": 1000,
                "currency": "USD",
                "country": "USA",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
                "organization": organization.slug,
            },
            format="json",
        )
        assert response.status_code == 403

    def test_member_role_rejected(
        self, api_client: APIClient, program_manager_org_user_member: User, program_manager_org: Organization
    ):
        """Member (not admin) of PM org cannot access creation endpoints."""
        _add_create_credentials(api_client, program_manager_org_user_member)
        response = api_client.post(
            "/api/program/",
            {
                "name": "Test",
                "description": "Test",
                "delivery_type": 1,
                "budget": 1000,
                "currency": "USD",
                "country": "USA",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
                "organization": program_manager_org.slug,
            },
            format="json",
        )
        assert response.status_code == 403
