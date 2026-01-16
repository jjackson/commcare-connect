"""
Data Access Layer for Workflows.

This layer uses LabsRecordAPIClient to interact with production LabsRecord API.
It handles:
1. Managing workflow definitions, render code, and runs via production API
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


class WorkflowRunRecord(LocalLabsRecord):
    """Proxy model for workflow run LabsRecords."""

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


class WorkflowChatHistoryRecord(LocalLabsRecord):
    """Proxy model for workflow chat history LabsRecords."""

    @property
    def definition_id(self):
        return self.data.get("definition_id")

    @property
    def messages(self):
        return self.data.get("messages", [])

    @property
    def created_at(self):
        return self.data.get("created_at")

    @property
    def updated_at(self):
        return self.data.get("updated_at")


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
        result = self.labs_api.update_record(
            record_id=definition_id,
            experiment=self.EXPERIMENT,
            type="workflow_definition",
            data=data,
        )
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
            result = self.labs_api.update_record(
                record_id=existing.id,
                experiment=self.EXPERIMENT,
                type="workflow_render_code",
                data=data,
            )
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
    # Workflow Run Methods
    # -------------------------------------------------------------------------

    def list_runs(self, definition_id: int | None = None) -> list[WorkflowRunRecord]:
        """
        List workflow runs.

        Args:
            definition_id: Optional filter by definition ID

        Returns:
            List of WorkflowRunRecord instances
        """
        records = self.labs_api.get_records(
            experiment=self.EXPERIMENT,
            type="workflow_run",
            model_class=WorkflowRunRecord,
        )

        if definition_id:
            records = [r for r in records if r.data.get("definition_id") == definition_id]

        return records

    def get_run(self, run_id: int) -> WorkflowRunRecord | None:
        """
        Get a workflow run by ID.

        Args:
            run_id: Run ID

        Returns:
            WorkflowRunRecord or None if not found
        """
        return self.labs_api.get_record_by_id(
            record_id=run_id,
            experiment=self.EXPERIMENT,
            type="workflow_run",
            model_class=WorkflowRunRecord,
        )

    def get_or_create_run(self, definition_id: int, opportunity_id: int) -> WorkflowRunRecord:
        """
        Get or create a workflow run for the current week.

        Args:
            definition_id: Definition ID
            opportunity_id: Opportunity ID

        Returns:
            WorkflowRunRecord (existing or newly created)
        """
        # Calculate current week boundaries
        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())  # Monday
        week_end = week_start + timedelta(days=6)  # Sunday

        # Look for existing run for this week
        runs = self.list_runs(definition_id)
        for run in runs:
            if run.opportunity_id == opportunity_id and run.data.get("period_start") == week_start.isoformat():
                return run

        # Create new run
        data = {
            "definition_id": definition_id,
            "period_start": week_start.isoformat(),
            "period_end": week_end.isoformat(),
            "status": "in_progress",
            "state": {},
        }

        record = self.labs_api.create_record(
            experiment=self.EXPERIMENT,
            type="workflow_run",
            data=data,
        )

        return WorkflowRunRecord(
            {
                "id": record.id,
                "experiment": record.experiment,
                "type": record.type,
                "data": record.data,
                "opportunity_id": record.opportunity_id,
            }
        )

    def create_run(
        self, definition_id: int, opportunity_id: int, period_start: str, period_end: str, initial_state: dict = None
    ) -> WorkflowRunRecord:
        """
        Create a new workflow run.

        Args:
            definition_id: Definition ID
            opportunity_id: Opportunity ID
            period_start: Period start date (ISO format)
            period_end: Period end date (ISO format)
            initial_state: Initial state data

        Returns:
            Created WorkflowRunRecord
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
            type="workflow_run",
            data=data,
        )

        return WorkflowRunRecord(
            {
                "id": record.id,
                "experiment": record.experiment,
                "type": record.type,
                "data": record.data,
                "opportunity_id": record.opportunity_id,
            }
        )

    def update_run_state(self, run_id: int, new_state: dict) -> WorkflowRunRecord | None:
        """
        Update workflow run state.

        Args:
            run_id: Run ID
            new_state: New state data (merged with existing)

        Returns:
            Updated WorkflowRunRecord or None
        """
        run = self.get_run(run_id)
        if not run:
            return None

        # Merge state
        current_state = run.data.get("state", {})
        merged_state = {**current_state, **new_state}

        # Update data
        updated_data = {**run.data, "state": merged_state}

        result = self.labs_api.update_record(
            record_id=run_id,
            experiment=self.EXPERIMENT,
            type="workflow_run",
            data=updated_data,
        )
        if result:
            return WorkflowRunRecord(
                {
                    "id": result.id,
                    "experiment": result.experiment,
                    "type": result.type,
                    "data": result.data,
                    "opportunity_id": result.opportunity_id,
                }
            )
        return None

    def complete_run(self, run_id: int) -> WorkflowRunRecord | None:
        """
        Mark a workflow run as completed.

        Args:
            run_id: Run ID

        Returns:
            Updated WorkflowRunRecord or None
        """
        run = self.get_run(run_id)
        if not run:
            return None

        updated_data = {**run.data, "status": "completed", "completed_at": datetime.now().isoformat()}

        result = self.labs_api.update_record(
            record_id=run_id,
            experiment=self.EXPERIMENT,
            type="workflow_run",
            data=updated_data,
        )
        if result:
            return WorkflowRunRecord(
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
    # Chat History Methods
    # -------------------------------------------------------------------------

    def get_chat_history(self, definition_id: int) -> WorkflowChatHistoryRecord | None:
        """
        Get chat history for a workflow definition.

        Args:
            definition_id: Definition ID

        Returns:
            WorkflowChatHistoryRecord or None if not found
        """
        records = self.labs_api.get_records(
            experiment=self.EXPERIMENT,
            type="workflow_chat_history",
            model_class=WorkflowChatHistoryRecord,
        )

        logger.info(
            f"Looking for chat history for definition {definition_id}, found {len(records)} chat history records"
        )

        # Find the one matching this definition (compare as int to handle type differences)
        definition_id_int = int(definition_id)
        for record in records:
            record_def_id = record.data.get("definition_id")
            logger.debug(
                f"Checking record {record.id}: definition_id={record_def_id} (type={type(record_def_id).__name__})"
            )
            if record_def_id is not None and int(record_def_id) == definition_id_int:
                logger.info(f"Found chat history record {record.id} with {len(record.messages)} messages")
                return record

        logger.info(f"No chat history found for definition {definition_id}")
        return None

    def get_chat_messages(self, definition_id: int) -> list[dict]:
        """
        Get chat messages for a workflow definition.

        Args:
            definition_id: Definition ID

        Returns:
            List of message dicts with 'role' and 'content' keys
        """
        record = self.get_chat_history(definition_id)
        if record:
            return record.messages
        return []

    def save_chat_history(self, definition_id: int, messages: list[dict]) -> WorkflowChatHistoryRecord:
        """
        Save chat history for a workflow definition.

        Args:
            definition_id: Definition ID
            messages: List of message dicts

        Returns:
            Created or updated WorkflowChatHistoryRecord
        """
        now = datetime.now().isoformat()
        definition_id_int = int(definition_id)  # Ensure it's stored as int
        existing = self.get_chat_history(definition_id_int)

        data = {
            "definition_id": definition_id_int,
            "messages": messages,
            "updated_at": now,
        }

        if existing:
            # Update existing - preserve created_at
            data["created_at"] = existing.data.get("created_at", now)
            result = self.labs_api.update_record(
                record_id=existing.id,
                experiment=self.EXPERIMENT,
                type="workflow_chat_history",
                data=data,
            )
        else:
            # Create new
            data["created_at"] = now
            result = self.labs_api.create_record(
                experiment=self.EXPERIMENT,
                type="workflow_chat_history",
                data=data,
            )

        return WorkflowChatHistoryRecord(
            {
                "id": result.id,
                "experiment": result.experiment,
                "type": result.type,
                "data": result.data,
                "opportunity_id": result.opportunity_id,
            }
        )

    def add_chat_message(self, definition_id: int, role: str, content: str) -> bool:
        """
        Add a single message to the chat history.

        Args:
            definition_id: Definition ID
            role: Message role ('user' or 'assistant')
            content: Message content

        Returns:
            True if successful
        """
        messages = self.get_chat_messages(definition_id)
        messages.append({"role": role, "content": content})
        self.save_chat_history(definition_id, messages)
        return True

    def clear_chat_history(self, definition_id: int) -> bool:
        """
        Clear chat history for a workflow definition.

        Args:
            definition_id: Definition ID

        Returns:
            True if cleared, False if not found
        """
        existing = self.get_chat_history(definition_id)
        if existing:
            # Delete the record by setting messages to empty
            # (or we could actually delete the record if the API supports it)
            self.save_chat_history(definition_id, [])
            return True
        return False

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
