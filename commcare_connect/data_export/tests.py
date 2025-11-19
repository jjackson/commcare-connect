import pytest
from oauth2_provider.models import AccessToken, Application
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from commcare_connect.opportunity.tests.factories import (
    OpportunityAccessFactory,
    OpportunityFactory,
)
from commcare_connect.users.tests.factories import UserFactory

User = get_user_model()


@pytest.mark.django_db
def test_opportunity_serializer_includes_user_count(api_client):
    """Test that the OpportunitySerializer includes user_count field."""
    # Create an organization member
    user = UserFactory()
    
    # Create an opportunity
    opportunity = OpportunityFactory(organization__name="Test Org")
    
    # Add users to the opportunity
    OpportunityAccessFactory(opportunity=opportunity)
    OpportunityAccessFactory(opportunity=opportunity)
    OpportunityAccessFactory(opportunity=opportunity)
    
    # Create OAuth application and access token
    app = Application.objects.create(
        name="Test App",
        user=user,
        client_type=Application.CLIENT_CONFIDENTIAL,
        authorization_grant_type=Application.GRANT_CLIENT_CREDENTIALS,
    )
    
    token = AccessToken.objects.create(
        user=user,
        token="test-token-123",
        application=app,
        expires=timezone.now() + timedelta(days=1),
        scope="export",
    )
    
    # Make the user a member of the organization
    opportunity.organization.add_user(user, "admin")
    
    # Make request with OAuth token
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.token}")
    response = api_client.get(f"/export/opportunity/{opportunity.id}/")
    
    # Verify response
    assert response.status_code == 200
    assert "user_count" in response.data
    assert response.data["user_count"] == 3


@pytest.mark.django_db
def test_opportunity_serializer_user_count_zero(api_client):
    """Test that the OpportunitySerializer returns 0 when no users."""
    # Create an organization member
    user = UserFactory()
    
    # Create an opportunity with no users
    opportunity = OpportunityFactory(organization__name="Test Org")
    
    # Create OAuth application and access token
    app = Application.objects.create(
        name="Test App",
        user=user,
        client_type=Application.CLIENT_CONFIDENTIAL,
        authorization_grant_type=Application.GRANT_CLIENT_CREDENTIALS,
    )
    
    token = AccessToken.objects.create(
        user=user,
        token="test-token-456",
        application=app,
        expires=timezone.now() + timedelta(days=1),
        scope="export",
    )
    
    # Make the user a member of the organization
    opportunity.organization.add_user(user, "admin")
    
    # Make request with OAuth token
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.token}")
    response = api_client.get(f"/export/opportunity/{opportunity.id}/")
    
    # Verify response
    assert response.status_code == 200
    assert "user_count" in response.data
    assert response.data["user_count"] == 0
