"""
Data Access Layer for Workflows.

This layer uses LabsRecordAPIClient to interact with production LabsRecord API.
It handles:
1. Managing workflow definitions, render code, and instances via production API
2. Fetching worker data dynamically from Connect OAuth APIs

This is a pure API client with no local database storage.
"""

import logging
import os
import tempfile
from datetime import datetime, timedelta

import httpx
import pandas as pd
from django.conf import settings
from django.http import HttpRequest

from commcare_connect.labs.integrations.connect.api_client import LabsRecordAPIClient
from commcare_connect.labs.models import LocalLabsRecord

logger = logging.getLogger(__name__)


class WorkflowDefinitionRecord(LocalLabsRecord):
    """Proxy model for workflow definition LabsRecords."""

    @property
    def name(self):
        return self.data.get("name", "Untitled Workflow")

    @property
    def description(self):
        return self.data.get("description", "")

    @property
    def version(self):
        return self.data.get("version", 1)

    @property
    def render_code_id(self):
        return self.data.get("render_code_id")


class WorkflowRenderCodeRecord(LocalLabsRecord):
    """Proxy model for workflow render code LabsRecords."""

    @property
    def definition_id(self):
        return self.data.get("definition_id")

    @property
    def component_code(self):
        return self.data.get("component_code", "")

    @property
    def version(self):
        return self.data.get("version", 1)


class WorkflowInstanceRecord(LocalLabsRecord):
    """Proxy model for workflow instance LabsRecords."""

    @property
    def definition_id(self):
        return self.data.get("definition_id")

    @property
    def period_start(self):
        return self.data.get("period_start")

    @property
    def period_end(self):
        return self.data.get("period_end")

    @property
    def status(self):
        return self.data.get("status", "in_progress")

    @property
    def state(self):
        return self.data.get("state", {})


