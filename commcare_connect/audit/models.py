from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class AuditDefinition(models.Model):
    """
    Defines an audit scope and configuration.

    This is a first-class object that captures all parameters needed to create
    an audit session. It is created during the preview step and used during
    the creation step, ensuring consistency between preview and actual creation.

    It can be exported/imported to allow rerunning audits with the same parameters.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        READY = "ready", _("Ready")  # Preview completed, ready for creation
        USED = "used", _("Used")  # Sessions created from this definition
        EXPIRED = "expired", _("Expired")  # Sampled data expired (cache cleared)

    # Metadata
    name = models.CharField(max_length=255, blank=True, help_text="Optional name for this audit definition")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_definitions",
        help_text="User who created this definition",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    # Audit Configuration
    opportunity_ids = models.JSONField(help_text="List of opportunity IDs to audit")
    audit_type = models.CharField(
        max_length=50, help_text="Type: date_range, last_n_per_flw, last_n_per_opp, last_n_across_all"
    )
    granularity = models.CharField(max_length=50, help_text="Granularity: combined, per_opp, per_flw")

    # Criteria (optional based on audit_type)
    start_date = models.DateField(null=True, blank=True, help_text="For date_range type")
    end_date = models.DateField(null=True, blank=True, help_text="For date_range type")
    count_per_flw = models.IntegerField(null=True, blank=True, help_text="For last_n_per_flw type")
    count_per_opp = models.IntegerField(null=True, blank=True, help_text="For last_n_per_opp type")
    count_across_all = models.IntegerField(null=True, blank=True, help_text="For last_n_across_all type")

    # Sampling
    sample_percentage = models.IntegerField(default=100, help_text="Percentage of visits to sample (1-100)")
    sampled_visit_ids = models.JSONField(
        null=True, blank=True, help_text="List of sampled visit IDs (if sampling enabled)"
    )
    sample_cache_key = models.CharField(
        max_length=255, blank=True, help_text="Cache key for sampled visit IDs (temporary)"
    )

    # Preview Results (calculated during preview step)
    preview_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Preview statistics: FLW counts, visit counts, date ranges per opportunity/granularity",
    )

    # Creation tracking
    sessions_created = models.IntegerField(
        default=0, help_text="Number of audit sessions created from this definition"
    )
    used_at = models.DateTimeField(null=True, blank=True, help_text="When sessions were created")
    used_by = models.CharField(max_length=150, blank=True, help_text="Username who executed the creation")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["created_by", "status"]),
        ]

    def __str__(self):
        name = self.name or f"Audit {self.id}"
        return f"{name} ({self.audit_type}, {len(self.opportunity_ids)} opps)"

    def to_dict(self) -> dict:
        """Export as dictionary for JSON serialization"""
        return {
            "id": self.id,
            "name": self.name,
            "created_by": self.created_by.username if self.created_by else None,
            "created_at": self.created_at.isoformat(),
            "status": self.status,
            "opportunity_ids": self.opportunity_ids,
            "audit_type": self.audit_type,
            "granularity": self.granularity,
            "start_date": str(self.start_date) if self.start_date else None,
            "end_date": str(self.end_date) if self.end_date else None,
            "count_per_flw": self.count_per_flw,
            "count_per_opp": self.count_per_opp,
            "count_across_all": self.count_across_all,
            "sample_percentage": self.sample_percentage,
            "sampled_visit_ids": self.sampled_visit_ids,  # Include sampled IDs
            "sample_cache_key": self.sample_cache_key,  # Include cache key
            "preview_data": self.preview_data,
            "sessions_created": self.sessions_created,
            "used_at": self.used_at.isoformat() if self.used_at else None,
            "used_by": self.used_by,
        }

    @classmethod
    def from_dict(cls, data: dict, user=None):
        """Import from dictionary (for import functionality)"""
        from datetime import date

        definition = cls(
            name=data.get("name", ""),
            created_by=user,
            opportunity_ids=data["opportunity_ids"],
            audit_type=data["audit_type"],
            granularity=data["granularity"],
            start_date=date.fromisoformat(data["start_date"]) if data.get("start_date") else None,
            end_date=date.fromisoformat(data["end_date"]) if data.get("end_date") else None,
            count_per_flw=data.get("count_per_flw"),
            count_per_opp=data.get("count_per_opp"),
            count_across_all=data.get("count_across_all"),
            sample_percentage=data.get("sample_percentage", 100),
            sampled_visit_ids=data.get("sampled_visit_ids"),  # Import sampled IDs
            sample_cache_key=data.get("sample_cache_key", ""),  # Import cache key
            preview_data=data.get("preview_data"),  # Import preview data
            status=cls.Status.READY if data.get("preview_data") else cls.Status.DRAFT,  # Ready if has preview
        )
        return definition

    def to_criteria_dict(self) -> dict:
        """
        Convert to the criteria dictionary format used by audit services.
        This ensures backward compatibility with existing service APIs.
        """
        criteria = {
            "type": self.audit_type,
            "granularity": self.granularity,
            "samplePercentage": self.sample_percentage,
        }

        if self.audit_type == "last_n_per_flw" and self.count_per_flw:
            criteria["countPerFlw"] = self.count_per_flw
        elif self.audit_type == "last_n_per_opp" and self.count_per_opp:
            criteria["countPerOpp"] = self.count_per_opp
        elif self.audit_type == "last_n_across_all" and self.count_across_all:
            criteria["countAcrossAll"] = self.count_across_all
        elif self.audit_type == "date_range":
            if self.start_date:
                criteria["startDate"] = str(self.start_date)
            if self.end_date:
                criteria["endDate"] = str(self.end_date)

        # Add cache key if present (for using cached sample)
        if self.sample_cache_key:
            criteria["sampleCacheKey"] = self.sample_cache_key

        return criteria

    def mark_used(self, sessions_created: int, username: str):
        """Mark this definition as used after creating sessions"""
        self.status = self.Status.USED
        self.sessions_created = sessions_created
        self.used_at = timezone.now()
        self.used_by = username
        self.save(update_fields=["status", "sessions_created", "used_at", "used_by", "updated_at"])

    def mark_ready(self):
        """Mark as ready after successful preview"""
        self.status = self.Status.READY
        self.save(update_fields=["status", "updated_at"])

    def get_summary(self) -> dict:
        """Get a human-readable summary of this audit definition"""
        summary = {
            "opportunities": len(self.opportunity_ids),
            "audit_type": self.audit_type,
            "granularity": self.granularity,
        }

        if self.audit_type == "date_range":
            summary["date_range"] = f"{self.start_date} to {self.end_date}"
        elif self.audit_type == "last_n_per_flw":
            summary["visits_per_flw"] = self.count_per_flw
        elif self.audit_type == "last_n_per_opp":
            summary["visits_per_opp"] = self.count_per_opp
        elif self.audit_type == "last_n_across_all":
            summary["total_visits"] = self.count_across_all

        if self.sample_percentage < 100:
            summary["sampling"] = f"{self.sample_percentage}%"

        if self.preview_data:
            # Aggregate preview statistics
            total_flws = sum(p.get("total_flws", 0) for p in self.preview_data)
            total_visits = sum(p.get("total_visits", 0) for p in self.preview_data)
            sessions = sum(p.get("sessions_to_create", 0) for p in self.preview_data)

            summary["preview"] = {"flws": total_flws, "visits": total_visits, "sessions": sessions}

        return summary


class AuditSession(models.Model):
    """Represents an audit session for a specific FLW and date range"""

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", _("In Progress")
        COMPLETED = "completed", _("Completed")

    class OverallResult(models.TextChoices):
        PASS = "pass", _("Pass")
        FAIL = "fail", _("Fail")

    # Link to audit definition (optional - for tracking provenance)
    audit_definition = models.ForeignKey(
        AuditDefinition,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_sessions",
        help_text="The audit definition used to create this session",
    )

    # Auditor info
    auditor_username = models.CharField(max_length=150, help_text="Username of person conducting the audit")

    # Audit categorization
    title = models.CharField(max_length=255, blank=True, help_text="Audit title (e.g., 'Week of Jan 1-7, 2024')")
    tag = models.CharField(
        max_length=100,
        blank=True,
        help_text="Tag for categorizing audits (e.g., 'first_10', 'quarterly_review')",
    )

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
