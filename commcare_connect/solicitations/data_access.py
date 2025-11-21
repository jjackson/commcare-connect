"""
Data Access Layer for Solicitations.

This layer uses LabsRecordAPIClient to interact with production LabsRecord API.
It handles casting API responses to typed proxy models
(SolicitationRecord, ResponseRecord, ReviewRecord).

This is a pure API client with no local database storage.
"""

from django.http import HttpRequest

from commcare_connect.labs.api_client import LabsRecordAPIClient
from commcare_connect.solicitations.models import ResponseRecord, ReviewRecord, SolicitationRecord


class SolicitationDataAccess:
    """
    Data access layer for solicitations that uses LabsRecordAPIClient.

    This class provides solicitation-specific methods and handles casting
    API responses to appropriate proxy model types.
    """

    def __init__(
        self,
        organization_id: int | None = None,
        program_id: int | None = None,
        access_token: str | None = None,
        request: HttpRequest | None = None,
    ):
        """Initialize solicitations data access.

        Args:
            organization_id: Optional organization ID for API scoping
            program_id: Optional program ID for API scoping
            access_token: OAuth Bearer token for production API
            request: HttpRequest object (for extracting token and org context in labs mode)

        Note: Solicitations use program_id (for solicitation queries) and
        organization_id (for response queries). They do NOT use opportunity_id.
        """
        self.organization_id = organization_id
        self.program_id = program_id

        # Use labs_context from middleware if available (takes precedence)
        if request and hasattr(request, "labs_context"):
            labs_context = request.labs_context
            if not program_id and "program_id" in labs_context:
                self.program_id = labs_context["program_id"]
            if not organization_id and "organization_id" in labs_context:
                self.organization_id = labs_context["organization_id"]

        # Get OAuth token from labs session
        if not access_token and request:
            from django.utils import timezone

            labs_oauth = request.session.get("labs_oauth", {})
            expires_at = labs_oauth.get("expires_at", 0)
            if timezone.now().timestamp() < expires_at:
                access_token = labs_oauth.get("access_token")

        if not access_token:
            raise ValueError("OAuth access token required for solicitation data access")

        self.labs_api = LabsRecordAPIClient(
            access_token,
            organization_id=self.organization_id,
            program_id=self.program_id,
        )

    def get_solicitations(
        self,
        program_id: int | None = None,
        status: str | None = None,
        solicitation_type: str | None = None,
        is_publicly_listed: bool | None = None,
        username: str | None = None,
    ) -> list[SolicitationRecord]:
        """
        Query for solicitation records with optional filters.

        Args:
            program_id: Filter by production program ID
            status: Filter by status ('active', 'closed', 'draft')
            solicitation_type: Filter by type ('eoi', 'rfp')
            is_publicly_listed: Filter by public listing status
            username: Filter by username who created the solicitation (client-side filter)

        Returns:
            List of SolicitationRecord instances
        """
        # Build kwargs for data field filters
        kwargs = {}
        if status:
            kwargs["status"] = status
        if solicitation_type:
            kwargs["solicitation_type"] = solicitation_type
        if is_publicly_listed is not None:
            kwargs["is_publicly_listed"] = is_publicly_listed

        # Get records from API (don't send username - production doesn't support it)
        records = self.labs_api.get_records(
            experiment="solicitations",
            type="Solicitation",
            program_id=program_id,
            model_class=SolicitationRecord,
            **kwargs,
        )

        # Filter by username client-side if specified
        if username:
            records = [r for r in records if r.username == username]

        return records

    def get_solicitation_by_id(self, solicitation_id: int) -> SolicitationRecord | None:
        """
        Get a single solicitation record by ID.

        Args:
            solicitation_id: ID of the solicitation

        Returns:
            SolicitationRecord instance or None
        """
        return self.labs_api.get_record_by_id(
            record_id=solicitation_id, experiment="solicitations", type="Solicitation", model_class=SolicitationRecord
        )

    def create_solicitation(self, program_id: int, username: str, data_dict: dict) -> SolicitationRecord:
        """
        Create a new solicitation via production API.

        Args:
            program_id: Production program ID
            username: Username who created this
            data_dict: Dictionary containing solicitation data

        Returns:
            SolicitationRecord instance
        """
        return self.labs_api.create_record(
            experiment="solicitations",
            type="Solicitation",
            data=data_dict,
            program_id=program_id,
            username=username,
        )

    def get_responses_for_solicitation(
        self, solicitation_record: SolicitationRecord, status: str | None = None
    ) -> list[ResponseRecord]:
        """
        Get all responses for a solicitation.

        Args:
            solicitation_record: Solicitation to find responses for
            status: Optional status filter ('draft', 'submitted')

        Returns:
            List of ResponseRecord instances
        """
        kwargs = {}
        if status:
            kwargs["status"] = status

        return self.labs_api.get_records(
            experiment="solicitations",
            type="SolicitationResponse",
            labs_record_id=solicitation_record.id,
            model_class=ResponseRecord,
            **kwargs,
        )

    def get_response_for_solicitation(
        self,
        solicitation_record: SolicitationRecord,
        organization_id: str,
        username: str | None = None,
        status: str | None = None,
    ) -> ResponseRecord | None:
        """
        Find a response by a specific organization for a solicitation.

        Args:
            solicitation_record: Solicitation to find response for
            organization_id: Organization slug/ID that submitted the response
            username: Optional username filter
            status: Optional status filter ('draft', 'submitted')

        Returns:
            ResponseRecord instance or None
        """
        kwargs = {}
        if status:
            kwargs["status"] = status

        records = self.labs_api.get_records(
            experiment="solicitations",
            type="SolicitationResponse",
            labs_record_id=solicitation_record.id,
            organization_id=organization_id,
            username=username,
            model_class=ResponseRecord,
            **kwargs,
        )

        return records[0] if records else None

    def get_response_by_id(self, response_id: int) -> ResponseRecord | None:
        """
        Get a single response record by ID.

        Args:
            response_id: ID of the response

        Returns:
            ResponseRecord instance or None
        """
        return self.labs_api.get_record_by_id(
            record_id=response_id, experiment="solicitations", type="SolicitationResponse", model_class=ResponseRecord
        )

    def create_response(
        self, solicitation_record: SolicitationRecord, username: str, data_dict: dict
    ) -> ResponseRecord:
        """
        Create a new response via production API.

        Args:
            solicitation_record: Solicitation being responded to
            username: Username submitting the response
            data_dict: Dictionary containing response data

        Returns:
            ResponseRecord instance
        """
        return self.labs_api.create_record(
            experiment="solicitations",
            type="SolicitationResponse",
            data=data_dict,
            labs_record_id=solicitation_record.id,
            username=username,
            program_id=solicitation_record.program_id,
        )

    def get_review_by_user(self, response_record: ResponseRecord, username: str) -> ReviewRecord | None:
        """
        Get a specific user's review of a response.

        Args:
            response_record: Response to find review for
            username: Username who created the review

        Returns:
            ReviewRecord instance or None
        """
        records = self.labs_api.get_records(
            experiment="solicitations",
            type="SolicitationReview",
            labs_record_id=response_record.id,
            username=username,
            model_class=ReviewRecord,
        )

        return records[0] if records else None

    def create_review(self, response_record: ResponseRecord, reviewer_username: str, data_dict: dict) -> ReviewRecord:
        """
        Create a new review via production API.

        Args:
            response_record: Response being reviewed
            reviewer_username: Username of reviewer
            data_dict: Dictionary containing review data

        Returns:
            ReviewRecord instance
        """
        return self.labs_api.create_record(
            experiment="solicitations",
            type="SolicitationReview",
            data=data_dict,
            labs_record_id=response_record.id,
            username=reviewer_username,
            program_id=response_record.program_id,
        )

    def get_responses_for_organization(self, organization_id: str, status: str | None = None) -> list[ResponseRecord]:
        """
        Get all responses submitted by an organization.

        Args:
            organization_id: Organization slug/ID that submitted responses
            status: Optional status filter ('draft', 'submitted')

        Returns:
            List of ResponseRecord instances
        """
        kwargs = {}
        if status:
            kwargs["status"] = status

        # Don't pass organization_id if it's a slug (string), only if it's an actual ID (int)
        # The client is already scoped by program_id or opportunity_id
        org_id_param = {}
        if organization_id and isinstance(organization_id, int):
            org_id_param["organization_id"] = organization_id

        return self.labs_api.get_records(
            experiment="solicitations",
            type="SolicitationResponse",
            model_class=ResponseRecord,
            **org_id_param,
            **kwargs,
        )
