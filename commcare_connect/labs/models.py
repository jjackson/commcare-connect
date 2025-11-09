"""
Labs User Model

Transient user object that mimics Django User interface.
Never saved to database - initialized from session data only.
"""

from typing import Any

from django.db import models

from commcare_connect.utils.db import BaseModel


def _get_empty_memberships():
    """Return empty queryset for memberships.

    Defined as function to avoid circular imports at module level.
    """
    from commcare_connect.organization.models import UserOrganizationMembership

    return UserOrganizationMembership.objects.none()


class LabsUser:
    """Transient user object for labs OAuth authentication.

    This class mimics Django's User interface but is never saved to the database.
    It's instantiated from session data on each request.
    """

    def __init__(self, session_data: dict[str, Any]) -> None:
        """Initialize from session OAuth data.

        Args:
            session_data: Full labs_oauth session data including user_profile and organization_data
        """
        # Extract user profile
        user_profile = session_data.get("user_profile", session_data)  # Fallback for old format

        self.id: int = user_profile["id"]
        self.pk: int = user_profile["id"]
        self.username: str = user_profile["username"]
        self.email: str = user_profile["email"]
        self.first_name: str = user_profile.get("first_name", "")
        self.last_name: str = user_profile.get("last_name", "")
        self.is_authenticated: bool = True
        self.is_active: bool = True
        self.is_staff: bool = True  # Staff for admin access
        self.is_superuser: bool = True  # Superuser for labs testing (bypasses permission checks)
        self.is_anonymous: bool = False
        self.is_labs_user: bool = True  # Flag to identify labs users in templates

        # Organization data from API (just storage, no helper methods)
        self._org_data: dict = session_data.get("organization_data", {})

    @property
    def organizations(self) -> list[dict]:
        """Return list of organizations user is member of."""
        return self._org_data.get("organizations", [])

    @property
    def programs(self) -> list[dict]:
        """Return list of programs user has access to."""
        return self._org_data.get("programs", [])

    @property
    def opportunities(self) -> list[dict]:
        """Return list of opportunities user has access to."""
        return self._org_data.get("opportunities", [])

    @property
    def memberships(self):
        """Return empty queryset for organization memberships.

        LabsUser is not stored in database, so has no memberships.
        This property exists for compatibility with Django User interface.
        Could be populated with actual memberships in the future if needed.
        """
        return _get_empty_memberships()

    def __str__(self) -> str:
        return self.username

    def __repr__(self) -> str:
        return f"<LabsUser: {self.username}>"

    def get_full_name(self) -> str:
        """Return the first_name plus the last_name, with a space in between."""
        full_name = f"{self.first_name} {self.last_name}"
        return full_name.strip()

    def get_short_name(self) -> str:
        """Return the short name for the user."""
        return self.first_name

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Prevent saving to database."""
        raise NotImplementedError("LabsUser cannot be saved to database")

    def delete(self, *args: Any, **kwargs: Any) -> None:
        """Prevent deletion from database."""
        raise NotImplementedError("LabsUser cannot be deleted from database")


class ExperimentRecord(BaseModel):
    """
    Generic experiment record storage for labs features.

    Stores production IDs as integers (no ForeignKeys) to work with OAuth data.
    When this moves to production API, ForeignKeys can be added there.
    """

    experiment = models.TextField(help_text="Experiment name (e.g., 'solicitations', 'audit')")
    type = models.CharField(max_length=50, help_text="Record type (e.g., 'Solicitation', 'SolicitationResponse')")

    # Store production IDs as integers (no ForeignKeys for labs)
    user_id = models.IntegerField(null=True, blank=True, help_text="Production user ID")
    opportunity_id = models.IntegerField(null=True, blank=True, help_text="Production opportunity ID")
    organization_id = models.CharField(
        max_length=255, null=True, blank=True, help_text="Production organization slug or ID"
    )
    program_id = models.IntegerField(null=True, blank=True, help_text="Production program ID")

    # Self-referential link for hierarchies (e.g., Response -> Solicitation, Review -> Response)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")

    # JSON data storage - store all the actual content here
    data = models.JSONField(default=dict, help_text="JSON storage for record content")

    class Meta:
        indexes = [
            models.Index(fields=["experiment", "type"]),
            models.Index(fields=["experiment", "type", "parent"]),
            models.Index(fields=["program_id"]),
            models.Index(fields=["organization_id"]),
        ]
        ordering = ["-date_created"]

    def __str__(self):
        return f"{self.experiment}:{self.type}:{self.pk}"
