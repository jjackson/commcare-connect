"""
Generic views for configurable timeline UI.

These views work with any program's timeline configuration - KMC, nutrition, early childhood, etc.
The program-specific views just need to provide a config_module.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View
from django.views.generic import TemplateView

from commcare_connect.labs.configurable_ui.linking import ChildLinkingService
from commcare_connect.labs.configurable_ui.widgets import BaseWidget
from commcare_connect.opportunity.models import UserVisit, VisitValidationStatus


class GenericTimelineListView(LoginRequiredMixin, TemplateView):
    """Generic list view for children - works with any timeline config."""

    template_name = "labs/configurable_ui/child_list.html"
    config_module = None  # Override in subclass

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get opportunity from labs context
        labs_context = getattr(self.request, "labs_context", {})
        opportunity_id = labs_context.get("opportunity_id")

        if not opportunity_id:
            context["error"] = "No opportunity selected"
            return context

        # Import configuration
        linking_config = self.config_module.KMC_LINKING_CONFIG
        widgets_config = self.config_module.KMC_WIDGETS
        header_fields = self.config_module.KMC_HEADER_FIELDS

        # Get all visits
        visits = UserVisit.objects.filter(
            opportunity_id=opportunity_id, status=VisitValidationStatus.approved
        ).select_related("user")

        # Link visits into children
        linking_service = ChildLinkingService(linking_config)
        children = linking_service.link_visits(list(visits))

        # Build child list with summary data
        child_list = []
        visit_history_widget = BaseWidget(widgets_config["visit_history"])
        header_config = type("HeaderConfig", (), {"field_extractors": header_fields})()
        header_widget = BaseWidget(header_config)

        for child_id, child_visits in children.items():
            if not child_visits:
                continue

            first_visit = child_visits[0]
            last_visit = child_visits[-1]

            child_data = {
                "child_id": child_id,
                "name": header_widget.extract_field(first_visit.form_json, "child_name"),
                "visit_count": len(child_visits),
                "last_visit_date": visit_history_widget.extract_field(last_visit.form_json, "visit_date"),
                "current_weight": visit_history_widget.extract_field(last_visit.form_json, "weight"),
            }
            child_list.append(child_data)

        context["children"] = child_list
        context["opportunity_id"] = opportunity_id
        context["program_name"] = getattr(self.config_module, "PROGRAM_NAME", "Timeline")
        return context


class GenericTimelineDetailView(LoginRequiredMixin, TemplateView):
    """Generic detail view for a single child's timeline."""

    template_name = "labs/configurable_ui/timeline.html"
    api_url_name = None  # Override in subclass (e.g., "kmc:api_child_data")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        child_id = self.kwargs["child_id"]
        context["child_id"] = child_id

        # Build API URL
        from django.urls import reverse

        context["api_url"] = reverse(self.api_url_name, kwargs={"child_id": child_id})
        return context


class GenericTimelineDataView(LoginRequiredMixin, View):
    """Generic API endpoint for child timeline data - works with any config."""

    config_module = None  # Override in subclass

    def get(self, request, child_id):
        # Get opportunity from labs context
        labs_context = getattr(request, "labs_context", {})
        opportunity_id = labs_context.get("opportunity_id")

        if not opportunity_id:
            return JsonResponse({"error": "No opportunity selected"}, status=400)

        # Import configuration
        linking_config = self.config_module.KMC_LINKING_CONFIG
        widgets_config = self.config_module.KMC_WIDGETS
        layout_config = self.config_module.KMC_LAYOUT
        header_fields = self.config_module.KMC_HEADER_FIELDS

        # Get all visits for this opportunity
        visits = UserVisit.objects.filter(
            opportunity_id=opportunity_id, status=VisitValidationStatus.approved
        ).select_related("user")

        # Link and filter to this child
        linking_service = ChildLinkingService(linking_config)
        children = linking_service.link_visits(list(visits))

        child_visits = children.get(child_id, [])
        if not child_visits:
            return JsonResponse({"error": "Child not found"}, status=404)

        # Extract data using widgets
        timeline_data = self._build_timeline_data(child_id, child_visits, widgets_config, layout_config, header_fields)

        return JsonResponse(timeline_data)

    def _build_timeline_data(self, child_id, visits, widgets_config, layout_config, header_fields):
        """Build complete timeline data using composable widgets."""
        # Header data from first visit
        header_config = type("HeaderConfig", (), {"field_extractors": header_fields})()
        header_widget = BaseWidget(header_config)
        first_visit = visits[0]

        header = {}
        for field_name in header_fields.keys():
            header[field_name] = header_widget.extract_field(first_visit.form_json, field_name)

        # Create widget instances
        widgets = {widget_id: BaseWidget(config) for widget_id, config in widgets_config.items()}

        # Extract data for each visit using all widgets
        visit_data = []
        for visit in visits:
            visit_info = {
                "visit_id": visit.id,
                "widgets": {},  # Data organized by widget_id
            }

            # Extract data for each widget
            for widget_id, widget in widgets.items():
                widget_data = widget.extract_all_fields(visit.form_json)

                # Special handling for photo URLs
                if widget_id == "visit_history" and "photo_url" in widget_data:
                    photo_filename = widget_data["photo_url"]
                    if photo_filename and visit.form_json.get("attachments"):
                        attachments = visit.form_json["attachments"]
                        if photo_filename in attachments:
                            widget_data["photo_url"] = attachments[photo_filename].get("url")

                visit_info["widgets"][widget_id] = widget_data

            visit_data.append(visit_info)

        # Serialize widget configs for frontend
        widget_configs_serialized = {}
        for widget_id, config in widgets_config.items():
            widget_configs_serialized[widget_id] = {
                "widget_type": config.widget_type,
                "title": config.title,
                "options": config.options,
                "field_labels": {
                    field_name: extractor.display_name for field_name, extractor in config.field_extractors.items()
                },
            }

        return {
            "child_id": child_id,
            "header": header,
            "visits": visit_data,
            "layout": {
                "left": layout_config.left_widgets,
                "center": layout_config.center_widgets,
                "right": layout_config.right_widgets,
            },
            "widget_configs": widget_configs_serialized,
        }
