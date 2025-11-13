"""
Proxy models for Task LocalLabsRecords.

These proxy models provide convenient access to LocalLabsRecord data
for the tasks workflow. LocalLabsRecord is a transient Python object
that deserializes production API responses - no database storage.
"""

from datetime import datetime

from commcare_connect.labs.models import LocalLabsRecord


class TaskRecord(LocalLabsRecord):
    """Proxy model for Task-type LocalLabsRecords."""

    # Properties for convenient access to task data
    # Note: username and opportunity_id are fields on LocalLabsRecord parent
    # LocalLabsRecord is a transient object from API responses, not a database model

    @property
    def task_username(self):
        """Username of the FLW this task is about (stored in data, not parent username field)."""
        return self.data.get("username")

    @property
    def task_type(self):
        """Type of task: warning, deactivation."""
        return self.data.get("task_type", "warning")

    @property
    def status(self):
        """Current status: unassigned, network_manager, program_manager, action_underway, resolved, closed."""
        return self.data.get("status", "unassigned")

    @property
    def priority(self):
        """Priority: low, medium, high."""
        return self.data.get("priority", "medium")

    @property
    def title(self):
        """Task title."""
        return self.data.get("title", "")

    @property
    def description(self):
        """Task description."""
        return self.data.get("description", "")

    @property
    def learning_assignment_text(self):
        """Text description of learning modules or training assigned."""
        return self.data.get("learning_assignment_text", "")

    @property
    def audit_session_id(self):
        """Reference to audit session that triggered this task (optional)."""
        return self.data.get("audit_session_id")

    @property
    def assigned_to_id(self):
        """ID of user currently assigned to handle this task."""
        return self.data.get("assigned_to_id")

    @property
    def created_by_id(self):
        """ID of user who created this task."""
        return self.data.get("created_by_id")

    @property
    def events(self):
        """List of timeline events."""
        return self.data.get("events", [])

    @property
    def comments(self):
        """List of user comments."""
        return self.data.get("comments", [])

    @property
    def ai_sessions(self):
        """List of AI assistant sessions."""
        return self.data.get("ai_sessions", [])

    # Helper methods for managing nested data
    def add_event(self, event_type, actor, actor_user_id, description, **kwargs):
        """
        Add an event to the task timeline.

        Args:
            event_type: Type of event (created, status_changed, assigned, etc.)
            actor: Name of person/system performing the action
            actor_user_id: User ID of actor (if applicable)
            description: Human-readable description of the event
            **kwargs: Additional metadata (ai_session_id, etc.)

        Returns:
            Updated task record (not saved to DB)
        """
        if "events" not in self.data:
            self.data["events"] = []

        event = {
            "event_type": event_type,
            "actor": actor,
            "actor_user_id": actor_user_id,
            "description": description,
            "timestamp": datetime.now().isoformat(),
            "metadata": kwargs.get("metadata", {}),
            "ai_session_id": kwargs.get("ai_session_id"),
        }

        self.data["events"].append(event)
        return self

    def add_comment(self, author_id, author_name, content):
        """
        Add a comment to the task.

        Args:
            author_id: User ID of comment author
            author_name: Display name of author
            content: Comment text

        Returns:
            Updated task record (not saved to DB)
        """
        if "comments" not in self.data:
            self.data["comments"] = []

        comment = {
            "author_id": author_id,
            "author_name": author_name,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }

        self.data["comments"].append(comment)
        return self

    def add_ai_session(self, ocs_session_id, **kwargs):
        """
        Add an AI assistant session to the task.

        Args:
            ocs_session_id: Session ID from OCS API
            **kwargs: Additional session metadata (status, parameters, etc.)

        Returns:
            Updated task record (not saved to DB)
        """
        if "ai_sessions" not in self.data:
            self.data["ai_sessions"] = []

        session = {
            "session_id": kwargs.get("session_id"),
            "ocs_session_id": ocs_session_id,
            "status": kwargs.get("status", "initiated"),
            "timestamp": datetime.now().isoformat(),
            "metadata": kwargs.get("metadata", {}),
        }

        self.data["ai_sessions"].append(session)
        return self

    def get_timeline(self):
        """
        Get combined timeline of events and comments, sorted by timestamp.

        Returns:
            List of timeline items sorted by timestamp (newest first)
        """
        timeline = []

        # Add events
        for event in self.events:
            timeline.append(
                {
                    "type": "event",
                    "timestamp": event.get("timestamp"),
                    "event_type": event.get("event_type"),
                    "actor": event.get("actor"),
                    "actor_user_id": event.get("actor_user_id"),
                    "description": event.get("description"),
                    "metadata": event.get("metadata", {}),
                    "ai_session_id": event.get("ai_session_id"),
                }
            )

        # Add comments
        for comment in self.comments:
            timeline.append(
                {
                    "type": "comment",
                    "timestamp": comment.get("timestamp"),
                    "author_id": comment.get("author_id"),
                    "author_name": comment.get("author_name"),
                    "content": comment.get("content"),
                }
            )

        # Sort by timestamp (newest first)
        timeline.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        return timeline

    def get_status_display(self):
        """Get human-readable status label."""
        status_labels = {
            "unassigned": "Unassigned",
            "network_manager": "Network Manager",
            "program_manager": "Program Manager",
            "action_underway": "Action Underway",
            "resolved": "Resolved",
            "closed": "Closed",
        }
        return status_labels.get(self.status, self.status.title())

    def get_task_type_display(self):
        """Get human-readable task type label."""
        type_labels = {
            "warning": "Warning",
            "deactivation": "Deactivation",
        }
        return type_labels.get(self.task_type, self.task_type.title())

    def get_priority_display(self):
        """Get human-readable priority label."""
        priority_labels = {
            "low": "Low",
            "medium": "Medium",
            "high": "High",
        }
        return priority_labels.get(self.priority, self.priority.title())
