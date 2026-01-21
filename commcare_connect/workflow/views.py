"""
Workflow views for dynamic AI-generated workflows.

These views handle listing, viewing, and executing workflows that are stored
as LabsRecord objects with React component code for rendering.
"""

import json
import logging

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView

from commcare_connect.workflow.data_access import WorkflowDataAccess
from commcare_connect.workflow.templates import TEMPLATES
from commcare_connect.workflow.templates import create_workflow_from_template as create_from_template

logger = logging.getLogger(__name__)


class WorkflowListView(LoginRequiredMixin, TemplateView):
    """List all workflow definitions the user can access."""

    template_name = "workflow/list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Check for labs context
        labs_context = getattr(self.request, "labs_context", {})
        context["has_context"] = bool(labs_context.get("opportunity_id") or labs_context.get("program_id"))
        context["opportunity_id"] = labs_context.get("opportunity_id")
        context["opportunity_name"] = labs_context.get("opportunity_name")

        # Get workflow definitions and their runs
        if context["has_context"]:
            try:
                data_access = WorkflowDataAccess(request=self.request)
                definitions = data_access.list_definitions()

                # For each definition, get its runs
                workflows_with_runs = []
                for definition in definitions:
                    runs = data_access.list_runs(definition.id)
                    workflows_with_runs.append(
                        {
                            "definition": definition,
                            "runs": runs,
                            "run_count": len(runs),
                        }
                    )

                context["workflows"] = workflows_with_runs
                context["definitions"] = definitions  # Keep for backwards compatibility
            except Exception as e:
                logger.error(f"Failed to load workflow definitions: {e}")
                context["workflows"] = []
                context["definitions"] = []
                context["error"] = str(e)
        else:
            context["workflows"] = []
            context["definitions"] = []

        return context


class WorkflowDefinitionView(LoginRequiredMixin, TemplateView):
    """View workflow definition details."""

    template_name = "workflow/detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        definition_id = self.kwargs.get("definition_id")

        try:
            data_access = WorkflowDataAccess(request=self.request)
            definition = data_access.get_definition(definition_id)
            context["definition"] = definition
            context["definition_json"] = json.dumps(definition.data if definition else {}, indent=2)
        except Exception as e:
            logger.error(f"Failed to load workflow definition {definition_id}: {e}")
            context["error"] = str(e)

        return context


