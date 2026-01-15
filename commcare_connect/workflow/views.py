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

        # Get workflow definitions
        if context["has_context"]:
            try:
                data_access = WorkflowDataAccess(request=self.request)
                definitions = data_access.list_definitions()
                context["definitions"] = definitions
            except Exception as e:
                logger.error(f"Failed to load workflow definitions: {e}")
                context["definitions"] = []
                context["error"] = str(e)
        else:
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
    """Main UI for executing a workflow."""

    template_name = "workflow/run.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        definition_id = self.kwargs.get("definition_id")

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

            # Get or create workflow instance for this opportunity
            instance = data_access.get_or_create_instance(definition_id, opportunity_id)
            context["instance"] = instance

            # Get render code
            render_code = data_access.get_render_code(definition_id)
            context["render_code"] = render_code.data.get("component_code") if render_code else None

            # Get workers for the opportunity
            workers = data_access.get_workers(opportunity_id)
            context["workers"] = workers

            # Prepare data for React (pass as dict, json_script will handle encoding)
            context["workflow_data"] = {
                "definition": definition.data,
                "definition_id": definition.id,
                "instance": {
                    "id": instance.id,
                    "definition_id": definition_id,
                    "opportunity_id": opportunity_id,
                    "status": instance.data.get("status", "in_progress"),
                    "state": instance.data.get("state", {}),
                },
                "workers": workers,
                "links": {
                    "auditUrlBase": "/labs/audit/create/",
                    "taskUrlBase": "/labs/tasks/new/",
                },
                "apiEndpoints": {
                    "updateState": f"/labs/workflow/api/instance/{instance.id}/state/",
                    "getWorkers": "/labs/workflow/api/workers/",
                },
            }

        except Exception as e:
            logger.error(f"Failed to load workflow {definition_id}: {e}", exc_info=True)
            context["error"] = str(e)

        return context


