from django.contrib import admin
from django.utils.html import format_html

from commcare_connect.audit.models import AuditImageNote, AuditResult, AuditSession


@admin.register(AuditSession)
class AuditSessionAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "flw_username",
        "opportunity_name",
        "domain",
        "date_range",
        "status",
        "overall_result",
        "progress",
        "created_at",
    ]
    list_filter = ["status", "overall_result", "domain", "created_at"]
    search_fields = ["flw_username", "auditor_username", "opportunity_name", "domain"]
    readonly_fields = ["created_at", "progress"]

    fieldsets = (
        (None, {"fields": ("auditor_username", "flw_username", "opportunity_name", "domain", "app_id")}),
        ("Audit Period", {"fields": ("start_date", "end_date")}),
        ("Results", {"fields": ("status", "overall_result", "notes", "kpi_notes")}),
        ("Timestamps", {"fields": ("created_at", "completed_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="Date Range")
    def date_range(self, obj):
        return f"{obj.start_date} to {obj.end_date}"

    @admin.display(description="Progress")
    def progress(self, obj):
        percentage = obj.progress_percentage
        total_visits = obj.visits.count()
        audited_visits = obj.results.count()

        if percentage == 100:
            color = "green"
        elif percentage > 50:
            color = "orange"
        else:
            color = "red"

        return format_html(
            '<span style="color: {};">{:.1f}% ({}/{})</span>', color, percentage, audited_visits, total_visits
        )


# AuditVisit removed - using UserVisit directly for full production compatibility


# AuditVisitImage removed - using BlobMeta instead for consistency with production


@admin.register(AuditResult)
class AuditResultAdmin(admin.ModelAdmin):
    list_display = ["id", "audit_session", "user_visit", "visit_date", "result", "has_notes", "audited_at"]
    list_filter = ["result", "audit_session__status", "audit_session__domain", "audited_at"]
    search_fields = ["audit_session__flw_username", "user_visit__xform_id", "notes"]
    readonly_fields = ["audited_at"]

    @admin.display(description="Visit Date")
    def visit_date(self, obj):
        return obj.user_visit.visit_date.strftime("%Y-%m-%d %H:%M")

    @admin.display(
        description="Has Notes",
        boolean=True,
    )
    def has_notes(self, obj):
        return bool(obj.notes)


@admin.register(AuditImageNote)
class AuditImageNoteAdmin(admin.ModelAdmin):
    list_display = ["audit_result", "blob_id", "note_preview", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["blob_id", "note", "audit_result__user_visit__xform_id"]
    readonly_fields = ["created_at"]

    @admin.display(description="Note Preview")
    def note_preview(self, obj):
        return obj.note[:50] + "..." if len(obj.note) > 50 else obj.note
