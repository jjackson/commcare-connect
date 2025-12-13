import django_tables2 as tables
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe


class KMCChildTable(tables.Table):
    """Table for displaying KMC children with their visit data."""

    child_name = tables.Column(
        verbose_name="Child Name",
        orderable=True,
    )

    flw_display_name = tables.Column(
        verbose_name="FLW Name",
        orderable=True,
    )

    visit_count = tables.Column(
        verbose_name="Visits",
        orderable=True,
    )

    starting_weight = tables.Column(
        verbose_name="Starting Weight",
        orderable=True,
    )

    current_weight = tables.Column(
        verbose_name="Current Weight",
        orderable=True,
    )

    last_visit_date = tables.Column(
        verbose_name="Last Visit",
        orderable=True,
    )

    actions = tables.Column(
        verbose_name="Actions",
        orderable=False,
        empty_values=(),
    )

    def render_child_name(self, value, record):
        """Render child name with entity_id below in parentheses."""
        entity_id = record.get("entity_id") or record.get("child_id", "")
        return format_html(
            '<div class="font-medium text-gray-900">{}</div>' '<div class="text-xs text-gray-500">({})</div>',
            value or "Unknown",
            entity_id,
        )

    def render_flw_display_name(self, value, record):
        """Render FLW name with fallback to username."""
        return value or record.get("flw_username") or "-"

    def render_starting_weight(self, value):
        """Render starting weight with unit."""
        if value:
            return format_html("{}g", value)
        return mark_safe('<span class="text-gray-400">-</span>')

    def render_current_weight(self, value):
        """Render current weight with unit."""
        if value:
            return format_html("{}g", value)
        return mark_safe('<span class="text-gray-400">-</span>')

    def render_last_visit_date(self, value):
        """Render last visit date (date only)."""
        if value:
            # Extract date part if it's an ISO string
            if "T" in str(value):
                return str(value).split("T")[0]
            return value
        return "-"

    def render_actions(self, record):
        """Render action buttons."""
        child_id = record.get("child_id") or record.get("entity_id", "")
        timeline_url = reverse("kmc:child_timeline", kwargs={"child_id": child_id})
        inspector_query = f"entity_id = '{child_id}'"

        return format_html(
            '<div class="flex gap-2">'
            '<a href="{}" class="inline-flex items-center px-3 py-1 border border-blue-300 '
            "rounded-md text-xs font-medium text-blue-700 bg-blue-50 hover:bg-blue-100 "
            'hover:border-blue-400 transition-colors">'
            '<i class="fa-solid fa-timeline mr-1"></i> View Timeline'
            "</a>"
            '<a href="/labs/explorer/visit-inspector/?query={}" '
            'class="inline-flex items-center px-3 py-1 border border-purple-300 '
            "rounded-md text-xs font-medium text-purple-700 bg-purple-50 "
            'hover:bg-purple-100 hover:border-purple-400 transition-colors">'
            '<i class="fa-solid fa-search mr-1"></i> View in Inspector'
            "</a>"
            "</div>",
            timeline_url,
            inspector_query,
        )

    class Meta:
        template_name = "base_table.html"
        fields = (
            "child_name",
            "flw_display_name",
            "visit_count",
            "starting_weight",
            "current_weight",
            "last_visit_date",
            "actions",
        )
        sequence = fields
        order_by = ("-visit_count",)  # Default sort by visit count descending