class WorkflowInstanceView(LoginRequiredMixin, TemplateView):
    """View a specific workflow instance."""

    template_name = "workflow/instance.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        instance_id = self.kwargs.get("instance_id")

        try:
            data_access = WorkflowDataAccess(request=self.request)
            instance = data_access.get_instance(instance_id)
            if instance:
                context["instance"] = instance
                # Also get the definition
                definition_id = instance.data.get("definition_id")
                if definition_id:
                    context["definition"] = data_access.get_definition(definition_id)
        except Exception as e:
            logger.error(f"Failed to load workflow instance {instance_id}: {e}")
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
def update_state_api(request, instance_id):
    """API endpoint to update workflow instance state."""
    try:
        data = json.loads(request.body)
        new_state = data.get("state")

        if new_state is None:
            return JsonResponse({"error": "state required in request body"}, status=400)

        data_access = WorkflowDataAccess(request=request)
        updated_instance = data_access.update_instance_state(instance_id, new_state)

        if updated_instance:
            return JsonResponse(
                {
                    "success": True,
                    "instance": {
                        "id": updated_instance.id,
                        "state": updated_instance.data.get("state", {}),
                    },
                }
            )
        else:
            return JsonResponse({"error": "Instance not found"}, status=404)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.error(f"Failed to update instance state: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_GET
def get_instance_api(request, instance_id):
    """API endpoint to get workflow instance details."""
    try:
        data_access = WorkflowDataAccess(request=request)
        instance = data_access.get_instance(instance_id)

        if instance:
            return JsonResponse(
                {
                    "instance": {
                        "id": instance.id,
                        "definition_id": instance.data.get("definition_id"),
                        "opportunity_id": instance.opportunity_id,
                        "status": instance.data.get("status", "in_progress"),
                        "state": instance.data.get("state", {}),
                    }
                }
            )
        else:
            return JsonResponse({"error": "Instance not found"}, status=404)

    except Exception as e:
        logger.error(f"Failed to get instance: {e}")
        return JsonResponse({"error": str(e)}, status=500)


# Example workflow definition data
EXAMPLE_WORKFLOW_DEFINITION = {
    "name": "Weekly Performance Review",
    "description": "Review each worker's performance and mark as confirmed, needs audit, or create a task",
    "version": 1,
    "statuses": [
        {"id": "pending", "label": "Pending Review", "color": "gray"},
        {"id": "confirmed", "label": "Confirmed Good", "color": "green"},
        {"id": "needs_audit", "label": "Needs Audit", "color": "yellow"},
        {"id": "task_created", "label": "Task Created", "color": "blue"},
    ],
    "worker_fields": ["notes", "audit_id", "task_id"],
}

# Example render code - stored but currently rendered via inline JS in template
# In Phase 2, this will be dynamically loaded and executed
EXAMPLE_RENDER_CODE = """
// Weekly Performance Review Workflow Component
// This is sample render code that would be dynamically loaded in Phase 2

export function WorkflowUI({ definition, instance, workers, links, onUpdateState }) {
    // Get statuses and worker states
    const statuses = definition.statuses || [];
    const workerStates = instance.state?.worker_states || {};

    // Calculate stats
    const stats = { total: workers.length, reviewed: 0, counts: {} };
    statuses.forEach(s => stats.counts[s.id] = 0);
    workers.forEach(w => {
        const status = workerStates[w.username]?.status || 'pending';
        stats.counts[status] = (stats.counts[status] || 0) + 1;
        if (status !== 'pending') stats.reviewed++;
    });

    // Handle status change
    const handleStatusChange = async (username, newStatus) => {
        await onUpdateState({
            worker_states: {
                ...workerStates,
                [username]: { ...workerStates[username], status: newStatus }
            }
        });
    };

    // Render worker table with status dropdowns and action links
    return `
        <div class="space-y-6">
            <div class="bg-white rounded-lg shadow-sm p-6">
                <h1 class="text-2xl font-bold">${definition.name}</h1>
                <p class="text-gray-600">${definition.description}</p>
            </div>
            <div class="grid grid-cols-4 gap-4">
                <div class="bg-white p-4 rounded-lg shadow-sm">
                    <div class="text-3xl font-bold">${stats.total}</div>
                    <div class="text-gray-600">Total Workers</div>
                </div>
                <div class="bg-green-50 p-4 rounded-lg shadow-sm">
                    <div class="text-3xl font-bold text-green-700">${stats.reviewed}</div>
                    <div class="text-gray-600">Reviewed</div>
                </div>
            </div>
            <!-- Worker table rendered here -->
        </div>
    `;
}
"""


@login_required
@require_POST
def create_example_workflow(request):
    """Create the example 'Weekly Performance Review' workflow definition and render code."""
    from django.contrib import messages
    from django.shortcuts import redirect

    try:
        data_access = WorkflowDataAccess(request=request)

        # Create the workflow definition (always create a new one)
        definition = data_access.create_definition(
            name=EXAMPLE_WORKFLOW_DEFINITION["name"],
            description=EXAMPLE_WORKFLOW_DEFINITION["description"],
            version=EXAMPLE_WORKFLOW_DEFINITION["version"],
            statuses=EXAMPLE_WORKFLOW_DEFINITION["statuses"],
            worker_fields=EXAMPLE_WORKFLOW_DEFINITION["worker_fields"],
        )

        # Also create the render code for this workflow
        data_access.save_render_code(
            definition_id=definition.id,
            component_code=EXAMPLE_RENDER_CODE,
            version=1,
        )

        messages.success(
            request, f"Created example workflow: {definition.name} (ID: {definition.id}) with render code"
        )
        return redirect("labs:workflow:list")

    except Exception as e:
        logger.error(f"Failed to create example workflow: {e}", exc_info=True)
        messages.error(request, f"Failed to create example workflow: {e}")
        return redirect("labs:workflow:list")
