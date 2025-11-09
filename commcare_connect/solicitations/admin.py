from django.contrib import admin

from commcare_connect.labs.models import ExperimentRecord


@admin.register(ExperimentRecord)
class ExperimentRecordAdmin(admin.ModelAdmin):
    """
    Admin interface for ExperimentRecord.
    Solicitations data is now stored as ExperimentRecord with JSON data.
    """

    list_display = ["id", "experiment", "type", "program_id", "organization_id", "user_id", "date_created"]
    list_filter = ["experiment", "type", "date_created"]
    search_fields = ["data", "experiment", "type"]
    readonly_fields = ["date_created", "date_modified"]

    fieldsets = (
        ("Record Info", {"fields": ("experiment", "type")}),
        ("References", {"fields": ("user_id", "opportunity_id", "organization_id", "program_id", "parent")}),
        ("Data", {"fields": ("data",)}),
        ("Metadata", {"fields": ("date_created", "date_modified"), "classes": ("collapse",)}),
    )
