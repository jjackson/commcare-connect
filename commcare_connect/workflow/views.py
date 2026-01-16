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
from commcare_connect.workflow.management.commands.seed_example_workflow import TEMPLATES

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

            # Prepare data for React (pass as dict, json_script will handle encoding)
            context["workflow_data"] = {
                "definition": definition.data,
                "definition_id": definition.id,
                "opportunity_id": opportunity_id,
                "render_code": render_code.data.get("component_code") if render_code else None,
                "instance": run_data,
                "is_edit_mode": is_edit_mode,
                "workers": workers,
                "links": {
                    "auditUrlBase": "/labs/audit/create/",
                    "taskUrlBase": "/labs/tasks/new/",
                },
                "apiEndpoints": {
                    # In edit mode, state updates are local only
                    "updateState": None if is_edit_mode else f"/labs/workflow/api/run/{run_data['id']}/state/",
                    "getWorkers": "/labs/workflow/api/workers/",
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
def create_workflow_from_template(request):
    """Create a workflow from a template."""
    from django.contrib import messages
    from django.shortcuts import redirect

    template_key = request.POST.get("template", "performance_review")

    if template_key not in TEMPLATES:
        messages.error(request, f"Unknown template: {template_key}")
        return redirect("labs:workflow:list")

    template = TEMPLATES[template_key]
    template_def = template["definition"]

    try:
        data_access = WorkflowDataAccess(request=request)

        # Create the workflow definition
        definition = data_access.create_definition(
            name=template_def["name"],
            description=template_def["description"],
            version=template_def.get("version", 1),
            statuses=template_def.get("statuses", []),
            worker_fields=template_def.get("worker_fields", []),
            # Pass any extra fields from the definition
            **{
                k: v
                for k, v in template_def.items()
                if k not in ["name", "description", "version", "statuses", "worker_fields"]
            },
        )

        # Create the render code for this workflow
        data_access.save_render_code(
            definition_id=definition.id,
            component_code=template["render_code"],
            version=1,
        )

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
    """Create the example 'Weekly Performance Review' workflow. Deprecated: use create_workflow_from_template."""
    # Inject the template parameter and forward to the new function
    request.POST = request.POST.copy()
    request.POST["template"] = "performance_review"
    return create_workflow_from_template(request)


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
