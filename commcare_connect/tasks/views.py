"""
Task views using ExperimentRecord-based TaskRecord model.

These views replace the old Django ORM-based views with ExperimentRecord-backed
implementation using TaskDataAccess for OAuth-based API access.
"""

import json
import logging

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView, TemplateView

from commcare_connect.tasks.data_access import TaskDataAccess
from commcare_connect.tasks.models import TaskRecord
from commcare_connect.tasks.ocs_client import OCSClientError, get_recent_session, get_transcript, trigger_bot

logger = logging.getLogger(__name__)


class TaskListView(LoginRequiredMixin, ListView):
    """List view for tasks with filtering and statistics."""

    model = TaskRecord
    template_name = "tasks/tasks_list.html"
    context_object_name = "tasks"
    paginate_by = 50

    def get_queryset(self):
        """Get tasks the user can access with filtering."""
        # Check if required context is present (program or opportunity)
        labs_context = getattr(self.request, "labs_context", {})
        if not labs_context.get("opportunity_id") and not labs_context.get("program_id"):
            # No program or opportunity selected, return empty list
            return []

        data_access = TaskDataAccess(user=self.request.user, request=self.request)

        # Get all tasks (OAuth enforces access) - returns a list, not QuerySet
        tasks = data_access.get_tasks()

        # Apply filters from GET parameters
        status_filter = self.request.GET.get("status")
        if status_filter and status_filter != "all":
            tasks = [t for t in tasks if t.status == status_filter]

        action_type_filter = self.request.GET.get("action_type")
        if action_type_filter and action_type_filter != "all":
            tasks = [t for t in tasks if t.task_type == action_type_filter]

        search_query = self.request.GET.get("search")
        if search_query:
            search_lower = search_query.lower()
            tasks = [t for t in tasks if search_lower in t.title.lower()]

        # Sort by id descending (higher IDs are more recent)
        return sorted(tasks, key=lambda x: x.id, reverse=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Check if required context is present (program or opportunity)
        labs_context = getattr(self.request, "labs_context", {})
        has_context = bool(labs_context.get("opportunity_id") or labs_context.get("program_id"))

        if has_context:
            data_access = TaskDataAccess(user=self.request.user, request=self.request)
            all_tasks = data_access.get_tasks()
        else:
            all_tasks = []

        # Calculate statistics - all_tasks is a list, not QuerySet
        stats = {
            "total": len(all_tasks),
            "unassigned": len([t for t in all_tasks if t.status == "unassigned"]),
            "network_manager": len([t for t in all_tasks if t.status == "network_manager"]),
            "program_manager": len([t for t in all_tasks if t.status == "program_manager"]),
            "action_underway": len([t for t in all_tasks if t.status == "action_underway"]),
            "resolved": len([t for t in all_tasks if t.status == "resolved"]),
        }

        # Status and type choices for filters
        statuses = [
            "unassigned",
            "network_manager",
            "program_manager",
            "action_underway",
            "resolved",
            "closed",
        ]
        action_types = ["warning", "deactivation"]

        # Check for Connect OAuth token
        has_token = False
        token_expires_at = None

        # For LabsUser, check session
        if hasattr(self.request.user, "is_labs_user") and self.request.user.is_labs_user:
            has_token = True  # LabsUser always has token via OAuth

        # For regular Django users, check SocialToken
        else:
            from allauth.socialaccount.models import SocialAccount, SocialToken

            try:
                social_account = SocialAccount.objects.get(user=self.request.user, provider="connect")
                social_token = SocialToken.objects.get(account=social_account)
                has_token = True
                token_expires_at = social_token.expires_at
            except (SocialAccount.DoesNotExist, SocialToken.DoesNotExist):
                pass

        context.update(
            {
                "stats": stats,
                "statuses": statuses,
                "action_types": action_types,
                "selected_status": self.request.GET.get("status", "all"),
                "selected_action_type": self.request.GET.get("action_type", "all"),
                "has_connect_token": has_token,
                "token_expires_at": token_expires_at,
                "has_context": has_context,
            }
        )

        return context


class TaskDetailView(LoginRequiredMixin, DetailView):
    """Detail view for a single task."""

    model = TaskRecord
    template_name = "tasks/task_detail_streamlined.html"
    context_object_name = "task"
    pk_url_kwarg = "task_id"

    def get_object(self, queryset=None):
        """Get task by ID."""
        task_id = self.kwargs.get(self.pk_url_kwarg)
        data_access = TaskDataAccess(user=self.request.user, request=self.request)
        task = data_access.get_task(task_id)

        if not task:
            from django.http import Http404

            raise Http404("Task not found")

        return task

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        task = self.object

        # Get timeline (events + comments combined)
        timeline = task.get_timeline()

        # Get FLW history (past tasks for the same user) - returns list, not QuerySet
        data_access = TaskDataAccess(user=self.request.user, request=self.request)
        formatted_history = []

        # Try to get FLW history, but handle errors gracefully (e.g., invalid username)
        try:
            if task.task_username:
                all_flw_tasks = data_access.get_tasks(username=task.task_username)

                # Filter out current task and sort by id descending
                flw_history = [t for t in all_flw_tasks if t.id != task.id]
                flw_history = sorted(flw_history, key=lambda x: x.id, reverse=True)[:5]

                # Format history for template
                for hist in flw_history:
                    formatted_history.append(
                        {
                            "id": hist.id,
                            "task_type": hist.task_type,
                            "status": hist.status,
                            "title": hist.title,
                        }
                    )
        except Exception as e:
            # Log the error but don't crash the page
            logger.error(f"Failed to fetch FLW history for task {task.id}: {e}", exc_info=True)

        context.update(
            {
                "task": {
                    "id": task.id,
                    "user_id": task.user_id,
                    "opportunity_id": task.opportunity_id,
                    "task_type": task.task_type,
                    "status": task.status,
                    "priority": task.priority,
                    "title": task.title,
                    "description": task.description,
                    "learning_assignment_text": task.learning_assignment_text,
                    "audit_session_id": task.audit_session_id,
                    "assigned_to_id": task.assigned_to_id,
                    "created_by_id": task.created_by_id,
                    "timeline": timeline,
                    "flw_history": formatted_history,
                },
            }
        )

        return context


class TaskCreationWizardView(LoginRequiredMixin, TemplateView):
    """Wizard interface for creating tasks using Connect OAuth."""

    template_name = "tasks/task_creation_wizard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Check for Connect OAuth token
        has_token = False
        token_expires_at = None

        # For LabsUser, check session
        if hasattr(self.request.user, "is_labs_user") and self.request.user.is_labs_user:
            has_token = True

        # For regular Django users, check SocialToken
        else:
            from allauth.socialaccount.models import SocialAccount, SocialToken

            try:
                social_account = SocialAccount.objects.get(user=self.request.user, provider="connect")
                social_token = SocialToken.objects.get(account=social_account)
                has_token = True
                token_expires_at = social_token.expires_at
            except (SocialAccount.DoesNotExist, SocialToken.DoesNotExist):
                pass

        context.update(
            {
                "has_connect_token": has_token,
                "token_expires_at": token_expires_at,
            }
        )

        return context


# Opportunity API Views (used by creation wizard)


class OpportunitySearchAPIView(LoginRequiredMixin, View):
    """Search opportunities via Connect OAuth API."""

    def get(self, request):
        query = request.GET.get("query", "")
        limit = int(request.GET.get("limit", 50))

        try:
            data_access = TaskDataAccess(user=request.user, request=request)
            opportunities = data_access.search_opportunities(query, limit)
            data_access.close()

            return JsonResponse({"success": True, "opportunities": opportunities})

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


class OpportunityWorkersAPIView(LoginRequiredMixin, View):
    """Get workers for an opportunity via Connect OAuth API."""

    def get(self, request, opportunity_id):
        try:
            data_access = TaskDataAccess(user=request.user, request=request)
            workers = data_access.get_users_from_opportunity(opportunity_id)
            data_access.close()

            return JsonResponse({"success": True, "workers": workers})

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


# Database Management API Views


class DatabaseStatsAPIView(LoginRequiredMixin, View):
    """Get database statistics for tasks."""

    def get(self, request):
        try:
            # TODO: Update to use LabsRecordAPIClient with opportunity_id
            stats = {
                "tasks": 0,  # Would need to query API
                "events": 0,
                "comments": 0,
                "ai_sessions": 0,
            }

            return JsonResponse({"success": True, "stats": stats})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


@method_decorator(csrf_exempt, name="dispatch")
class DatabaseResetAPIView(LoginRequiredMixin, View):
    """Reset tasks database (delete all experiment records)."""

    def post(self, request):
        try:
            # TODO: Update to use LabsRecordAPIClient with opportunity_id for deletion
            deleted = (0, {})

            return JsonResponse({"success": True, "deleted": deleted})
        except Exception as e:
            import traceback

            return JsonResponse({"error": str(e), "traceback": traceback.format_exc()}, status=500)


# Task Bulk Creation API


@login_required
@csrf_exempt
@require_POST
def task_bulk_create(request):
    """Create multiple tasks at once (bulk creation)."""
    try:
        body = json.loads(request.body)
        opportunity_id = body.get("opportunity_id")
        flw_ids = body.get("flw_ids", [])
        task_type = body.get("task_type", "warning")
        priority = body.get("priority", "medium")
        title = body.get("title", "")
        description = body.get("description", "")
        learning_assignment_text = body.get("learning_assignment_text", "")

        if not opportunity_id:
            return JsonResponse({"success": False, "error": "opportunity_id is required"}, status=400)

        if not flw_ids:
            return JsonResponse({"success": False, "error": "At least one FLW must be selected"}, status=400)

        data_access = TaskDataAccess(user=request.user, request=request)
        created_count = 0
        errors = []

        for flw_id in flw_ids:
            try:
                # Create task for each FLW
                data_access.create_task(
                    username=str(flw_id),  # Using flw_id as username for now
                    opportunity_id=opportunity_id,
                    created_by_id=request.user.id if hasattr(request.user, "id") else 0,
                    task_type=task_type,
                    priority=priority,
                    title=title,
                    description=description,
                    learning_assignment_text=learning_assignment_text,
                    creator_name=request.user.get_full_name() if hasattr(request.user, "get_full_name") else "User",
                )
                created_count += 1
            except Exception as e:
                errors.append(f"Failed to create task for FLW {flw_id}: {str(e)}")
                logger.error(f"Error creating task for FLW {flw_id}: {e}", exc_info=True)

        data_access.close()

        return JsonResponse({"success": True, "created_count": created_count, "errors": errors})

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.error(f"Error in bulk task creation: {e}", exc_info=True)
        return JsonResponse({"success": False, "error": str(e)}, status=500)


# AI Assistant Integration Views


@login_required
@csrf_exempt
@require_POST
def task_initiate_ai(request, task_id):
    """Initiate an AI assistant conversation for a task via OCS."""
    try:
        # Get the task using TaskDataAccess
        data_access = TaskDataAccess(user=request.user, request=request)
        task = data_access.get_task(task_id)
        if not task:
            return JsonResponse({"error": "Task not found"}, status=404)
    except Exception:
        return JsonResponse({"error": "Task not found"}, status=404)

    try:
        # Parse request body
        body = json.loads(request.body)

        # Extract parameters from request
        identifier = body.get("identifier", "").strip()
        experiment = body.get("experiment", "").strip()
        platform = body.get("platform", "commcare_connect")
        prompt_text = body.get("prompt_text", "").strip()
        start_new_session = body.get("start_new_session", False)

        # Validate required fields
        if not identifier:
            return JsonResponse({"error": "Participant ID is required"}, status=400)
        if not experiment:
            return JsonResponse({"error": "Bot ID (experiment) is required"}, status=400)
        if not prompt_text:
            return JsonResponse({"error": "Prompt instructions are required"}, status=400)

        # Prepare session data to link back to Connect
        session_data = {
            "task_id": str(task.id),
            "task_type": task.task_type,
            "opportunity_id": str(task.opportunity_id),
            "username": task.username,
            "created_by": request.user.username if hasattr(request.user, "username") else "unknown",
        }

        # Trigger bot with OCS
        trigger_bot(
            identifier=identifier,
            platform=platform,
            bot_id=experiment,
            prompt_text=prompt_text,
            start_new_session=start_new_session,
            session_data=session_data,
        )

        # Add AI session to task using nested JSON
        task.add_ai_session(
            ocs_session_id=None,  # Will be populated later via manual linking
            status="pending",
            metadata={
                "parameters": {
                    "identifier": identifier,
                    "experiment": experiment,
                    "platform": platform,
                    "prompt_text": prompt_text,
                }
            },
        )

        # Add event for AI conversation initiation
        task.add_event(
            event_type="ai_initiated",
            actor=request.user.username if hasattr(request.user, "username") else "system",
            actor_user_id=request.user.id if hasattr(request.user, "id") else 0,
            description=f"Triggered AI assistant for {identifier}",
        )

        # Save task via data access
        data_access.save_task(task)
        data_access.close()

        return JsonResponse(
            {
                "success": True,
                "message": "AI conversation initiated. The session ID can be linked manually once available.",
            }
        )

    except OCSClientError as e:
        logger.error(f"OCS error when initiating AI for task {task_id}: {e}")
        return JsonResponse({"error": str(e)}, status=500)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON in request body"}, status=400)
    except Exception as e:
        logger.error(f"Unexpected error when initiating AI for task {task_id}: {e}")
        return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)


