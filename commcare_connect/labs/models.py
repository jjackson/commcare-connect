"""
Labs User Model

Transient user object that mimics Django User interface.
Never saved to database - initialized from session data only.
"""

from typing import Any


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
        self.is_superuser: bool = False  # OAuth API is source of truth for permissions
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

    def get_display_name(self) -> str:
        """Return display name for UI and event logging."""
        return self.username

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Prevent saving to database."""
        raise NotImplementedError("LabsUser cannot be saved to database")

    def delete(self, *args: Any, **kwargs: Any) -> None:
        """Prevent deletion from database."""
        raise NotImplementedError("LabsUser cannot be deleted from database")


class LocalLabsRecord:
    """Transient object for Labs API responses. Never saved to database.

    This class mimics production LabsRecord but is not a Django model.
    It's instantiated from production API responses and provides typed access
    to record data.
    """

    def __init__(self, api_data: dict[str, Any]) -> None:
        """Initialize from production API response.

        Args:
            api_data: Response data from /export/labs_record/ API
        """
        self.id: int = api_data["id"]
        self.experiment: str = api_data["experiment"]
        self.type: str = api_data["type"]
        self.data: dict = api_data["data"]
        self.username: str | None = api_data.get("username")  # Primary user identifier (not user_id)
        self.opportunity_id: int = api_data["opportunity_id"]
        self.organization_id: str | None = api_data.get("organization_id")
        self.program_id: int | None = api_data.get("program_id")
        self.labs_record_id: int | None = api_data.get("labs_record_id")  # Parent reference

    @property
    def pk(self) -> int:
        """Alias for id to mimic Django model interface.

        This allows LocalLabsRecord instances to be used in contexts that expect
        Django models, such as django-tables2 and URL reverse lookups.
        """
        return self.id

    def __str__(self) -> str:
        return f"{self.experiment}:{self.type}:{self.id}"

    def __repr__(self) -> str:
        return f"<LocalLabsRecord: {self}>"

    def to_api_dict(self) -> dict[str, Any]:
        """Serialize for API POST/PUT requests.

        Returns:
            Dict suitable for posting to production API
        """
        return {
            "id": self.id,
            "experiment": self.experiment,
            "type": self.type,
            "data": self.data,
            "username": self.username,
            "program_id": self.program_id,  # Will be supported shortly
            "labs_record_id": self.labs_record_id,
            # opportunity_id set by API endpoint URL
            # organization_id inferred from username in production
        }

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Prevent saving to database."""
        raise NotImplementedError("LocalLabsRecord cannot be saved. Use LabsRecordAPIClient instead.")

    def delete(self, *args: Any, **kwargs: Any) -> None:
        """Prevent deletion from database."""
        raise NotImplementedError("LocalLabsRecord cannot be deleted. Use LabsRecordAPIClient instead.")
