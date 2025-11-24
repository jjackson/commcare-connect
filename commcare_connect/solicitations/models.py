"""
Proxy models for LocalLabsRecord.

These proxy models provide convenient access to LocalLabsRecord data
for solicitations. LocalLabsRecord is a transient Python object
that deserializes production API responses - no database storage.
"""

from datetime import datetime

from commcare_connect.labs.models import LocalLabsRecord


class SolicitationRecord(LocalLabsRecord):
    """Proxy model for Solicitation-type LocalLabsRecords."""

    # Properties for convenient access
    @property
    def title(self):
        return self.data.get("title", "")

    @property
    def description(self):
        return self.data.get("description", "")

    @property
    def scope_of_work(self):
        return self.data.get("scope_of_work", "")

    @property
    def solicitation_type(self):
        return self.data.get("solicitation_type", "")

    @property
    def status(self):
        return self.data.get("status", "")

    @property
    def is_publicly_listed(self):
        return self.data.get("is_publicly_listed", True)

    @property
    def questions(self):
        return self.data.get("questions", [])

    @property
    def program_name(self):
        """Return program name from JSON data."""
        return self.data.get("program_name", "")

    @property
    def application_deadline(self):
        """Return application deadline as a date object."""
        date_str = self.data.get("application_deadline")
        if date_str:
            try:
                return datetime.strptime(date_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                return None
        return None

    @property
    def expected_start_date(self):
        """Return expected start date as a date object."""
        date_str = self.data.get("expected_start_date")
        if date_str:
            try:
                return datetime.strptime(date_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                return None
        return None

    @property
    def expected_end_date(self):
        """Return expected end date as a date object."""
        date_str = self.data.get("expected_end_date")
        if date_str:
            try:
                return datetime.strptime(date_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                return None
        return None

    @property
    def estimated_scale(self):
        return self.data.get("estimated_scale", "")

    @property
    def contact_email(self):
        """Return contact email."""
        return self.data.get("contact_email", "")

    # Helper methods
    def can_accept_responses(self):
        """Check if this solicitation can accept responses."""
        return self.status == "active"

    def get_solicitation_type_display(self):
        """Get display text for solicitation type."""
        type_map = {"eoi": "Expression of Interest", "rfp": "Request for Proposal"}
        return type_map.get(self.solicitation_type, self.solicitation_type)


class ResponseRecord(LocalLabsRecord):
    """Proxy model for SolicitationResponse-type LocalLabsRecords."""

    @property
    def responses(self):
        return self.data.get("responses", {})

    @property
    def response_status(self):
        return self.data.get("status", "draft")

    @property
    def submission_date(self):
        # date_created doesn't exist on LocalLabsRecord - store in data if needed
        return self.data.get("submission_date")

    @property
    def attachments(self):
        return self.data.get("attachments", [])

    @property
    def submitted_by_name(self):
        """Return user name for display."""
        submitted_by = self.data.get("submitted_by", {})
        full_name = submitted_by.get("full_name", "").strip()
        if full_name:
            return full_name
        username = submitted_by.get("username")
        if username:
            return username
        return f"User {self.user_id}" if self.user_id is not None else "Unknown User"

    @property
    def submitted_by_email(self):
        """Return user email for display."""
        submitted_by = self.data.get("submitted_by", {})
        return submitted_by.get("email", "")

    @property
    def organization_name(self):
        """Return organization name for display."""
        # For labs, we only have slug. Could look up in OAuth data if needed.
        return self.organization_id if self.organization_id else "Unknown Organization"

    # Helper methods
    def is_draft(self):
        """Check if this response is still a draft."""
        return self.response_status == "draft"

    def is_submitted(self):
        """Check if this response has been submitted."""
        return self.response_status == "submitted"


class ReviewRecord(LocalLabsRecord):
    """Proxy model for SolicitationReview-type LocalLabsRecords."""

    @property
    def score(self):
        return self.data.get("score")

    @property
    def tags(self):
        return self.data.get("tags", "")

    @property
    def notes(self):
        return self.data.get("notes", "")

    @property
    def recommendation(self):
        return self.data.get("recommendation")

    @property
    def review_date(self):
        # date_created doesn't exist on LocalLabsRecord - store in data if needed
        return self.data.get("review_date")

    def get_recommendation_display(self):
        """Get display text for recommendation."""
        rec_map = {
            "recommended": "Recommended",
            "not_recommended": "Not Recommended",
            "neutral": "Neutral",
        }
        return rec_map.get(self.recommendation, self.recommendation)
