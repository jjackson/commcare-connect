"""
Views for Custom Pipelines.

Provides views for listing, running, and editing AI-generated data pipelines.
"""

import json
import logging
from collections.abc import Generator

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from commcare_connect.labs.analysis.backends.sql.query_builder import generate_sql_preview
from commcare_connect.labs.analysis.pipeline import AnalysisPipeline
from commcare_connect.labs.analysis.sse_streaming import AnalysisPipelineSSEMixin, BaseSSEStreamView, send_sse_event
from commcare_connect.labs.custom_pipelines.data_access import PipelineDataAccess, json_to_pipeline_config

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Template Views
# -----------------------------------------------------------------------------


class PipelineListView(LoginRequiredMixin, TemplateView):
    """List all custom pipelines."""

    template_name = "custom_pipelines/list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        labs_context = getattr(self.request, "labs_context", {})
        opportunity_id = labs_context.get("opportunity_id")

        context["opportunity_id"] = opportunity_id
        context["opportunity_name"] = labs_context.get("opportunity_name")
        context["has_context"] = bool(opportunity_id)

        # Check for OAuth token
        labs_oauth = self.request.session.get("labs_oauth", {})
        context["has_oauth"] = bool(labs_oauth.get("access_token"))

        # Load pipelines if we have context
        if opportunity_id and labs_oauth.get("access_token"):
            try:
                data_access = PipelineDataAccess(request=self.request)
                context["pipelines"] = data_access.list_definitions()
                data_access.close()
            except Exception as e:
                logger.error(f"Failed to load pipelines: {e}")
                context["pipelines"] = []
                context["load_error"] = str(e)
        else:
            context["pipelines"] = []

        return context


class PipelineRunView(LoginRequiredMixin, TemplateView):
    """Run/execute a custom pipeline with visualization and AI chat."""

    template_name = "custom_pipelines/run.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        definition_id = self.kwargs.get("definition_id")

        labs_context = getattr(self.request, "labs_context", {})
        opportunity_id = labs_context.get("opportunity_id")

        context["definition_id"] = definition_id
        context["opportunity_id"] = opportunity_id
        context["opportunity_name"] = labs_context.get("opportunity_name")
        context["has_context"] = bool(opportunity_id)

        # Check for OAuth token
        labs_oauth = self.request.session.get("labs_oauth", {})
        context["has_oauth"] = bool(labs_oauth.get("access_token"))

        if opportunity_id and labs_oauth.get("access_token"):
            try:
                data_access = PipelineDataAccess(request=self.request)

                # Get pipeline definition
                definition = data_access.get_definition(definition_id)
                if definition:
                    context["definition"] = definition

                    # Get render code if exists
                    render_code = data_access.get_render_code(definition_id)
                    render_code_str = render_code.component_code if render_code else ""

                    # Build stream and API URLs
                    stream_url = reverse(
                        "labs:custom_pipelines:data_stream",
                        kwargs={"definition_id": definition_id},
                    )
                    sql_preview_url = reverse(
                        "labs:custom_pipelines:api_sql_preview",
                        kwargs={"definition_id": definition_id},
                    )

                    # Build pipeline_data dict for json_script
                    context["pipeline_data"] = {
                        "definition_id": definition_id,
                        "opportunity_id": opportunity_id,
                        "definition": {
                            "id": definition.id,
                            "name": definition.name,
                            "description": definition.description,
                            "schema": definition.schema,
                            "render_code_id": definition.render_code_id,
                        },
                        "schema": definition.schema,
                        "render_code": render_code_str,
                        "stream_url": stream_url,
                        "sql_preview_url": sql_preview_url,
                    }
                else:
                    context["error"] = "Pipeline not found"

                data_access.close()
            except Exception as e:
                logger.error(f"Failed to load pipeline: {e}")
                context["error"] = str(e)

        return context


# -----------------------------------------------------------------------------
# SSE Streaming Views
# -----------------------------------------------------------------------------


