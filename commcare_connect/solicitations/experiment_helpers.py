"""
Helper functions for working with ExperimentRecords in solicitations.

These functions provide convenient interfaces for creating and querying
solicitation-related ExperimentRecords. They delegate to the SolicitationDataAccess
layer which uses the ExperimentRecordAPI.
"""

from django.db.models import QuerySet

from commcare_connect.organization.models import Organization
from commcare_connect.solicitations.data_access import SolicitationDataAccess
from commcare_connect.solicitations.experiment_models import ResponseRecord, ReviewRecord, SolicitationRecord
from commcare_connect.users.models import User

# Initialize the data access layer
_data_access = SolicitationDataAccess()


# =============================================================================
# Create Functions
# =============================================================================


def create_solicitation_record(
    program_id: int, organization_id: int, user_id: int, data_dict: dict
) -> SolicitationRecord:
    """
    Create a new solicitation ExperimentRecord.

    Args:
        program_id: Production program ID
        organization_id: Production organization ID/slug
        user_id: Production user ID who created this
        data_dict: Dictionary containing solicitation data
                  Expected keys: title, description, solicitation_type, status,
                  questions (list), application_deadline, etc.

    Returns:
        SolicitationRecord instance
    """
    return _data_access.create_solicitation(
        program_id=program_id, organization_id=organization_id, user_id=user_id, data_dict=data_dict
    )


def create_response_record(
    solicitation_record: SolicitationRecord, organization_id: str, user_id: int, data_dict: dict
) -> ResponseRecord:
    """
    Create a new response ExperimentRecord.

    Args:
        solicitation_record: Solicitation being responded to
        organization_id: Production organization slug/ID submitting the response
        user_id: Production user ID submitting the response
        data_dict: Dictionary containing response data
                  Expected keys: responses (dict), status, attachments (list), etc.

    Returns:
        ResponseRecord instance
    """
    return _data_access.create_response(
        solicitation_record=solicitation_record, organization_id=organization_id, user_id=user_id, data_dict=data_dict
    )


def create_review_record(response_record: ResponseRecord, reviewer_id: int, data_dict: dict) -> ReviewRecord:
    """
    Create a new review ExperimentRecord.

    Args:
        response_record: Response being reviewed
        reviewer_id: Production user ID of reviewer
        data_dict: Dictionary containing review data
                  Expected keys: score, recommendation, notes, tags, etc.

    Returns:
        ReviewRecord instance
    """
    return _data_access.create_review(response_record=response_record, reviewer_id=reviewer_id, data_dict=data_dict)


# =============================================================================
# Query Functions
# =============================================================================


def get_solicitations(
    program_id: int | None = None,
    status: str | None = None,
    solicitation_type: str | None = None,
    is_publicly_listed: bool | None = None,
) -> QuerySet:
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
    return _data_access.get_solicitations(
        program_id=program_id,
        status=status,
        solicitation_type=solicitation_type,
        is_publicly_listed=is_publicly_listed,
    )


def get_solicitation_by_id(solicitation_id: int) -> SolicitationRecord | None:
    """
    Get a single solicitation record by ID.

    Args:
        solicitation_id: ID of the solicitation

    Returns:
        SolicitationRecord instance or None
    """
    return _data_access.get_solicitation_by_id(solicitation_id)


def get_response_for_solicitation(
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
        user_id: Optional user ID filter (for labs, to find user's specific response)
        status: Optional status filter ('draft', 'submitted')

    Returns:
        ResponseRecord instance or None
    """
    return _data_access.get_response_for_solicitation(
        solicitation_record=solicitation_record, organization_id=organization_id, user_id=user_id, status=status
    )


def get_responses_for_solicitation(solicitation_record: SolicitationRecord, status: str | None = None) -> QuerySet:
    """
    Get all responses for a solicitation.

    Args:
        solicitation_record: Solicitation to find responses for
        status: Optional status filter ('draft', 'submitted')

    Returns:
        QuerySet of ResponseRecord instances
    """
    return _data_access.get_responses_for_solicitation(solicitation_record=solicitation_record, status=status)


def get_response_by_id(response_id: int) -> ResponseRecord | None:
    """
    Get a single response record by ID.

    Args:
        response_id: ID of the response

    Returns:
        ResponseRecord instance or None
    """
    return _data_access.get_response_by_id(response_id)


def get_reviews_for_response(response_record: ResponseRecord) -> QuerySet:
    """
    Get all reviews for a response.

    Args:
        response_record: Response to find reviews for

    Returns:
        QuerySet of ReviewRecord instances
    """
    # This method isn't in the data access layer yet, but we can use the API directly
    from commcare_connect.labs.api_helpers import ExperimentRecordAPI

    api = ExperimentRecordAPI()
    qs = api.get_records(experiment="solicitations", type="SolicitationReview", parent_id=response_record.id)
    return ReviewRecord.objects.filter(pk__in=qs.values_list("pk", flat=True))


def get_review_by_user(response_record: ResponseRecord, user: User) -> ReviewRecord | None:
    """
    Get a specific user's review of a response.

    Args:
        response_record: Response to find review for
        user: User who created the review

    Returns:
        ReviewRecord instance or None
    """
    return _data_access.get_review_by_user(response_record=response_record, user=user)


def get_responses_for_organization(organization: Organization, status: str | None = None) -> QuerySet:
    """
    Get all responses submitted by an organization.

    Args:
        organization: Organization that submitted responses
        status: Optional status filter ('draft', 'submitted')

    Returns:
        QuerySet of ResponseRecord instances
    """
    # For labs, organization is passed as an object, but we use slug for queries
    organization_id = organization.slug if hasattr(organization, "slug") else str(organization)
    return _data_access.get_responses_for_organization(organization_id=organization_id, status=status)