@login_required
def task_ai_sessions(request, task_id):
    """Get AI sessions for a task and try to populate session_id from OCS if missing."""
    try:
        data_access = TaskDataAccess(user=request.user, request=request)
        task = data_access.get_task(task_id)
        if not task:
            return JsonResponse({"error": "Task not found"}, status=404)
    except Exception:
        return JsonResponse({"error": "Task not found"}, status=404)

    # Get all AI sessions from task's nested data
    ai_sessions = task.ai_sessions or []

    # Get the specific session ID from query params (if polling for a specific session)
    session_index = request.GET.get("session_index")

    pending_session = None
    if session_index is not None:
        try:
            idx = int(session_index)
            if 0 <= idx < len(ai_sessions):
                session = ai_sessions[idx]
                if not session.get("session_id"):
                    pending_session = session
        except (ValueError, IndexError):
            pass

    # Try to fetch and populate session_id from OCS
    if pending_session and pending_session.get("session_metadata"):
        params = pending_session["session_metadata"].get("parameters", {})
        experiment = params.get("experiment")
        identifier = params.get("identifier")

        if experiment and identifier:
            try:
                # Query OCS for recent sessions
                sessions = get_recent_session(experiment_id=experiment, identifier=identifier, limit=5)

                if sessions:
                    # Get the most recent session
                    most_recent = sessions[0]
                    session_id = most_recent.get("external_id")

                    if session_id:
                        # Update the session in the nested data
                        pending_session["session_id"] = session_id
                        pending_session["status"] = "completed"
                        data_access.save_task(task)

            except OCSClientError as e:
                logger.error(f"Error fetching OCS sessions: {e}")

        data_access.close()

    # Return the AI sessions
    return JsonResponse({"success": True, "sessions": ai_sessions})