class PipelineDataStreamView(AnalysisPipelineSSEMixin, BaseSSEStreamView):
    """SSE streaming endpoint for pipeline data."""

    def get(self, request, *args, **kwargs):
        """Override get to store URL kwargs before streaming."""
        self.kwargs = kwargs
        return super().get(request)

    def stream_data(self, request) -> Generator[str, None, None]:
        """Stream pipeline data loading progress via SSE."""
        try:
            definition_id = self.kwargs.get("definition_id")

            # Check for context
            labs_context = getattr(request, "labs_context", {})
            opportunity_id = labs_context.get("opportunity_id") or request.GET.get("opportunity_id")

            if not opportunity_id:
                yield send_sse_event("Error", error="No opportunity selected")
                return

            # Check for OAuth token
            labs_oauth = request.session.get("labs_oauth", {})
            if not labs_oauth.get("access_token"):
                yield send_sse_event("Error", error="No OAuth token found. Please log in to Connect.")
                return

            # Get pipeline config
            data_access = PipelineDataAccess(request=request)
            pipeline_config = data_access.get_pipeline_config(definition_id)

            if not pipeline_config:
                yield send_sse_event("Error", error="Pipeline configuration not found")
                return

            # Run analysis pipeline with streaming
            pipeline = AnalysisPipeline(request)
            pipeline_stream = pipeline.stream_analysis(pipeline_config, opportunity_id=opportunity_id)

            logger.info(f"[Pipeline] Starting stream for definition {definition_id}, opportunity {opportunity_id}")

            # Stream all pipeline events as SSE (using mixin)
            yield from self.stream_pipeline_events(pipeline_stream)

            # Result is now available in self._pipeline_result
            result = self._pipeline_result
            from_cache = self._pipeline_from_cache

            if result:
                logger.info(f"[Pipeline] Got result with {len(result.rows) if hasattr(result, 'rows') else 0} rows")

                # Convert result to JSON-serializable format
                rows_data = []
                for row in result.rows:
                    row_dict = {
                        "username": row.username,
                        "visit_date": row.visit_date.isoformat() if row.visit_date else None,
                        "status": row.status,
                        "flagged": row.flagged,
                        "entity_id": row.entity_id,
                        "entity_name": row.entity_name,
                        "computed": row.computed if hasattr(row, "computed") else {},
                    }

                    # Add FLW-specific fields if this is an aggregated result
                    if hasattr(row, "total_visits"):
                        row_dict["total_visits"] = row.total_visits
                        row_dict["approved_visits"] = row.approved_visits
                        row_dict["pending_visits"] = row.pending_visits
                        row_dict["rejected_visits"] = row.rejected_visits
                        row_dict["flagged_visits"] = row.flagged_visits
                        row_dict["first_visit_date"] = (
                            row.first_visit_date.isoformat() if row.first_visit_date else None
                        )
                        row_dict["last_visit_date"] = row.last_visit_date.isoformat() if row.last_visit_date else None
                        row_dict["custom_fields"] = row.custom_fields if hasattr(row, "custom_fields") else {}

                    rows_data.append(row_dict)

                yield send_sse_event(
                    "Complete",
                    data={
                        "rows": rows_data,
                        "metadata": result.metadata,
                        "from_cache": from_cache,
                    },
                )
            else:
                logger.warning("[Pipeline] No result from pipeline")
                yield send_sse_event("Error", error="No data returned from pipeline")

            data_access.close()

        except Exception as e:
            logger.error(f"[Pipeline] Stream failed: {e}", exc_info=True)
            yield send_sse_event("Error", error=f"Failed to load pipeline data: {str(e)}")


# -----------------------------------------------------------------------------
# API Endpoints
# -----------------------------------------------------------------------------