class WorkflowRunView(LoginRequiredMixin, TemplateView):
    """Main UI for executing a workflow. Also handles edit mode via ?edit=true."""

    template_name = "workflow/run.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        definition_id = self.kwargs.get("definition_id")

        # Check for run_id in query params (to load existing run)
        run_id = self.request.GET.get("run_id")
        # Check for edit mode (temporary run, not persisted)
        is_edit_mode = self.request.GET.get("edit") == "true"

        # Get labs context
        labs_context = getattr(self.request, "labs_context", {})
        opportunity_id = labs_context.get("opportunity_id")
        context["opportunity_id"] = opportunity_id
        context["opportunity_name"] = labs_context.get("opportunity_name")
        context["has_context"] = bool(opportunity_id)

        if not opportunity_id:
            context["error"] = "Please select an opportunity to run this workflow."
            return context

        try:
            data_access = WorkflowDataAccess(request=self.request)

            # Get workflow definition
            definition = data_access.get_definition(definition_id)
            if not definition:
                context["error"] = f"Workflow definition {definition_id} not found."
                return context
            context["definition"] = definition

            # Get render code
            render_code = data_access.get_render_code(definition_id)
            context["render_code"] = render_code.data.get("component_code") if render_code else None

            # Get workers for the opportunity
            workers = data_access.get_workers(opportunity_id)
            context["workers"] = workers

            # Get or create run based on mode
            if is_edit_mode:
                # Edit mode: create temporary run (not persisted)
                from datetime import datetime, timedelta

                today = datetime.now().date()
                week_start = today - timedelta(days=today.weekday())
                week_end = week_start + timedelta(days=6)

                run_data = {
                    "id": 0,  # Temporary ID
                    "definition_id": definition_id,
                    "opportunity_id": opportunity_id,
                    "status": "preview",
                    "state": {"worker_states": {}},
                    "period_start": week_start.isoformat(),
                    "period_end": week_end.isoformat(),
                }
                context["is_edit_mode"] = True
            elif run_id:
                # Load existing run by ID
                run = data_access.get_run(int(run_id))
                if not run:
                    context["error"] = f"Workflow run {run_id} not found."
                    return context
                run_data = {
                    "id": run.id,
                    "definition_id": definition_id,
                    "opportunity_id": opportunity_id,
                    "status": run.data.get("status", "in_progress"),
                    "state": run.data.get("state", {}),
                    "period_start": run.data.get("period_start"),
                    "period_end": run.data.get("period_end"),
                }
                context["is_edit_mode"] = False
            else:
                # Create new run (always creates a fresh run)
                from datetime import datetime, timedelta

                today = datetime.now().date()
                week_start = today - timedelta(days=today.weekday())
                week_end = week_start + timedelta(days=6)

                run = data_access.create_run(
                    definition_id=definition_id,
                    opportunity_id=opportunity_id,
                    period_start=week_start.isoformat(),
                    period_end=week_end.isoformat(),
                    initial_state={"worker_states": {}},
                )
                run_data = {
                    "id": run.id,
                    "definition_id": definition_id,
                    "opportunity_id": opportunity_id,
                    "status": run.data.get("status", "in_progress"),
                    "state": run.data.get("state", {}),
                    "period_start": run.data.get("period_start"),
                    "period_end": run.data.get("period_end"),
                }
                context["is_edit_mode"] = False

            # Fetch pipeline data if workflow has pipeline sources
            pipeline_data = {}
            if definition.pipeline_sources:
                try:
                    pipeline_data = data_access.get_pipeline_data(definition_id, opportunity_id)
                except Exception as e:
                    logger.warning(f"Failed to fetch pipeline data: {e}")

            # Prepare data for React (pass as dict, json_script will handle encoding)
            context["workflow_data"] = {
                "definition": definition.data,
                "definition_id": definition.id,
                "opportunity_id": opportunity_id,
                "render_code": render_code.data.get("component_code") if render_code else None,
                "instance": run_data,
                "is_edit_mode": is_edit_mode,
                "workers": workers,
                "pipeline_data": pipeline_data,
                "links": {
                    "auditUrlBase": "/labs/audit/create/",
                    "taskUrlBase": "/labs/tasks/new/",
                },
                "apiEndpoints": {
                    # In edit mode, state updates are local only
                    "updateState": None if is_edit_mode else f"/labs/workflow/api/run/{run_data['id']}/state/",
                    "getWorkers": "/labs/workflow/api/workers/",
                    "getPipelineData": f"/labs/workflow/api/{definition_id}/pipeline-data/",
                },
            }

        except Exception as e:
            logger.error(f"Failed to load workflow {definition_id}: {e}", exc_info=True)
            context["error"] = str(e)

        return context


class WorkflowRunDetailView(LoginRequiredMixin, TemplateView):
    """View a specific workflow run."""

    template_name = "workflow/run_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        run_id = self.kwargs.get("run_id")

        try:
            data_access = WorkflowDataAccess(request=self.request)
            run = data_access.get_run(run_id)
            if run:
                context["run"] = run
                # Also get the definition
                definition_id = run.data.get("definition_id")
                if definition_id:
                    context["definition"] = data_access.get_definition(definition_id)
        except Exception as e:
            logger.error(f"Failed to load workflow run {run_id}: {e}")
            context["error"] = str(e)

        return context