@login_required
@csrf_exempt
@require_POST
def task_add_ai_session(request, task_id):
    """Manually add OCS session ID to a task."""
    try:
        data_access = TaskDataAccess(user=request.user, request=request)
        task = data_access.get_task(task_id)
        if not task:
            return JsonResponse({"error": "Task not found"}, status=404)
    except Exception:
        return JsonResponse({"error": "Task not found"}, status=404)

    session_id = request.POST.get("session_id", "").strip()

    if not session_id:
        return JsonResponse({"success": False, "error": "Session ID is required"}, status=400)

    # Check if we already have an AI session
    existing_sessions = task.ai_sessions or []

    if existing_sessions:
        # Update the most recent session
        existing_sessions[-1]["session_id"] = session_id
        existing_sessions[-1]["status"] = "completed"
        created = False
    else:
        # Create new AI session
        task.add_ai_session(ocs_session_id=session_id, status="completed")
        created = True

    # Add event for AI conversation linked
    task.add_event(
        event_type="ai_linked",
        actor=request.user.username if hasattr(request.user, "username") else "system",
        actor_user_id=request.user.id if hasattr(request.user, "id") else 0,
        description=f"Linked OCS session: {session_id}",
    )

    # Save task via data access
    data_access.save_task(task)
    data_access.close()

    return JsonResponse({"success": True, "session_id": session_id, "created": created})