@login_required
@require_GET
def api_sql_preview(request, definition_id):
    """
    Get SQL preview for a pipeline definition.

    Returns the SQL queries that would be executed without actually running them.
    """
    try:
        labs_context = getattr(request, "labs_context", {})
        opportunity_id = labs_context.get("opportunity_id") or request.GET.get("opportunity_id")

        if not opportunity_id:
            return JsonResponse({"error": "No opportunity selected"}, status=400)

        # Get pipeline config
        data_access = PipelineDataAccess(request=request)
        pipeline_config = data_access.get_pipeline_config(definition_id)

        if not pipeline_config:
            return JsonResponse({"error": "Pipeline configuration not found"}, status=404)

        # Generate SQL preview
        sql_preview = generate_sql_preview(pipeline_config, int(opportunity_id))

        data_access.close()

        return JsonResponse(sql_preview)

    except Exception as e:
        logger.error(f"Failed to generate SQL preview: {e}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_GET
def api_sql_preview_from_schema(request):
    """
    Get SQL preview from a JSON schema (without saving to database).

    This allows previewing SQL while editing in the UI before saving.

    Query params:
        schema: JSON-encoded pipeline schema
        opportunity_id: Opportunity ID for WHERE clause
    """
    try:
        schema_json = request.GET.get("schema")
        opportunity_id = request.GET.get("opportunity_id")

        if not schema_json:
            return JsonResponse({"error": "schema parameter required"}, status=400)

        if not opportunity_id:
            return JsonResponse({"error": "opportunity_id parameter required"}, status=400)

        try:
            schema = json.loads(schema_json)
        except json.JSONDecodeError as e:
            return JsonResponse({"error": f"Invalid JSON schema: {e}"}, status=400)

        # Convert JSON to config
        pipeline_config = json_to_pipeline_config(schema, experiment="preview")

        # Generate SQL preview
        sql_preview = generate_sql_preview(pipeline_config, int(opportunity_id))

        return JsonResponse(sql_preview)

    except Exception as e:
        logger.error(f"Failed to generate SQL preview from schema: {e}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_POST
def api_save_definition(request, definition_id):
    """Save updates to a pipeline definition."""
    try:
        data = json.loads(request.body)

        data_access = PipelineDataAccess(request=request)

        definition = data_access.update_definition(
            definition_id,
            name=data.get("name"),
            description=data.get("description"),
            schema=data.get("schema"),
        )

        if not definition:
            return JsonResponse({"error": "Pipeline not found"}, status=404)

        data_access.close()

        return JsonResponse({"success": True, "id": definition.id})

    except Exception as e:
        logger.error(f"Failed to save pipeline definition: {e}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_POST
def api_save_render_code(request, definition_id):
    """Save render code for a pipeline."""
    try:
        data = json.loads(request.body)
        component_code = data.get("component_code", "")

        data_access = PipelineDataAccess(request=request)
        render_code = data_access.save_render_code(definition_id, component_code)
        data_access.close()

        return JsonResponse({"success": True, "id": render_code.id})

    except Exception as e:
        logger.error(f"Failed to save render code: {e}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_GET
def api_chat_history(request, definition_id):
    """Get chat history for a pipeline."""
    try:
        data_access = PipelineDataAccess(request=request)
        messages = data_access.get_chat_history(definition_id)
        data_access.close()

        return JsonResponse({"messages": messages})

    except Exception as e:
        logger.error(f"Failed to get chat history: {e}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_POST
def api_clear_chat_history(request, definition_id):
    """Clear chat history for a pipeline."""
    try:
        data_access = PipelineDataAccess(request=request)
        data_access.clear_chat_history(definition_id)
        data_access.close()

        return JsonResponse({"success": True})

    except Exception as e:
        logger.error(f"Failed to clear chat history: {e}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_POST
def api_create_pipeline(request):
    """Create a new pipeline from a template."""
    try:
        data = json.loads(request.body)

        # Check if using a predefined template type
        template_type = data.get("template_type")

        if template_type:
            # Import templates from seed command
            from commcare_connect.labs.custom_pipelines.management.commands.seed_pipeline_templates import TEMPLATES

            if template_type not in TEMPLATES:
                return JsonResponse({"error": f"Unknown template type: {template_type}"}, status=400)

            template = TEMPLATES[template_type]
            name = data.get("name", template["name"])
            description = data.get("description", template["description"])
            schema = template["schema"]
            render_code = template["render_code"]
        else:
            # Use provided data directly
            name = data.get("name", "New Pipeline")
            description = data.get("description", "")
            schema = data.get("schema", {})
            render_code = data.get("render_code", "")

        data_access = PipelineDataAccess(request=request)

        definition = data_access.create_definition(
            name=name,
            description=description,
            schema=schema,
            render_code=render_code,
        )

        data_access.close()

        return JsonResponse({"success": True, "id": definition.id})

    except Exception as e:
        logger.error(f"Failed to create pipeline: {e}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)
