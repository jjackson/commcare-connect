from django.db import models
from django.utils.translation import gettext_lazy as _


class AuditSession(models.Model):
    """Represents an audit session for a specific FLW and date range"""

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", _("In Progress")
        COMPLETED = "completed", _("Completed")

    class OverallResult(models.TextChoices):
        PASS = "pass", _("Pass")
        FAIL = "fail", _("Fail")

    # Auditor info
    auditor_username = models.CharField(max_length=150, help_text="Username of person conducting the audit")

    # The exact visits included in this audit session
    visits = models.ManyToManyField(
        "opportunity.UserVisit",
        related_name="audit_sessions",
        help_text="Explicit list of visits included in this audit",
    )

    # Metadata fields (for display/filtering only - NOT used to query visits)
    flw_username = models.CharField(max_length=150, blank=True, help_text="FLW username (metadata only)")
    opportunity_name = models.CharField(max_length=255, help_text="Name of opportunity/program being audited")
    domain = models.CharField(max_length=255, help_text="CommCare domain/project space")
    app_id = models.CharField(max_length=50, help_text="CommCare application ID")
    opportunity_ids = models.JSONField(default=list, blank=True, help_text="List of opportunity IDs (metadata only)")
    user_ids = models.JSONField(default=list, blank=True, help_text="List of user IDs/FLWs (metadata only)")

    # Date range metadata (calculated from actual visits, for display only)
    start_date = models.DateField(help_text="Start date of audit period (metadata only)")
    end_date = models.DateField(help_text="End date of audit period (metadata only)")

    # Audit status and results
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_PROGRESS)
    overall_result = models.CharField(
        max_length=10,
        choices=OverallResult.choices,
        null=True,
        blank=True,
        help_text="Overall audit result for this FLW/period",
    )
    notes = models.TextField(blank=True, help_text="General notes about the audit session")
    kpi_notes = models.TextField(blank=True, help_text="KPI-related notes or reasons for failure")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["auditor_username", "status"]),
            models.Index(fields=["flw_username", "domain"]),
            models.Index(fields=["start_date", "end_date"]),
        ]

    def __str__(self):
        return f"Audit: {self.flw_username} ({self.start_date} - {self.end_date})"

    @property
    def progress_percentage(self):
        """Calculate audit progress as percentage"""
        # Total visits is the explicit set of visits assigned to this session
        total_visits = self.visits.count()

        if total_visits == 0:
            return 0

        # Audited visits are those with results
        audited_visits = self.results.count()
        return round((audited_visits / total_visits) * 100, 1)


# AuditVisit removed - using UserVisit directly for full production compatibility


class AuditResult(models.Model):
    """Individual visit audit results"""

    class Result(models.TextChoices):
        PASS = "pass", _("Pass")
        FAIL = "fail", _("Fail")

    audit_session = models.ForeignKey(AuditSession, on_delete=models.CASCADE, related_name="results")
    user_visit = models.ForeignKey(
        "opportunity.UserVisit", on_delete=models.CASCADE, help_text="The UserVisit being audited"
    )
    result = models.CharField(max_length=10, choices=Result.choices, help_text="Pass or fail for this visit")
    notes = models.TextField(blank=True, help_text="Optional notes about why this visit failed")
    audited_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["audit_session", "user_visit"]
        ordering = ["user_visit__visit_date"]
        indexes = [
            models.Index(fields=["audit_session", "result"]),
        ]

    def __str__(self):
        return f"{self.user_visit} - {self.result}"


class AuditImageNote(models.Model):
    """Notes for specific images within an audit result"""

    audit_result = models.ForeignKey(AuditResult, on_delete=models.CASCADE, related_name="image_notes")
    blob_id = models.CharField(max_length=255, help_text="The blob ID of the image this note refers to")
    note = models.TextField(help_text="Note about this specific image")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["audit_result", "blob_id"]
        ordering = ["created_at"]

    def __str__(self):
        return f"Image note for {self.blob_id} in {self.audit_result}"
