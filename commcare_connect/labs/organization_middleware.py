"""
Labs-specific organization middleware for LabsUser.

This middleware provides organization context for LabsUser (session-based OAuth users)
without hitting the database. It mimics the interface of OrganizationMiddleware but uses
data from the OAuth session instead of database queries.
"""

import logging

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
from django.utils.functional import SimpleLazyObject

from commcare_connect.organization.models import Organization

logger = logging.getLogger(__name__)


class MockOrganization:
    """Mock organization object for LabsUser when no real org in DB."""

    def __init__(self):
        self.id = 999999  # Use a high number that won't conflict with real IDs
        self.pk = 999999
        self.slug = "labs-mock"
        self.name = "Labs Mock Organization"
        self.program_manager = True  # Always True for labs permissions


class MockMembership:
    """Mock membership object for LabsUser compatibility."""

    def __init__(self, org_data: dict):
        self.is_admin = True  # Labs users are assumed to be admins for testing
        self.organization_id = org_data.get("id")
        self.organization_name = org_data.get("name")
        self.organization_slug = org_data.get("slug")

    @property
    def organization(self):
        """Return organization from database using ID from OAuth data."""
        if hasattr(self, "_org_cache"):
            return self._org_cache
        try:
            self._org_cache = Organization.objects.get(id=self.organization_id)
        except Organization.DoesNotExist:
            self._org_cache = None
        return self._org_cache


def _get_labs_organization(request, view_kwargs) -> Organization | None:
    """Get organization for LabsUser from OAuth session data or URL."""
    if not hasattr(request, "_cached_labs_org"):
        org = None

        # First try URL slug (for organization-specific URLs like /a/<org_slug>/...)
        org_slug = view_kwargs.get("org_slug")
        if org_slug:
            try:
                org = Organization.objects.get(slug=org_slug)
            except Organization.DoesNotExist:
                logger.warning(f"Organization with slug '{org_slug}' not found in database")

        # Fall back to first organization from OAuth data
        if not org and hasattr(request.user, "_org_data"):
            orgs = request.user._org_data.get("organizations", [])
            if orgs:
                first_org = orgs[0]
                try:
                    org = Organization.objects.get(id=first_org.get("id"))
                except Organization.DoesNotExist:
                    logger.warning(f"Organization ID {first_org.get('id')} from OAuth not found in database")

        # If still no org, use a mock organization for labs
        if not org:
            org = MockOrganization()

        request._cached_labs_org = org

    return request._cached_labs_org


def _get_labs_org_membership(request) -> MockMembership | None:
    """Get mock membership for LabsUser."""
    if not hasattr(request, "_cached_labs_membership"):
        membership = None
        org = request.org

        if isinstance(org, MockOrganization):
            # For mock org, create a mock membership
            membership = MockMembership({"id": None, "name": org.name, "slug": org.slug})
        elif org and hasattr(request.user, "_org_data"):
            # Find the matching org in user's OAuth data
            orgs = request.user._org_data.get("organizations", [])
            for org_data in orgs:
                if org_data.get("id") == org.id or org_data.get("slug") == org.slug:
                    membership = MockMembership(org_data)
                    break

        request._cached_labs_membership = membership

    return request._cached_labs_membership


def _get_labs_all_memberships(request):
    """Get mock memberships for all of LabsUser's organizations."""
    if not hasattr(request, "_cached_labs_memberships"):
        memberships = []

        if hasattr(request.user, "_org_data"):
            orgs = request.user._org_data.get("organizations", [])
            memberships = [MockMembership(org_data) for org_data in orgs]

        request._cached_labs_memberships = memberships

    return request._cached_labs_memberships


class LabsOrganizationMiddleware(MiddlewareMixin):
    """
    Labs-specific middleware for providing organization context to LabsUser.

    This middleware only runs in labs environment and provides organization
    information from OAuth session data instead of database queries.

    Replaces OrganizationMiddleware for LabsUser to avoid database FK issues.
    """

    def process_view(self, request, view_func, view_args, view_kwargs):
        """Add organization context to request for LabsUser."""
        # Only process for authenticated LabsUser in labs environment
        is_labs = getattr(settings, "IS_LABS_ENVIRONMENT", False)

        if not is_labs:
            return None

        # Check if user is LabsUser (has _org_data attribute)
        if not (request.user.is_authenticated and hasattr(request.user, "_org_data")):
            return None

        # Set up SimpleLazyObjects to mimic OrganizationMiddleware interface
        request.org = SimpleLazyObject(lambda: _get_labs_organization(request, view_kwargs))
        request.org_membership = SimpleLazyObject(lambda: _get_labs_org_membership(request))
        request.memberships = SimpleLazyObject(lambda: _get_labs_all_memberships(request))

        # For labs, we don't implement opportunity_pm check (not needed for solicitations)
        request.is_opportunity_pm = SimpleLazyObject(lambda: None)

        return None