@login_required
def task_ai_transcript(request, task_id):
    """Fetch AI conversation transcript from OCS."""
    try:
        data_access = TaskDataAccess(user=request.user, request=request)
        task = data_access.get_task(task_id)
        data_access.close()
        if not task:
            return JsonResponse({"error": "Task not found"}, status=404)
    except Exception:
        return JsonResponse({"error": "Task not found"}, status=404)

    # Get AI sessions from nested data
    ai_sessions = task.ai_sessions or []

    if not ai_sessions:
        return JsonResponse({"success": False, "error": "No AI session found for this task"}, status=404)

    # Get the most recent session
    latest_session = ai_sessions[-1]
    session_id = latest_session.get("session_id")

    if not session_id:
        return JsonResponse({"success": False, "error": "No session ID available yet"}, status=404)

    # Fetch transcript from OCS
    try:
        transcript = get_transcript(session_id)

        # Transform OCS format to UI format
        if isinstance(transcript, dict) and transcript.get("messages"):
            formatted_messages = []
            for msg in transcript["messages"]:
                formatted_messages.append(
                    {
                        "actor": "AI Assistant" if msg.get("role") == "assistant" else task.username,
                        "message": msg.get("content", ""),
                        "timestamp": msg.get("created_at", ""),
                    }
                )

            return JsonResponse({"success": True, "messages": formatted_messages, "session_id": session_id})
        else:
            return JsonResponse({"success": False, "error": "Invalid transcript format from OCS"}, status=500)

    except OCSClientError as e:
        logger.error(f"Error fetching transcript from OCS: {e}")
        return JsonResponse({"success": False, "error": f"Failed to fetch transcript: {str(e)}"}, status=500)
