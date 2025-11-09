"""
Labs API Helper Functions

Utility functions for calling Connect production APIs with OAuth tokens.
Following the audit app's APIFacade pattern.
"""
import logging

import httpx
from django.conf import settings
from django.db.models import QuerySet

logger = logging.getLogger(__name__)


def fetch_user_organization_data(access_token: str) -> dict | None:
    """
    Fetch user's organizations, programs, and opportunities from production.

    Uses the /export/opp_org_program_list/ API endpoint.

    Args:
        access_token: OAuth Bearer token for Connect production

    Returns:
        Dict with 'organizations', 'programs', 'opportunities' keys, or None if fails.
    """
    try:
        response = httpx.get(
            f"{settings.CONNECT_PRODUCTION_URL}/export/opp_org_program_list/",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Failed to fetch organization data: {str(e)}", exc_info=True)
        return None


class ExperimentRecordAPI:
    """
    Generic API helper for ExperimentRecord CRUD operations.

    This class simulates how labs projects will interact with production APIs.
    Currently uses direct database queries, but the interface is designed to
    make transitioning to real API calls straightforward.

    Returns untyped ExperimentRecord instances - experiment-specific code
    should cast these to appropriate proxy models.
    """

    def get_records(
        self,
        experiment: str,
        type: str,
        user_id: int | None = None,
        opportunity_id: int | None = None,
        organization_id: str | None = None,
        program_id: int | None = None,
        parent_id: int | None = None,
        data_filters: dict | None = None,
    ) -> QuerySet:
        """
        Query ExperimentRecords with filters.

        Args:
            experiment: Experiment name (e.g., 'solicitations')
            type: Record type (e.g., 'Solicitation', 'SolicitationResponse')
            user_id: Filter by user ID
            opportunity_id: Filter by opportunity ID
            organization_id: Filter by organization slug/ID
            program_id: Filter by program ID
            parent_id: Filter by parent record ID
            data_filters: Dict of JSON field filters (e.g., {'status': 'active'})

        Returns:
            QuerySet of ExperimentRecord instances (not cast to proxy types)
        """
        from commcare_connect.labs.models import ExperimentRecord

        qs = ExperimentRecord.objects.filter(experiment=experiment, type=type)

        if user_id is not None:
            qs = qs.filter(user_id=user_id)

        if opportunity_id is not None:
            qs = qs.filter(opportunity_id=opportunity_id)

        if organization_id is not None:
            qs = qs.filter(organization_id=organization_id)

        if program_id is not None:
            qs = qs.filter(program_id=program_id)

        if parent_id is not None:
            qs = qs.filter(parent_id=parent_id)

        # Apply JSON field filters
        if data_filters:
            for key, value in data_filters.items():
                qs = qs.filter(**{f"data__{key}": value})

        return qs

    def get_record_by_id(self, record_id: int, experiment: str, type: str):
        """
        Get a single ExperimentRecord by ID.

        Args:
            record_id: Record ID
            experiment: Experiment name (for validation)
            type: Record type (for validation)

        Returns:
            ExperimentRecord instance or None if not found
        """
        from commcare_connect.labs.models import ExperimentRecord

        try:
            return ExperimentRecord.objects.get(id=record_id, experiment=experiment, type=type)
        except ExperimentRecord.DoesNotExist:
            return None

    def create_record(
        self,
        experiment: str,
        type: str,
        data: dict,
        user_id: int | None = None,
        opportunity_id: int | None = None,
        organization_id: str | None = None,
        program_id: int | None = None,
        parent_id: int | None = None,
    ):
        """
        Create a new ExperimentRecord.

        Args:
            experiment: Experiment name (e.g., 'solicitations')
            type: Record type (e.g., 'Solicitation')
            data: Dict of data to store in JSON field
            user_id: User ID who created this
            opportunity_id: Associated opportunity ID
            organization_id: Associated organization slug/ID
            program_id: Associated program ID
            parent_id: Parent record ID (for hierarchical records)

        Returns:
            Created ExperimentRecord instance
        """
        from commcare_connect.labs.models import ExperimentRecord

        return ExperimentRecord.objects.create(
            experiment=experiment,
            type=type,
            data=data,
            user_id=user_id,
            opportunity_id=opportunity_id,
            organization_id=organization_id,
            program_id=program_id,
            parent_id=parent_id,
        )

    def update_record(
        self,
        record_id: int,
        data: dict | None = None,
        user_id: int | None = None,
        opportunity_id: int | None = None,
        organization_id: str | None = None,
        program_id: int | None = None,
    ):
        """
        Update an existing ExperimentRecord.

        Args:
            record_id: ID of record to update
            data: New data dict (if provided, replaces existing data)
            user_id: Update user ID
            opportunity_id: Update opportunity ID
            organization_id: Update organization slug/ID
            program_id: Update program ID

        Returns:
            Updated ExperimentRecord instance

        Raises:
            ExperimentRecord.DoesNotExist: If record not found
        """
        from commcare_connect.labs.models import ExperimentRecord

        record = ExperimentRecord.objects.get(id=record_id)

        if data is not None:
            record.data = data

        if user_id is not None:
            record.user_id = user_id

        if opportunity_id is not None:
            record.opportunity_id = opportunity_id

        if organization_id is not None:
            record.organization_id = organization_id

        if program_id is not None:
            record.program_id = program_id

        record.save()
        return record
