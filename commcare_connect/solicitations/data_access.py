"""
Data Access Layer for Solicitations.

This layer wraps the generic ExperimentRecordAPI to provide solicitations-specific
data access methods. It handles casting ExperimentRecords to typed proxy models
(SolicitationRecord, ResponseRecord, ReviewRecord).

This abstraction prepares for eventual production API integration.
"""

from django.db.models import QuerySet

from commcare_connect.labs.api_helpers import ExperimentRecordAPI
from commcare_connect.solicitations.experiment_models import ResponseRecord, ReviewRecord, SolicitationRecord
from commcare_connect.users.models import User


class SolicitationDataAccess:
    """
    Data access layer for solicitations that uses ExperimentRecordAPI.

    This class provides solicitation-specific methods and handles casting
    untyped ExperimentRecords to appropriate proxy model types.
    """

    def __init__(self):
        self.api = ExperimentRecordAPI()

    def get_solicitations(
        self,
        program_id: int | None = None,
        status: str | None = None,
        solicitation_type: str | None = None,
        is_publicly_listed: bool | None = None,
    ) -> QuerySet[SolicitationRecord]:
        """
        Query for solicitation records with optional filters.

        Args:
            program_id: Filter by production program ID
            status: Filter by status ('active', 'closed', 'draft')
            solicitation_type: Filter by type ('eoi', 'rfp')
            is_publicly_listed: Filter by public listing status

        Returns:
            QuerySet of SolicitationRecord instances
        """
        # Build data_filters for JSON field queries
        data_filters = {}
        if status:
            data_filters["status"] = status
        if solicitation_type:
            data_filters["solicitation_type"] = solicitation_type
        if is_publicly_listed is not None:
            data_filters["is_publicly_listed"] = is_publicly_listed

        # Get ExperimentRecords from API
        qs = self.api.get_records(
            experiment="solicitations",
            type="Solicitation",
            program_id=program_id,
            data_filters=data_filters if data_filters else None,
        )

        # Cast to SolicitationRecord proxy model by re-querying with the proxy model manager
        return SolicitationRecord.objects.filter(pk__in=qs.values_list("pk", flat=True))

    def get_solicitation_by_id(self, solicitation_id: int) -> SolicitationRecord | None:
        """
        Get a single solicitation record by ID.

        Args:
            solicitation_id: ID of the solicitation

        Returns:
            SolicitationRecord instance or None
        """
        record = self.api.get_record_by_id(record_id=solicitation_id, experiment="solicitations", type="Solicitation")

        if record:
            # Cast to SolicitationRecord proxy model
            record.__class__ = SolicitationRecord
            return record
        return None

    def create_solicitation(
        self, program_id: int, organization_id: str | None, user_id: int, data_dict: dict
    ) -> SolicitationRecord:
        """
        Create a new solicitation ExperimentRecord.

        Args:
            program_id: Production program ID
            organization_id: Production organization ID/slug
            user_id: Production user ID who created this
            data_dict: Dictionary containing solicitation data

        Returns:
            SolicitationRecord instance
        """
        record = self.api.create_record(
            experiment="solicitations",
            type="Solicitation",
            data=data_dict,
            program_id=program_id,
            organization_id=organization_id,
            user_id=user_id,
        )

        # Cast to SolicitationRecord proxy model
        record.__class__ = SolicitationRecord
        return record

    def get_responses_for_solicitation(
        self, solicitation_record: SolicitationRecord, status: str | None = None
    ) -> QuerySet[ResponseRecord]:
        """
        Get all responses for a solicitation.

        Args:
            solicitation_record: Solicitation to find responses for
            status: Optional status filter ('draft', 'submitted')

        Returns:
            QuerySet of ResponseRecord instances
        """
        data_filters = {}
        if status:
            data_filters["status"] = status

        qs = self.api.get_records(
            experiment="solicitations",
            type="SolicitationResponse",
            parent_id=solicitation_record.id,
            data_filters=data_filters if data_filters else None,
        )

        # Cast to ResponseRecord proxy model by re-querying with the proxy model manager
        return ResponseRecord.objects.filter(pk__in=qs.values_list("pk", flat=True))

    def get_response_for_solicitation(
        self,
        solicitation_record: SolicitationRecord,
        organization_id: str,
        user_id: int | None = None,
        status: str | None = None,
    ) -> ResponseRecord | None:
        """
        Find a response by a specific organization for a solicitation.

        Args:
            solicitation_record: Solicitation to find response for
            organization_id: Organization slug/ID that submitted the response
            user_id: Optional user ID filter
            status: Optional status filter ('draft', 'submitted')

        Returns:
            ResponseRecord instance or None
        """
        data_filters = {}
        if status:
            data_filters["status"] = status

        qs = self.api.get_records(
            experiment="solicitations",
            type="SolicitationResponse",
            parent_id=solicitation_record.id,
            organization_id=organization_id,
            user_id=user_id,
            data_filters=data_filters if data_filters else None,
        )

        # Cast to ResponseRecord and return first
        typed_qs = ResponseRecord.objects.filter(pk__in=qs.values_list("pk", flat=True))
        return typed_qs.first()

    def get_response_by_id(self, response_id: int) -> ResponseRecord | None:
        """
        Get a single response record by ID.

        Args:
            response_id: ID of the response

        Returns:
            ResponseRecord instance or None
        """
        record = self.api.get_record_by_id(
            record_id=response_id, experiment="solicitations", type="SolicitationResponse"
        )

        if record:
            # Cast to ResponseRecord proxy model
            record.__class__ = ResponseRecord
            return record
        return None

    def create_response(
        self, solicitation_record: SolicitationRecord, organization_id: str, user_id: int, data_dict: dict
    ) -> ResponseRecord:
        """
        Create a new response ExperimentRecord.

        Args:
            solicitation_record: Solicitation being responded to
            organization_id: Production organization ID/slug submitting the response
            user_id: Production user ID submitting the response
            data_dict: Dictionary containing response data

        Returns:
            ResponseRecord instance
        """
        record = self.api.create_record(
            experiment="solicitations",
            type="SolicitationResponse",
            data=data_dict,
            parent_id=solicitation_record.id,
            organization_id=organization_id,
            user_id=user_id,
            program_id=solicitation_record.program_id,
        )

        # Cast to ResponseRecord proxy model
        record.__class__ = ResponseRecord
        return record

    def get_review_by_user(self, response_record: ResponseRecord, user: User) -> ReviewRecord | None:
        """
        Get a specific user's review of a response.

        Args:
            response_record: Response to find review for
            user: User who created the review

        Returns:
            ReviewRecord instance or None
        """
        qs = self.api.get_records(
            experiment="solicitations",
            type="SolicitationReview",
            parent_id=response_record.id,
            user_id=user.id,
        )

        # Cast to ReviewRecord and return first
        typed_qs = ReviewRecord.objects.filter(pk__in=qs.values_list("pk", flat=True))
        return typed_qs.first()

    def create_review(self, response_record: ResponseRecord, reviewer_id: int, data_dict: dict) -> ReviewRecord:
        """
        Create a new review ExperimentRecord.

        Args:
            response_record: Response being reviewed
            reviewer_id: Production user ID of reviewer
            data_dict: Dictionary containing review data

        Returns:
            ReviewRecord instance
        """
        record = self.api.create_record(
            experiment="solicitations",
            type="SolicitationReview",
            data=data_dict,
            parent_id=response_record.id,
            user_id=reviewer_id,
            organization_id=response_record.organization_id,
            program_id=response_record.program_id,
        )

        # Cast to ReviewRecord proxy model
        record.__class__ = ReviewRecord
        return record

    def get_responses_for_organization(
        self, organization_id: str, status: str | None = None
    ) -> QuerySet[ResponseRecord]:
        """
        Get all responses submitted by an organization.

        Args:
            organization_id: Organization slug/ID that submitted responses
            status: Optional status filter ('draft', 'submitted')

        Returns:
            QuerySet of ResponseRecord instances
        """
        data_filters = {}
        if status:
            data_filters["status"] = status

        qs = self.api.get_records(
            experiment="solicitations",
            type="SolicitationResponse",
            organization_id=organization_id,
            data_filters=data_filters if data_filters else None,
        )

        # Cast to ResponseRecord proxy model by re-querying with the proxy model manager
        return ResponseRecord.objects.filter(pk__in=qs.values_list("pk", flat=True))
