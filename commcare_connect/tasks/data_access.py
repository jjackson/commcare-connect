"""
Data Access Layer for Tasks.

This layer uses LabsRecordAPIClient to interact with production LabsRecord API.
It handles:
1. Managing task state via production API
2. Fetching opportunity/user data dynamically from Connect OAuth APIs
3. Task operations (add events, comments, AI sessions)

This is a pure API client with no local database storage.
"""

import httpx
from django.conf import settings
from django.http import HttpRequest

from commcare_connect.labs.api_client import LabsRecordAPIClient
from commcare_connect.tasks.models import TaskRecord


class TaskDataAccess:
    """
    Data access layer for tasks that uses LabsRecordAPIClient for state
    and fetches opportunity/user data via OAuth APIs.
    """

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
        Initialize the task data access layer.

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
            raise ValueError("OAuth access token required for task data access")

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

    # Task CRUD Methods

    def create_task(
        self,
        username: str,
        opportunity_id: int,
        created_by_id: int,
        task_type: str = "warning",
        priority: str = "medium",
        title: str = "",
        description: str = "",
        user_id: int | None = None,
        **kwargs,
    ) -> TaskRecord:
        """
        Create a new task.

        Args:
            username: FLW username (primary identifier in Connect)
            opportunity_id: Opportunity ID this task relates to
            created_by_id: User ID who created this task
            task_type: Type of task (warning, deactivation)
            priority: Priority (low, medium, high)
            title: Task title
            description: Task description
            user_id: FLW user ID (optional, may not be available from API)
            **kwargs: Additional fields (learning_assignment_text, audit_session_id, assigned_to_id, status)

        Returns:
            TaskRecord instance with initial "created" event

        Raises:
            ValueError: If username is empty or appears invalid
        """
        # Validate username
        if not username or not username.strip():
            raise ValueError("Username is required to create a task")

        # Warn about suspiciously long usernames (might be tokens or IDs)
        if len(username) > 50:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Creating task with unusually long username (len={len(username)}): {username[:50]}...")
        data = {
            "username": username,
            "user_id": user_id,
            "opportunity_id": opportunity_id,
            "created_by_id": created_by_id,
            "task_type": task_type,
            "status": kwargs.get("status", "unassigned"),
            "priority": priority,
            "title": title,
            "description": description,
            "learning_assignment_text": kwargs.get("learning_assignment_text", ""),
            "audit_session_id": kwargs.get("audit_session_id"),
            "assigned_to_id": kwargs.get("assigned_to_id"),
            "events": [],
            "comments": [],
            "ai_sessions": [],
        }

        record = self.labs_api.create_record(
            experiment="tasks",
            type="Task",
            data=data,
            username=username,  # Use username not user_id
        )

        # Add initial "created" event
        creator_name = kwargs.get("creator_name", f"User {created_by_id}")
        record.add_event(
            event_type="created",
            actor=creator_name,
            actor_user_id=created_by_id,
            description=f"Task created by {creator_name}",
        )
        # Save changes via API
        return self.labs_api.update_record(record.id, record.data)

    def get_task(self, task_id: int) -> TaskRecord | None:
        """
        Get a task by ID.

        Args:
            task_id: Task ID

        Returns:
            TaskRecord or None if not found
        """
        return self.labs_api.get_record_by_id(
            record_id=task_id, experiment="tasks", type="Task", model_class=TaskRecord
        )

    def get_tasks(
        self,
        username: str | None = None,
        status: str | None = None,
        assigned_to_id: int | None = None,
    ) -> list[TaskRecord]:
        """
        Query tasks with filters.

        Args:
            username: Filter by FLW username (from data field, not parent username)
            status: Filter by status
            assigned_to_id: Filter by assigned user ID

        Returns:
            List of TaskRecord instances
        """
        # Pass filters as kwargs for data filters
        kwargs = {}
        if status:
            kwargs["status"] = status
        if assigned_to_id:
            kwargs["assigned_to_id"] = assigned_to_id
        if username:
            kwargs["username"] = username

        return self.labs_api.get_records(
            experiment="tasks",
            type="Task",
            model_class=TaskRecord,
            **kwargs,
        )

    def save_task(self, task_record: TaskRecord) -> TaskRecord:
        """
        Save a task record via API.

        Args:
            task_record: TaskRecord instance to save

        Returns:
            Saved TaskRecord instance
        """
        return self.labs_api.update_record(task_record.id, task_record.data)

    # Task Operation Methods

    def add_event(
        self,
        task: TaskRecord,
        event_type: str,
        actor: str,
        actor_user_id: int,
        description: str,
        **kwargs,
    ) -> TaskRecord:
        """
        Add an event to a task and save it.

        Args:
            task: TaskRecord instance
            event_type: Type of event (created, status_changed, assigned, etc.)
            actor: Name of actor
            actor_user_id: User ID of actor
            description: Event description
            **kwargs: Additional metadata

        Returns:
            Updated TaskRecord
        """
        task.add_event(event_type, actor, actor_user_id, description, **kwargs)
        return self.labs_api.update_record(task.id, task.data)

    def add_comment(self, task: TaskRecord, author_id: int, author_name: str, content: str) -> TaskRecord:
        """
        Add a comment to a task and save it.

        Args:
            task: TaskRecord instance
            author_id: Comment author user ID
            author_name: Comment author display name
            content: Comment text

        Returns:
            Updated TaskRecord
        """
        task.add_comment(author_id, author_name, content)
        return self.labs_api.update_record(task.id, task.data)

    def add_ai_session(self, task: TaskRecord, ocs_session_id: str, **kwargs) -> TaskRecord:
        """
        Add an AI session to a task and save it.

        Args:
            task: TaskRecord instance
            ocs_session_id: OCS session ID
            **kwargs: Additional session metadata

        Returns:
            Updated TaskRecord
        """
        task.add_ai_session(ocs_session_id, **kwargs)
        return self.labs_api.update_record(task.id, task.data)

    def update_status(self, task: TaskRecord, new_status: str, actor: str, actor_user_id: int) -> TaskRecord:
        """
        Update task status and add event.

        Args:
            task: TaskRecord instance
            new_status: New status value
            actor: Name of actor making the change
            actor_user_id: User ID of actor

        Returns:
            Updated TaskRecord
        """
        old_status = task.status
        task.data["status"] = new_status

        # Add event
        task.add_event(
            event_type="status_changed",
            actor=actor,
            actor_user_id=actor_user_id,
            description=f"Status changed from {old_status} to {new_status}",
        )

        return self.labs_api.update_record(task.id, task.data)

    def assign_task(self, task: TaskRecord, assigned_to_id: int | None, actor: str, actor_user_id: int) -> TaskRecord:
        """
        Assign task to a user and add event.

        Args:
            task: TaskRecord instance
            assigned_to_id: User ID to assign to (None for unassign)
            actor: Name of actor making the assignment
            actor_user_id: User ID of actor

        Returns:
            Updated TaskRecord
        """
        task.data["assigned_to_id"] = assigned_to_id

        # Add event
        if assigned_to_id:
            description = f"Assigned to user {assigned_to_id}"
        else:
            description = "Unassigned"

        task.add_event(
            event_type="assigned",
            actor=actor,
            actor_user_id=actor_user_id,
            description=description,
        )

        return self.labs_api.update_record(task.id, task.data)

    # Connect API Integration Methods

    def _call_connect_api(self, endpoint: str) -> httpx.Response:
        """Call Connect production API with OAuth token."""
        url = f"{self.production_url}{endpoint}"
        response = self.http_client.get(url)
        response.raise_for_status()
        return response

    def search_opportunities(self, query: str = "", limit: int = 100) -> list[dict]:
        """
        Search for opportunities.

        Args:
            query: Search query (name or ID)
            limit: Maximum results

        Returns:
            List of opportunity dicts (raw from API)
        """
        # Call Connect API
        response = self._call_connect_api("/export/opp_org_program_list/")
        data = response.json()

        opportunities_list = data.get("opportunities", [])
        results = []

        query_lower = query.lower().strip()
        for opp_data in opportunities_list:
            # Filter by query if provided
            if query_lower:
                opp_id_match = query_lower.isdigit() and int(query_lower) == opp_data.get("id")
                name_match = query_lower in opp_data.get("name", "").lower()
                if not (opp_id_match or name_match):
                    continue

            results.append(opp_data)

            if len(results) >= limit:
                break

        return results

    def get_opportunity_details(self, opportunity_id: int) -> dict | None:
        """
        Get detailed information about an opportunity.

        Args:
            opportunity_id: Opportunity ID

        Returns:
            Opportunity dict (raw from API) or None
        """
        # Search for this specific opportunity
        response = self._call_connect_api("/export/opp_org_program_list/")
        data = response.json()

        opportunities_list = data.get("opportunities", [])

        for opp_data in opportunities_list:
            if opp_data.get("id") == opportunity_id:
                return opp_data

        return None

    def get_users_from_opportunity(self, opportunity_id: int) -> list[dict]:
        """
        Get users for an opportunity from Connect API.

        Note: The /export/opportunity/<id>/user_data/ endpoint does NOT include user_id,
        only username. This is a limitation of the current data export API.

        Args:
            opportunity_id: Opportunity ID

        Returns:
            List of user dicts with username (no user_id available from API)
        """
        import os
        import tempfile

        import pandas as pd

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

            # Log CSV structure for debugging
            import logging

            logger = logging.getLogger(__name__)
            logger.info(f"CSV columns for opportunity {opportunity_id}: {list(df.columns)}")
            logger.info(f"CSV has {len(df)} rows")

            users = []
            for idx, row in df.iterrows():
                username = str(row["username"]) if pd.notna(row.get("username")) else None
                if username:
                    # Parse all available fields from CSV
                    user_dict = {"username": username}

                    # Add optional fields if they exist in the CSV
                    optional_fields = [
                        "name",
                        "phone_number",
                        "total_visits",
                        "approved_visits",
                        "flagged_visits",
                        "rejected_visits",
                        "last_active",
                        "email",
                    ]
                    for field in optional_fields:
                        if field in row and pd.notna(row[field]):
                            user_dict[field] = (
                                str(row[field]) if not isinstance(row[field], (int, float)) else row[field]
                            )

                    users.append(user_dict)

            return users

        finally:
            os.unlink(tmp_path)
