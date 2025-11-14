"""
Labs Record API Client

Pure API client for production LabsRecord endpoints. No local storage.
All operations are performed via HTTP calls to production API.
"""

import logging

import httpx
from django.conf import settings

from commcare_connect.labs.models import LocalLabsRecord

logger = logging.getLogger(__name__)


class LabsAPIError(Exception):
    """Exception raised for Labs API errors."""

    pass


class LabsRecordAPIClient:
    """API client for production LabsRecord endpoints.

    This client makes HTTP calls to production's data_export API endpoints
    and returns LocalLabsRecord instances. No local database storage.
    """

    def __init__(self, access_token: str, opportunity_id: int):
        """Initialize API client.

        Args:
            access_token: OAuth Bearer token for production API
            opportunity_id: Opportunity ID for scoped API requests
        """
        self.access_token = access_token
        self.opportunity_id = opportunity_id
        self.base_url = settings.CONNECT_PRODUCTION_URL.rstrip("/")
        self.http_client = httpx.Client(
            headers={"Authorization": f"Bearer {self.access_token}"},
            timeout=30.0,
        )

    def close(self):
        """Close HTTP client."""
        if self.http_client:
            self.http_client.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close client."""
        self.close()

    def get_records(
        self,
        experiment: str,
        type: str,
        username: str | None = None,
        organization_id: str | None = None,
        program_id: int | None = None,
        labs_record_id: int | None = None,
        model_class: type[LocalLabsRecord] | None = None,
        **data_filters,
    ) -> list[LocalLabsRecord]:
        """Fetch records from production API.

        Args:
            experiment: Experiment name (e.g., 'audit', 'tasks', 'solicitations')
            type: Record type (e.g., 'AuditSession', 'Task')
            username: Filter by username
            organization_id: Filter by organization slug/ID
            program_id: Filter by program ID
            labs_record_id: Filter by parent record ID
            model_class: Optional proxy model class to instantiate (e.g., AuditSessionRecord)
            **data_filters: Additional filters for JSON data fields

        Returns:
            List of LocalLabsRecord instances (or proxy model instances if model_class provided)

        Raises:
            LabsAPIError: If API request fails
        """
        try:
            # Build query parameters
            params = {
                "experiment": experiment,
                "type": type,
            }

            if username:
                params["username"] = username
            if organization_id:
                params["organization_id"] = organization_id
            if program_id:
                params["program_id"] = program_id
            if labs_record_id:
                params["labs_record_id"] = labs_record_id

            # Add data filters (for JSON field queries)
            for key, value in data_filters.items():
                params[f"data__{key}"] = value

            # Make API request
            url = f"{self.base_url}/export/opportunity/{self.opportunity_id}/labs_record/"
            logger.debug(f"GET {url} with params: {params}")

            response = self.http_client.get(url, params=params)
            response.raise_for_status()

            # Deserialize to LocalLabsRecord instances (or proxy model if specified)
            records_data = response.json()
            record_class = model_class if model_class else LocalLabsRecord
            return [record_class(item) for item in records_data]

        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch records: {e}", exc_info=True)
            raise LabsAPIError(f"Failed to fetch records from production API: {e}") from e

    def get_record_by_id(
        self,
        record_id: int,
        experiment: str,
        type: str,
        model_class: type[LocalLabsRecord] | None = None,
    ) -> LocalLabsRecord | None:
        """Get a single record by ID.

        Args:
            record_id: Record ID
            experiment: Experiment name (for filtering)
            type: Record type (for filtering)
            model_class: Optional proxy model class to instantiate

        Returns:
            LocalLabsRecord instance (or proxy model) or None if not found
        """
        # Fetch all records and filter by ID
        records = self.get_records(experiment=experiment, type=type, model_class=model_class)
        for record in records:
            if record.id == record_id:
                return record
        return None

    def create_record(
        self,
        experiment: str,
        type: str,
        data: dict,
        username: str | None = None,
        program_id: int | None = None,
        labs_record_id: int | None = None,
    ) -> LocalLabsRecord:
        """Create a new record in production.

        Args:
            experiment: Experiment name
            type: Record type
            data: JSON data to store
            username: Username to associate record with
            program_id: Program ID
            labs_record_id: Parent record ID

        Returns:
            Created LocalLabsRecord instance

        Raises:
            LabsAPIError: If API request fails
        """
        payload = {
            "experiment": experiment,
            "type": type,
            "data": data,
        }

        if username:
            payload["username"] = username
        if program_id:
            payload["program_id"] = program_id
        if labs_record_id:
            payload["labs_record_id"] = labs_record_id

        # TEMPORARY WORKAROUND: Generate fake ID to work around production API bug
        # Production has update_or_create(id=None) bug - sending a fake ID works around it
        # Remove this once PR is merged and deployed
        import time

        fake_id = int(time.time() * 1000) % 10000 + 50000
        payload["id"] = fake_id
        logger.info(f"WORKAROUND: Using fake ID {fake_id} (remove after production deployment)")

        try:
            url = f"{self.base_url}/export/opportunity/{self.opportunity_id}/labs_record/"
            logger.info(f"POST {url} with payload: {payload}")

            # DEBUG: Print exact API call details
            import json

            print("\n" + "=" * 80)
            print("API WRITE CALL - CREATE RECORD")
            print("=" * 80)
            print(f"URL: {url}")
            print("Method: POST")
            print(f"Headers: Authorization: Bearer {self.access_token[:20]}...")
            print("Payload (will be sent as list):")
            print(json.dumps([payload], indent=2))
            print("=" * 80 + "\n")

            response = self.http_client.post(url, json=[payload])

            # DEBUG: Print response details
            print(f"Response Status: {response.status_code}")
            if response.status_code >= 400:
                print(f"Error Response Body: {response.text}")

            response.raise_for_status()

            # API returns list, get first item
            result = response.json()
            print(f"Success Response: {json.dumps(result, indent=2)}")

            if not result:
                raise LabsAPIError("API returned empty response after create")

            return LocalLabsRecord(result[0])

        except httpx.HTTPError as e:
            logger.error(f"Failed to create record: {e}", exc_info=True)
            print("\nERROR DETAILS:")
            print(f"Exception: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"Response Status: {e.response.status_code}")
                print(f"Response Body: {e.response.text}")
            raise LabsAPIError(f"Failed to create record in production API: {e}") from e

    def update_record(
        self,
        record_id: int,
        experiment: str,
        type: str,
        data: dict,
        username: str | None = None,
        program_id: int | None = None,
        labs_record_id: int | None = None,
    ) -> LocalLabsRecord:
        """Update an existing record in production (upsert).

        Args:
            record_id: ID of record to update
            experiment: Experiment name (required to fetch current record)
            type: Record type (required to fetch current record)
            data: New JSON data
            username: Updated username
            program_id: Updated program ID
            labs_record_id: Updated parent record ID

        Returns:
            Updated LocalLabsRecord instance

        Raises:
            LabsAPIError: If API request fails
        """
        # Get current record to merge fields
        current = self.get_record_by_id(record_id, experiment=experiment, type=type)
        if not current:
            raise LabsAPIError(f"Record {record_id} not found")

        payload = {
            "id": record_id,
            "experiment": current.experiment,
            "type": current.type,
            "data": data,
        }

        if username is not None:
            payload["username"] = username
        elif current.username:
            payload["username"] = current.username

        if program_id is not None:
            payload["program_id"] = program_id
        elif current.program_id:
            payload["program_id"] = current.program_id

        if labs_record_id is not None:
            payload["labs_record_id"] = labs_record_id
        elif current.labs_record_id:
            payload["labs_record_id"] = current.labs_record_id

        try:
            url = f"{self.base_url}/export/opportunity/{self.opportunity_id}/labs_record/"
            logger.info(f"POST {url} (update) with payload: {payload}")

            # DEBUG: Print exact API call details
            import json

            print("\n" + "=" * 80)
            print("API WRITE CALL - UPDATE RECORD")
            print("=" * 80)
            print(f"URL: {url}")
            print("Method: POST")
            print(f"Headers: Authorization: Bearer {self.access_token[:20]}...")
            print("Payload (will be sent as list):")
            print(json.dumps([payload], indent=2))
            print("=" * 80 + "\n")

            response = self.http_client.post(url, json=[payload])

            # DEBUG: Print response details
            print(f"Response Status: {response.status_code}")
            if response.status_code >= 400:
                print(f"Error Response Body: {response.text}")

            response.raise_for_status()

            # API returns list, get first item
            result = response.json()
            print(f"Success Response: {json.dumps(result, indent=2)}")

            if not result:
                raise LabsAPIError("API returned empty response after update")

            return LocalLabsRecord(result[0])

        except httpx.HTTPError as e:
            logger.error(f"Failed to update record: {e}", exc_info=True)
            print("\nERROR DETAILS:")
            print(f"Exception: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"Response Status: {e.response.status_code}")
                print(f"Response Body: {e.response.text}")
            raise LabsAPIError(f"Failed to update record in production API: {e}") from e

    def delete_record(self, record_id: int) -> None:
        """Delete a record (if supported by API).

        Args:
            record_id: ID of record to delete

        Raises:
            NotImplementedError: Delete not yet supported by production API
        """
        raise NotImplementedError("Delete operation not yet supported by production LabsRecord API")
