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

from commcare_connect.labs.config import LABS_DEFAULT_OPPORTUNITY_ID
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
        data_access = TaskDataAccess(
            opportunity_id=LABS_DEFAULT_OPPORTUNITY_ID, user=self.request.user, request=self.request
        )

        # Get all tasks (OAuth enforces access)
        queryset = data_access.get_tasks()

        # Apply filters from GET parameters
        status_filter = self.request.GET.get("status")
        if status_filter and status_filter != "all":
            queryset = queryset.filter(data__status=status_filter)

        action_type_filter = self.request.GET.get("action_type")
        if action_type_filter and action_type_filter != "all":
            queryset = queryset.filter(data__task_type=action_type_filter)

        search_query = self.request.GET.get("search")
        if search_query:
            # Search in title (JSON field)
            queryset = queryset.filter(data__title__icontains=search_query)

        return queryset.order_by("-date_created")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        data_access = TaskDataAccess(
            opportunity_id=LABS_DEFAULT_OPPORTUNITY_ID, user=self.request.user, request=self.request
        )
        all_tasks = data_access.get_tasks()

        # Calculate statistics
        stats = {
            "total": all_tasks.count(),
            "unassigned": all_tasks.filter(data__status="unassigned").count(),
            "network_manager": all_tasks.filter(data__status="network_manager").count(),
            "program_manager": all_tasks.filter(data__status="program_manager").count(),
            "action_underway": all_tasks.filter(data__status="action_underway").count(),
            "resolved": all_tasks.filter(data__status="resolved").count(),
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
        data_access = TaskDataAccess(
            opportunity_id=LABS_DEFAULT_OPPORTUNITY_ID, user=self.request.user, request=self.request
        )
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

        # Get FLW history (past tasks for the same user)
        data_access = TaskDataAccess(
            opportunity_id=LABS_DEFAULT_OPPORTUNITY_ID, user=self.request.user, request=self.request
        )
        flw_history = (
            data_access.get_tasks(user_id=task.user_id)
            .exclude(id=task.id)
            .order_by("-date_created")[:5]
            .values("id", "date_created", "data")
        )

        # Format history for template
        formatted_history = []
        for hist in flw_history:
            formatted_history.append(
                {
                    "id": hist["id"],
                    "date_created": hist["date_created"],
                    "task_type": hist["data"].get("task_type"),
                    "status": hist["data"].get("status"),
                    "title": hist["data"].get("title"),
                }
            )

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
                    "date_created": task.date_created,
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
            data_access = TaskDataAccess(
                opportunity_id=LABS_DEFAULT_OPPORTUNITY_ID, user=request.user, request=request
            )
            opportunities = data_access.search_opportunities(query, limit)
            data_access.close()

            return JsonResponse({"success": True, "opportunities": opportunities})

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


class OpportunityWorkersAPIView(LoginRequiredMixin, View):
    """Get workers for an opportunity via Connect OAuth API."""

    def get(self, request, opportunity_id):
        try:
            data_access = TaskDataAccess(
                opportunity_id=LABS_DEFAULT_OPPORTUNITY_ID, user=request.user, request=request
            )
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


# AI Assistant Integration Views


@login_required
@csrf_exempt
@require_POST
def task_initiate_ai(request, task_id):
    """Initiate an AI assistant conversation for a task via OCS."""
    try:
        # Get the task using ExperimentRecord
        task = TaskRecord.objects.get(id=task_id, experiment="tasks")
    except TaskRecord.DoesNotExist:
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
            session_id=None,  # Will be populated later via manual linking
            status="pending",
            session_metadata={
                "parameters": {
                    "identifier": identifier,
                    "experiment": experiment,
                    "platform": platform,
                    "prompt_text": prompt_text,
                }
            },
        )
        task.save()

        # Add event for AI conversation initiation
        task.add_event(
            action="AI Conversation Initiated",
            actor=request.user.username if hasattr(request.user, "username") else "system",
            description=f"Triggered AI assistant for {identifier}",
        )
        task.save()

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
        task = TaskRecord.objects.get(id=task_id, experiment="tasks")
    except TaskRecord.DoesNotExist:
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
                        task.save()

            except OCSClientError as e:
                logger.error(f"Error fetching OCS sessions: {e}")

    # Return the AI sessions
    return JsonResponse({"success": True, "sessions": ai_sessions})


@login_required
@csrf_exempt
@require_POST
def task_add_ai_session(request, task_id):
    """Manually add OCS session ID to a task."""
    try:
        task = TaskRecord.objects.get(id=task_id, experiment="tasks")
    except TaskRecord.DoesNotExist:
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
        task.add_ai_session(session_id=session_id, status="completed")
        created = True

    task.save()

    # Add event for AI conversation linked
    task.add_event(
        action="AI Conversation Linked",
        actor=request.user.username if hasattr(request.user, "username") else "system",
        description=f"Linked OCS session: {session_id}",
    )
    task.save()

    return JsonResponse({"success": True, "session_id": session_id, "created": created})


@login_required
def task_ai_transcript(request, task_id):
    """Fetch AI conversation transcript from OCS."""
    try:
        task = TaskRecord.objects.get(id=task_id, experiment="tasks")
    except TaskRecord.DoesNotExist:
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