class WorkflowDataAccess:
    """
    Data access layer for workflows that uses LabsRecordAPIClient for state
    and fetches worker data via OAuth APIs.
    """

    EXPERIMENT = "workflow"

    def __init__(
        self,
        opportunity_id: int | None = None,
        organization_id: int | None = None,
        program_id: int | None = None,
        user=None,
        request: HttpRequest | None = None,
        access_token: str | None = None,
    ):
        """
        Initialize the workflow data access layer.

        Args:
            opportunity_id: Optional opportunity ID for scoped API requests
            organization_id: Optional organization ID for scoped API requests
            program_id: Optional program ID for scoped API requests
            user: Django User object (for OAuth token extraction)
            request: HttpRequest object (for extracting token and org context in labs mode)
            access_token: OAuth token for Connect production APIs
        """
        self.opportunity_id = opportunity_id
        self.organization_id = organization_id
        self.program_id = program_id
        self.user = user
        self.request = request

        # Use labs_context from middleware if available (takes precedence)
        if request and hasattr(request, "labs_context"):
            labs_context = request.labs_context
            if not opportunity_id and "opportunity_id" in labs_context:
                self.opportunity_id = labs_context["opportunity_id"]
            if not program_id and "program_id" in labs_context:
                self.program_id = labs_context["program_id"]
            if not organization_id and "organization_id" in labs_context:
                self.organization_id = labs_context["organization_id"]

        # Get OAuth token
        if not access_token and request:
            # Try to get token from labs session or SocialAccount
            if hasattr(request, "session") and "labs_oauth" in request.session:
                access_token = request.session["labs_oauth"].get("access_token")
            elif user:
                from allauth.socialaccount.models import SocialAccount, SocialToken

                try:
                    social_account = SocialAccount.objects.get(user=user, provider="connect")
                    social_token = SocialToken.objects.get(account=social_account)
                    access_token = social_token.token
                except (SocialAccount.DoesNotExist, SocialToken.DoesNotExist):
                    pass

        if not access_token:
            raise ValueError("OAuth access token required for workflow data access")

        self.access_token = access_token
        self.production_url = settings.CONNECT_PRODUCTION_URL.rstrip("/")

        # Initialize HTTP client with Bearer token
        self.http_client = httpx.Client(
            headers={"Authorization": f"Bearer {self.access_token}"},
            timeout=120.0,
        )

        # Initialize Labs API client for state management
        self.labs_api = LabsRecordAPIClient(
            access_token,
            opportunity_id=self.opportunity_id,
            organization_id=self.organization_id,
            program_id=self.program_id,
        )

    def close(self):
        """Close HTTP client."""
        if self.http_client:
            self.http_client.close()

    # -------------------------------------------------------------------------
    # Workflow Definition Methods
    # -------------------------------------------------------------------------

    def list_definitions(self) -> list[WorkflowDefinitionRecord]:
        """
        List all workflow definitions.

        Returns:
            List of WorkflowDefinitionRecord instances
        """
        return self.labs_api.get_records(
            experiment=self.EXPERIMENT,
            type="workflow_definition",
            model_class=WorkflowDefinitionRecord,
        )

    def get_definition(self, definition_id: int) -> WorkflowDefinitionRecord | None:
        """
        Get a workflow definition by ID.

        Args:
            definition_id: Definition ID

        Returns:
            WorkflowDefinitionRecord or None if not found
        """
        return self.labs_api.get_record_by_id(
            record_id=definition_id,
            experiment=self.EXPERIMENT,
            type="workflow_definition",
            model_class=WorkflowDefinitionRecord,
        )

    def create_definition(self, name: str, description: str, **kwargs) -> WorkflowDefinitionRecord:
        """
        Create a new workflow definition.

        Args:
            name: Workflow name
            description: Workflow description
            **kwargs: Additional data fields

        Returns:
            Created WorkflowDefinitionRecord
        """
        data = {
            "name": name,
            "description": description,
            "version": 1,
            **kwargs,
        }

        record = self.labs_api.create_record(
            experiment=self.EXPERIMENT,
            type="workflow_definition",
            data=data,
        )

        return WorkflowDefinitionRecord(
            {
                "id": record.id,
                "experiment": record.experiment,
                "type": record.type,
                "data": record.data,
                "opportunity_id": record.opportunity_id,
            }
        )

    def update_definition(self, definition_id: int, data: dict) -> WorkflowDefinitionRecord | None:
        """
        Update a workflow definition.

        Args:
            definition_id: Definition ID
            data: Updated data

        Returns:
            Updated WorkflowDefinitionRecord or None
        """
        result = self.labs_api.update_record(definition_id, data)
        if result:
            return WorkflowDefinitionRecord(
                {
                    "id": result.id,
                    "experiment": result.experiment,
                    "type": result.type,
                    "data": result.data,
                    "opportunity_id": result.opportunity_id,
                }
            )
        return None

    # -------------------------------------------------------------------------
    # Workflow Render Code Methods
    # -------------------------------------------------------------------------

    def get_render_code(self, definition_id: int) -> WorkflowRenderCodeRecord | None:
        """
        Get render code for a workflow definition.

        Args:
            definition_id: Definition ID

        Returns:
            WorkflowRenderCodeRecord or None if not found
        """
        records = self.labs_api.get_records(
            experiment=self.EXPERIMENT,
            type="workflow_render_code",
            model_class=WorkflowRenderCodeRecord,
        )

        # Find the one matching this definition
        for record in records:
            if record.data.get("definition_id") == definition_id:
                return record

        return None

    def save_render_code(self, definition_id: int, component_code: str, version: int = 1) -> WorkflowRenderCodeRecord:
        """
        Save render code for a workflow definition.

        Args:
            definition_id: Definition ID
            component_code: React component code
            version: Code version

        Returns:
            Created or updated WorkflowRenderCodeRecord
        """
        # Check if render code already exists
        existing = self.get_render_code(definition_id)

        data = {
            "definition_id": definition_id,
            "component_code": component_code,
            "version": version,
        }

        if existing:
            # Update existing
            result = self.labs_api.update_record(existing.id, data)
        else:
            # Create new
            result = self.labs_api.create_record(
                experiment=self.EXPERIMENT,
                type="workflow_render_code",
                data=data,
            )

        return WorkflowRenderCodeRecord(
            {
                "id": result.id,
                "experiment": result.experiment,
                "type": result.type,
                "data": result.data,
                "opportunity_id": result.opportunity_id,
            }
        )

    # -------------------------------------------------------------------------
    # Workflow Instance Methods
    # -------------------------------------------------------------------------

    def list_instances(self, definition_id: int | None = None) -> list[WorkflowInstanceRecord]:
        """
        List workflow instances.

        Args:
            definition_id: Optional filter by definition ID

        Returns:
            List of WorkflowInstanceRecord instances
        """
        records = self.labs_api.get_records(
            experiment=self.EXPERIMENT,
            type="workflow_instance",
            model_class=WorkflowInstanceRecord,
        )

        if definition_id:
            records = [r for r in records if r.data.get("definition_id") == definition_id]

        return records

    def get_instance(self, instance_id: int) -> WorkflowInstanceRecord | None:
        """
        Get a workflow instance by ID.

        Args:
            instance_id: Instance ID

        Returns:
            WorkflowInstanceRecord or None if not found
        """
        return self.labs_api.get_record_by_id(
            record_id=instance_id,
            experiment=self.EXPERIMENT,
            type="workflow_instance",
            model_class=WorkflowInstanceRecord,
        )

    def get_or_create_instance(self, definition_id: int, opportunity_id: int) -> WorkflowInstanceRecord:
        """
        Get or create a workflow instance for the current week.

        Args:
            definition_id: Definition ID
            opportunity_id: Opportunity ID

        Returns:
            WorkflowInstanceRecord (existing or newly created)
        """
        # Calculate current week boundaries
        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())  # Monday
        week_end = week_start + timedelta(days=6)  # Sunday

        # Look for existing instance for this week
        instances = self.list_instances(definition_id)
        for instance in instances:
            if (
                instance.opportunity_id == opportunity_id
                and instance.data.get("period_start") == week_start.isoformat()
            ):
                return instance

        # Create new instance
        data = {
            "definition_id": definition_id,
            "period_start": week_start.isoformat(),
            "period_end": week_end.isoformat(),
            "status": "in_progress",
            "state": {},
        }

        record = self.labs_api.create_record(
            experiment=self.EXPERIMENT,
            type="workflow_instance",
            data=data,
        )

        return WorkflowInstanceRecord(
            {
                "id": record.id,
                "experiment": record.experiment,
                "type": record.type,
                "data": record.data,
                "opportunity_id": record.opportunity_id,
            }
        )

    def create_instance(
        self, definition_id: int, opportunity_id: int, period_start: str, period_end: str, initial_state: dict = None
    ) -> WorkflowInstanceRecord:
        """
        Create a new workflow instance.

        Args:
            definition_id: Definition ID
            opportunity_id: Opportunity ID
            period_start: Period start date (ISO format)
            period_end: Period end date (ISO format)
            initial_state: Initial state data

        Returns:
            Created WorkflowInstanceRecord
        """
        data = {
            "definition_id": definition_id,
            "period_start": period_start,
            "period_end": period_end,
            "status": "in_progress",
            "state": initial_state or {},
        }

        record = self.labs_api.create_record(
            experiment=self.EXPERIMENT,
            type="workflow_instance",
            data=data,
        )

        return WorkflowInstanceRecord(
            {
                "id": record.id,
                "experiment": record.experiment,
                "type": record.type,
                "data": record.data,
                "opportunity_id": record.opportunity_id,
            }
        )

    def update_instance_state(self, instance_id: int, new_state: dict) -> WorkflowInstanceRecord | None:
        """
        Update workflow instance state.

        Args:
            instance_id: Instance ID
            new_state: New state data (merged with existing)

        Returns:
            Updated WorkflowInstanceRecord or None
        """
        instance = self.get_instance(instance_id)
        if not instance:
            return None

        # Merge state
        current_state = instance.data.get("state", {})
        merged_state = {**current_state, **new_state}

        # Update data
        updated_data = {**instance.data, "state": merged_state}

        result = self.labs_api.update_record(instance_id, updated_data)
        if result:
            return WorkflowInstanceRecord(
                {
                    "id": result.id,
                    "experiment": result.experiment,
                    "type": result.type,
                    "data": result.data,
                    "opportunity_id": result.opportunity_id,
                }
            )
        return None

    def complete_instance(self, instance_id: int) -> WorkflowInstanceRecord | None:
        """
        Mark a workflow instance as completed.

        Args:
            instance_id: Instance ID

        Returns:
            Updated WorkflowInstanceRecord or None
        """
        instance = self.get_instance(instance_id)
        if not instance:
            return None

        updated_data = {**instance.data, "status": "completed", "completed_at": datetime.now().isoformat()}

        result = self.labs_api.update_record(instance_id, updated_data)
        if result:
            return WorkflowInstanceRecord(
                {
                    "id": result.id,
                    "experiment": result.experiment,
                    "type": result.type,
                    "data": result.data,
                    "opportunity_id": result.opportunity_id,
                }
            )
        return None

    # -------------------------------------------------------------------------
    # Worker Data Methods
    # -------------------------------------------------------------------------

    def _call_connect_api(self, endpoint: str) -> httpx.Response:
        """Call Connect production API with OAuth token."""
        url = f"{self.production_url}{endpoint}"
        response = self.http_client.get(url)
        response.raise_for_status()
        return response

    def get_workers(self, opportunity_id: int) -> list[dict]:
        """
        Get workers for an opportunity from Connect API.

        Args:
            opportunity_id: Opportunity ID

        Returns:
            List of worker dicts with username, name, visit_count, last_active
        """
        # Download user data CSV
        endpoint = f"/export/opportunity/{opportunity_id}/user_data/"
        response = self._call_connect_api(endpoint)

        # Save to temp file
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".csv")
        try:
            with os.fdopen(tmp_fd, "wb") as f:
                f.write(response.content)

            # Parse CSV
            df = pd.read_csv(tmp_path)

            logger.info(f"CSV columns for opportunity {opportunity_id}: {list(df.columns)}")
            logger.info(f"CSV has {len(df)} rows")

            workers = []
            for idx, row in df.iterrows():
                username = str(row["username"]) if pd.notna(row.get("username")) else None
                if username:
                    worker = {
                        "username": username,
                        "name": str(row.get("name", username)) if pd.notna(row.get("name")) else username,
                        "visit_count": int(row.get("total_visits", 0)) if pd.notna(row.get("total_visits")) else 0,
                        "last_active": str(row.get("last_active")) if pd.notna(row.get("last_active")) else None,
                    }

                    # Add optional fields if available
                    optional_fields = [
                        "phone_number",
                        "approved_visits",
                        "flagged_visits",
                        "rejected_visits",
                        "email",
                    ]
                    for field in optional_fields:
                        if field in row and pd.notna(row[field]):
                            worker[field] = str(row[field]) if not isinstance(row[field], (int, float)) else row[field]

                    workers.append(worker)

            return workers

        finally:
            os.unlink(tmp_path)
