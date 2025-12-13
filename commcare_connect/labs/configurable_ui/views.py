"""
Generic views for configurable timeline UI.

These views work with any program's timeline configuration - KMC, nutrition, early childhood, etc.
The program-specific views just need to provide a config_module.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View
from django.views.generic import TemplateView


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

        # Add opportunity_id for image URLs
        labs_context = getattr(self.request, "labs_context", {})
        context["opportunity_id"] = labs_context.get("opportunity_id") or self.request.GET.get("opportunity_id")

        return context


class GenericTimelineDataView(LoginRequiredMixin, View):
    """Generic API endpoint for child timeline data - works with any config."""

    config_module = None  # Override in subclass
    pipeline_config = None  # Override in subclass - the AnalysisPipelineConfig

    def get(self, request, child_id):
        import logging
        from copy import deepcopy

        from commcare_connect.labs.analysis.pipeline import AnalysisPipeline

        logger = logging.getLogger(__name__)

        # Get opportunity from labs context or query params
        labs_context = getattr(request, "labs_context", {})
        opportunity_id = labs_context.get("opportunity_id") or request.GET.get("opportunity_id")

        logger.info(f"[Timeline API] child_id={child_id}, opportunity_id={opportunity_id}")

        if not opportunity_id:
            return JsonResponse({"error": "No opportunity selected"}, status=400)

        # Import configuration
        widgets_config = self.config_module.KMC_WIDGETS
        layout_config = self.config_module.KMC_LAYOUT
        header_fields = self.config_module.KMC_HEADER_FIELDS

        # Use pipeline with entity_id filter - this is SQL-optimized now
        pipeline = AnalysisPipeline(request)

        # Create filtered config for this specific child
        filtered_config = deepcopy(self.pipeline_config)
        filtered_config.filters = {"entity_id": child_id}

        logger.info(f"[Timeline API] Running pipeline with entity_id filter: {child_id}")
        result = pipeline.run_analysis(filtered_config, opportunity_id=opportunity_id)

        if not result or not result.rows:
            logger.warning(f"[Timeline API] No visits found for entity_id={child_id}")
            return JsonResponse({"error": f"No visits found for child {child_id}"}, status=404)

        logger.info(f"[Timeline API] Pipeline returned {len(result.rows)} visits for child {child_id}")

        # Sort by time_end (form submission end time) for consistent chronological order
        # Fall back to visit_date if time_end is not available
        def get_sort_key(row):
            time_end = row.computed.get("time_end")
            if time_end:
                return time_end
            return row.visit_date.isoformat() if row.visit_date else ""

        child_rows = sorted(result.rows, key=get_sort_key)

        # Build timeline data from computed fields ONLY
        timeline_data = self._build_timeline_data(child_id, child_rows, widgets_config, layout_config, header_fields)

        return JsonResponse(timeline_data)

    def _build_timeline_data(self, child_id, visit_rows, widgets_config, layout_config, header_fields):
        """Build complete timeline data using ONLY pipeline computed fields."""
        import logging

        logger = logging.getLogger(__name__)

        # Extract first visit for header
        first_row = visit_rows[0]

        # Header data from computed fields
        header = {}
        for field_name in header_fields.keys():
            # All header fields should be in computed
            header[field_name] = first_row.computed.get(field_name)

        logger.info(f"[Timeline API] Header data: {header}")

        # Extract data for each visit from computed fields (including images)
        visit_data = []
        for row in visit_rows:
            visit_info = {
                "visit_id": row.id,
                "visit_date": row.visit_date.isoformat() if row.visit_date else None,  # Raw datetime for formatting
                "widgets": {},  # Data organized by widget_id
                "images": row.computed.get("images_with_questions", []),  # Pre-computed by pipeline
            }

            # Extract data for each widget from computed fields
            for widget_id, widget_config in widgets_config.items():
                widget_data = {}

                # Extract each field for this widget from computed fields
                # Pipeline field names should match widget field names
                for field_name in widget_config.field_extractors.keys():
                    widget_data[field_name] = row.computed.get(field_name)

                visit_info["widgets"][widget_id] = widget_data

            visit_data.append(visit_info)

        logger.info(f"[Timeline API] Built {len(visit_data)} visit data objects")

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