@login_required
@require_GET
def get_workers_api(request):
    """API endpoint to fetch workers for an opportunity."""
    labs_context = getattr(request, "labs_context", {})
    opportunity_id = labs_context.get("opportunity_id") or request.GET.get("opportunity_id")

    if not opportunity_id:
        return JsonResponse({"error": "opportunity_id required"}, status=400)

    try:
        data_access = WorkflowDataAccess(request=request)
        workers = data_access.get_workers(opportunity_id)
        return JsonResponse({"workers": workers})
    except Exception as e:
        logger.error(f"Failed to fetch workers: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_POST
def update_state_api(request, run_id):
    """API endpoint to update workflow run state."""
    try:
        data = json.loads(request.body)
        new_state = data.get("state")

        if new_state is None:
            return JsonResponse({"error": "state required in request body"}, status=400)

        data_access = WorkflowDataAccess(request=request)
        updated_run = data_access.update_run_state(run_id, new_state)

        if updated_run:
            return JsonResponse(
                {
                    "success": True,
                    "run": {
                        "id": updated_run.id,
                        "state": updated_run.data.get("state", {}),
                    },
                }
            )
        else:
            return JsonResponse({"error": "Run not found"}, status=404)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.error(f"Failed to update run state: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_GET
def get_run_api(request, run_id):
    """API endpoint to get workflow run details."""
    try:
        data_access = WorkflowDataAccess(request=request)
        run = data_access.get_run(run_id)

        if run:
            return JsonResponse(
                {
                    "run": {
                        "id": run.id,
                        "definition_id": run.data.get("definition_id"),
                        "opportunity_id": run.opportunity_id,
                        "status": run.data.get("status", "in_progress"),
                        "state": run.data.get("state", {}),
                    }
                }
            )
        else:
            return JsonResponse({"error": "Run not found"}, status=404)

    except Exception as e:
        logger.error(f"Failed to get run: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_POST
def create_workflow_from_template_view(request):
    """Create a workflow from a template."""
    from django.contrib import messages
    from django.shortcuts import redirect

    template_key = request.POST.get("template", "performance_review")

    if template_key not in TEMPLATES:
        messages.error(request, f"Unknown template: {template_key}")
        return redirect("labs:workflow:list")

    try:
        data_access = WorkflowDataAccess(request=request)
        definition, render_code = create_from_template(data_access, template_key)

        messages.success(request, f"Created workflow: {definition.name} (ID: {definition.id})")
        return redirect("labs:workflow:list")

    except Exception as e:
        logger.error(f"Failed to create workflow from template {template_key}: {e}", exc_info=True)
        messages.error(request, f"Failed to create workflow: {e}")
        return redirect("labs:workflow:list")


# Keep old function name for backwards compatibility
@login_required
@require_POST
def create_example_workflow(request):
    """Create the example 'Weekly Performance Review' workflow. Deprecated: use create_workflow_from_template_view."""
    # Inject the template parameter and forward to the new function
    request.POST = request.POST.copy()
    request.POST["template"] = "performance_review"
    return create_workflow_from_template_view(request)


@login_required
@require_GET
def get_chat_history_api(request, definition_id):
    """API endpoint to get chat history for a workflow definition."""
    try:
        data_access = WorkflowDataAccess(request=request)
        messages = data_access.get_chat_messages(definition_id)

        return JsonResponse(
            {
                "success": True,
                "definition_id": definition_id,
                "messages": messages,
            }
        )

    except Exception as e:
        logger.error(f"Failed to get chat history for definition {definition_id}: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_POST
def clear_chat_history_api(request, definition_id):
    """API endpoint to clear chat history for a workflow definition."""
    try:
        data_access = WorkflowDataAccess(request=request)
        cleared = data_access.clear_chat_history(definition_id)

        return JsonResponse(
            {
                "success": True,
                "definition_id": definition_id,
                "cleared": cleared,
            }
        )

    except Exception as e:
        logger.error(f"Failed to clear chat history for definition {definition_id}: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_POST
def add_chat_message_api(request, definition_id):
    """API endpoint to add a message to chat history."""
    try:
        data = json.loads(request.body)
        role = data.get("role")
        content = data.get("content")

        if not role or not content:
            return JsonResponse({"error": "role and content are required"}, status=400)

        if role not in ("user", "assistant"):
            return JsonResponse({"error": "role must be 'user' or 'assistant'"}, status=400)

        data_access = WorkflowDataAccess(request=request)
        data_access.add_chat_message(definition_id, role, content)

        return JsonResponse(
            {
                "success": True,
                "definition_id": definition_id,
            }
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.error(f"Failed to add chat message for definition {definition_id}: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_POST
def save_render_code_api(request, definition_id):
    """API endpoint to save render code for a workflow definition."""
    try:
        data = json.loads(request.body)
        component_code = data.get("component_code")
        definition_data = data.get("definition")

        if not component_code:
            return JsonResponse({"error": "component_code is required"}, status=400)

        data_access = WorkflowDataAccess(request=request)

        # Save render code
        render_code_record = data_access.save_render_code(
            definition_id=definition_id,
            component_code=component_code,
            version=1,  # TODO: implement versioning
        )

        # Optionally update definition if provided
        if definition_data:
            data_access.update_definition(definition_id, definition_data)

        return JsonResponse(
            {
                "success": True,
                "definition_id": definition_id,
                "render_code_id": render_code_record.id,
            }
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.error(f"Failed to save render code for definition {definition_id}: {e}")
        return JsonResponse({"error": str(e)}, status=500)


# =============================================================================
# OCS Integration APIs
# =============================================================================


@login_required
def ocs_status_api(request):
    """Check if OCS OAuth is configured and valid for the current user."""
    from commcare_connect.labs.integrations.ocs.api_client import OCSDataAccess

    try:
        ocs = OCSDataAccess(request=request)
        connected = ocs.check_token_valid()
        ocs.close()

        return JsonResponse(
            {
                "connected": connected,
                "login_url": "/labs/ocs/initiate/",
            }
        )
    except Exception as e:
        logger.error(f"Error checking OCS status: {e}")
        return JsonResponse(
            {
                "connected": False,
                "login_url": "/labs/ocs/initiate/",
                "error": str(e),
            }
        )


@login_required
def ocs_bots_api(request):
    """List available OCS bots for the current user."""
    from commcare_connect.labs.integrations.ocs.api_client import OCSAPIError, OCSDataAccess

    try:
        ocs = OCSDataAccess(request=request)

        if not ocs.check_token_valid():
            ocs.close()
            return JsonResponse({"success": False, "needs_oauth": True}, status=401)

        experiments = ocs.list_experiments()
        ocs.close()

        # Format bots for frontend
        bots = [
            {
                "id": exp.get("public_id") or exp.get("id"),
                "name": exp.get("name", "Unnamed Bot"),
                "version": exp.get("version_number", 1),
            }
            for exp in experiments
        ]

        return JsonResponse({"success": True, "bots": bots})

    except OCSAPIError as e:
        logger.error(f"OCS API error listing bots: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)
    except Exception as e:
        logger.error(f"Error listing OCS bots: {e}", exc_info=True)
        return JsonResponse({"success": False, "error": str(e)}, status=500)


# =============================================================================
# Pipeline Data APIs
# =============================================================================


@login_required
@require_GET
def get_pipeline_data_api(request, definition_id):
    """
    API endpoint to fetch pipeline data for a workflow.

    Returns data from all pipeline sources defined in the workflow.
    """
    labs_context = getattr(request, "labs_context", {})
    opportunity_id = labs_context.get("opportunity_id") or request.GET.get("opportunity_id")

    if not opportunity_id:
        return JsonResponse({"error": "opportunity_id required"}, status=400)

    try:
        data_access = WorkflowDataAccess(request=request)
        pipeline_data = data_access.get_pipeline_data(definition_id, int(opportunity_id))
        data_access.close()

        return JsonResponse(pipeline_data)

    except Exception as e:
        logger.error(f"Failed to fetch pipeline data for workflow {definition_id}: {e}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_GET
def list_available_pipelines_api(request):
    """
    API endpoint to list pipelines available to add as sources.

    Returns user's own pipelines plus shared pipelines.
    """
    from commcare_connect.workflow.data_access import PipelineDataAccess

    try:
        data_access = PipelineDataAccess(request=request)
        pipelines = data_access.list_definitions(include_shared=True)
        data_access.close()

        result = [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "is_shared": p.is_shared,
                "shared_scope": p.shared_scope,
            }
            for p in pipelines
        ]

        return JsonResponse({"pipelines": result})

    except Exception as e:
        logger.error(f"Failed to list available pipelines: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_POST
def add_pipeline_source_api(request, definition_id):
    """
    API endpoint to add a pipeline as a data source for a workflow.
    """
    try:
        data = json.loads(request.body)
        pipeline_id = data.get("pipeline_id")
        alias = data.get("alias")

        if not pipeline_id or not alias:
            return JsonResponse({"error": "pipeline_id and alias are required"}, status=400)

        data_access = WorkflowDataAccess(request=request)
        updated = data_access.add_pipeline_source(definition_id, int(pipeline_id), alias)
        data_access.close()

        if updated:
            return JsonResponse(
                {
                    "success": True,
                    "definition_id": definition_id,
                    "pipeline_sources": updated.pipeline_sources,
                }
            )
        else:
            return JsonResponse({"error": "Workflow not found"}, status=404)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.error(f"Failed to add pipeline source: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_POST
def remove_pipeline_source_api(request, definition_id):
    """
    API endpoint to remove a pipeline source from a workflow.
    """
    try:
        data = json.loads(request.body)
        alias = data.get("alias")

        if not alias:
            return JsonResponse({"error": "alias is required"}, status=400)

        data_access = WorkflowDataAccess(request=request)
        updated = data_access.remove_pipeline_source(definition_id, alias)
        data_access.close()

        if updated:
            return JsonResponse(
                {
                    "success": True,
                    "definition_id": definition_id,
                    "pipeline_sources": updated.pipeline_sources,
                }
            )
        else:
            return JsonResponse({"error": "Workflow not found"}, status=404)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.error(f"Failed to remove pipeline source: {e}")
        return JsonResponse({"error": str(e)}, status=500)


# =============================================================================
# Sharing APIs
# =============================================================================


@login_required
@require_POST
def share_workflow_api(request, definition_id):
    """API endpoint to share a workflow."""
    try:
        data = json.loads(request.body)
        scope = data.get("scope", "global")

        if scope not in ("program", "organization", "global"):
            return JsonResponse({"error": "scope must be 'program', 'organization', or 'global'"}, status=400)

        data_access = WorkflowDataAccess(request=request)
        updated = data_access.share_workflow(definition_id, scope)
        data_access.close()

        if updated:
            return JsonResponse(
                {
                    "success": True,
                    "definition_id": definition_id,
                    "is_shared": True,
                    "shared_scope": scope,
                }
            )
        else:
            return JsonResponse({"error": "Workflow not found"}, status=404)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.error(f"Failed to share workflow {definition_id}: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_POST
def unshare_workflow_api(request, definition_id):
    """API endpoint to unshare a workflow."""
    try:
        data_access = WorkflowDataAccess(request=request)
        updated = data_access.unshare_workflow(definition_id)
        data_access.close()

        if updated:
            return JsonResponse(
                {
                    "success": True,
                    "definition_id": definition_id,
                    "is_shared": False,
                }
            )
        else:
            return JsonResponse({"error": "Workflow not found"}, status=404)

    except Exception as e:
        logger.error(f"Failed to unshare workflow {definition_id}: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_GET
def list_shared_workflows_api(request):
    """API endpoint to list shared workflows."""
    scope = request.GET.get("scope", "global")

    try:
        data_access = WorkflowDataAccess(request=request)
        shared = data_access.list_shared_workflows(scope)
        data_access.close()

        result = [
            {
                "id": w.id,
                "name": w.name,
                "description": w.description,
                "shared_scope": w.shared_scope,
            }
            for w in shared
        ]

        return JsonResponse({"workflows": result})

    except Exception as e:
        logger.error(f"Failed to list shared workflows: {e}")
        return JsonResponse({"error": str(e)}, status=500)
