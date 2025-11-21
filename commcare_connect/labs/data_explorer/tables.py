"""
Django Tables2 table definitions for Labs Data Explorer
"""

import django_tables2 as tables
from django.urls import reverse
from django.utils.html import format_html

from commcare_connect.labs.data_explorer.utils import truncate_json_preview


class LabsRecordTable(tables.Table):
    """Table for displaying LabsRecord data."""

    # Checkbox column for bulk selection
    select = tables.CheckBoxColumn(
        accessor="id",
        attrs={
            "th__input": {
                "@click": "toggleSelectAll()",
                "x-model": "selectAll",
                "name": "select_all",
                "type": "checkbox",
                "class": "checkbox",
            },
            "td__input": {
                "x-model": "selected",
                "name": "record_select",
                "type": "checkbox",
                "class": "checkbox",
            },
        },
        orderable=False,
    )

    id = tables.Column(verbose_name="ID")
    experiment = tables.Column(verbose_name="Experiment")
    type = tables.Column(verbose_name="Type")
    username = tables.Column(verbose_name="Username", empty_values=())
    data_preview = tables.Column(
        verbose_name="Data Preview",
        accessor="data",
        orderable=False,
        empty_values=(),
    )
    date_created = tables.Column(verbose_name="Created")
    date_modified = tables.Column(verbose_name="Modified", empty_values=())

    actions = tables.Column(
        verbose_name="Actions",
        empty_values=(),
        orderable=False,
    )

    class Meta:
        attrs = {
            "class": "table table-striped",
            "x-data": "{selected: [], selectAll: false}",
            "@change": "updateSelectAll()",
        }
        sequence = (
            "select",
            "id",
            "experiment",
            "type",
            "username",
            "data_preview",
            "date_created",
            "date_modified",
            "actions",
        )
        empty_text = "No records found."
        orderable = False

    def render_username(self, value, record):
        """Render username field."""
        return value if value else "—"

    def render_data_preview(self, value):
        """Render truncated JSON preview."""
        preview = truncate_json_preview(value, max_length=80)
        return format_html('<code class="text-sm">{}</code>', preview)

    def render_date_created(self, value):
        """Render created date."""
        if not value:
            return "—"
        # Value is ISO string from API, format for display
        try:
            from datetime import datetime

            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return value

    def render_date_modified(self, value):
        """Render modified date."""
        if not value:
            return "—"
        try:
            from datetime import datetime

            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return value

    def render_actions(self, record):
        """Render action buttons."""
        edit_url = reverse("data-explorer:edit", kwargs={"record_id": record.id})
        return format_html('<a href="{}" class="btn btn-sm btn-primary">Edit</a>', edit_url)
