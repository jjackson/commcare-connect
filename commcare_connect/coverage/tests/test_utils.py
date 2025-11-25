"""Tests for coverage utility functions."""

import pytest
from django.core.cache import cache

from commcare_connect.coverage.utils import get_flw_names_for_opportunity
from commcare_connect.opportunity.models import OpportunityAccess
from commcare_connect.users.tests.factories import MobileUserFactory


@pytest.mark.django_db
class TestGetFLWNamesForOpportunity:
    """Tests for get_flw_names_for_opportunity function."""

    def test_returns_username_to_name_mapping(self, opportunity):
        """Test that function returns correct username to display name mapping."""
        # Create user with username
        user = MobileUserFactory(username="test_flw_user", name="Test FLW")

        # Create OpportunityAccess
        OpportunityAccess.objects.create(opportunity=opportunity, user=user)

        # Get FLW names
        flw_names = get_flw_names_for_opportunity(opportunity.id)

        # Verify mapping
        assert user.username in flw_names
        assert flw_names[user.username] == user.name

    def test_caches_results(self, opportunity):
        """Test that function caches results properly."""
        # Create user with username
        user = MobileUserFactory(username="test_flw_user", name="Test FLW")

        # Create OpportunityAccess
        OpportunityAccess.objects.create(opportunity=opportunity, user=user)

        # Clear cache
        cache.clear()

        # First call should query database and cache
        cache_key = f"flw_names_opp_{opportunity.id}"
        assert cache.get(cache_key) is None

        flw_names = get_flw_names_for_opportunity(opportunity.id)

        # Cache should now be populated
        assert cache.get(cache_key) is not None
        assert cache.get(cache_key) == flw_names

    def test_returns_username_when_name_is_empty(self, opportunity):
        """Test that function falls back to username when display name is empty."""
        # Create user with empty name
        user = MobileUserFactory(username="test_user_no_name", name="")
        OpportunityAccess.objects.create(opportunity=opportunity, user=user)

        flw_names = get_flw_names_for_opportunity(opportunity.id)

        # Should fall back to username
        assert flw_names[user.username] == user.username

    def test_empty_opportunity_returns_empty_dict(self, opportunity):
        """Test that function returns empty dict for opportunity with no FLWs."""
        flw_names = get_flw_names_for_opportunity(opportunity.id)
        assert flw_names == {}
