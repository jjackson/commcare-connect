"""
Task views using ExperimentRecord-based TaskRecord model.

These views replace the old Django ORM-based views with ExperimentRecord-backed
implementation using TaskDataAccess for OAuth-based API access.
"""

import json
import logging
from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView, TemplateView

from commcare_connect.tasks.data_access import TaskDataAccess
from commcare_connect.tasks.experiment_models import TaskRecord
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
        data_access = TaskDataAccess(user=self.request.user, request=self.request)

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
            # Search in title and description (JSON fields)
            queryset = queryset.filter(
                Q(data__title__icontains=search_query) | Q(data__description__icontains=search_query)
            )

        return queryset.order_by("-date_created")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        data_access = TaskDataAccess(user=self.request.user, request=self.request)
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

        # Get FLW history (past tasks for the same user)
        data_access = TaskDataAccess(user=self.request.user, request=self.request)
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


# API Views


class OpportunitySearchAPIView(LoginRequiredMixin, View):
    """API endpoint for searching opportunities via ConnectAPIFacade."""

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


class OpportunityFieldWorkersAPIView(LoginRequiredMixin, View):
    """API endpoint for getting field workers for an opportunity."""

    def get(self, request, opportunity_id):
        try:
            data_access = TaskDataAccess(user=request.user, request=request)
            field_workers = data_access.get_field_workers(opportunity_id)
            data_access.close()

            return JsonResponse({"success": True, "field_workers": field_workers})

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


@method_decorator(csrf_exempt, name="dispatch")
class TaskCreateAPIView(LoginRequiredMixin, View):
    """API endpoint for bulk task creation."""

    def post(self, request):
        try:
            data = json.loads(request.body)

            # Extract parameters
            opportunity_id = data.get("opportunity_id")
            flw_ids = data.get("flw_ids", [])
            task_type = data.get("task_type", "warning")
            priority = data.get("priority", "medium")
            title = data.get("title", "")
            description = data.get("description", "")
            learning_assignment_text = data.get("learning_assignment_text", "")
            assigned_to_id = data.get("assigned_to_id")

            # Validate required fields
            if not opportunity_id:
                return JsonResponse({"error": "Opportunity ID is required"}, status=400)

            if not flw_ids:
                return JsonResponse({"error": "At least one FLW must be selected"}, status=400)

            if not title:
                return JsonResponse({"error": "Title is required"}, status=400)

            # Create tasks
            data_access = TaskDataAccess(user=request.user, request=request)
            created_tasks = []
            errors = []

            for flw_id in flw_ids:
                try:
                    # Determine creator name
                    creator_name = request.user.username
                    if hasattr(request.user, "get_full_name"):
                        full_name = request.user.get_full_name()
                        if full_name:
                            creator_name = full_name

                    task = data_access.create_task(
                        user_id=int(flw_id),
                        opportunity_id=int(opportunity_id),
                        created_by_id=request.user.id,
                        task_type=task_type,
                        priority=priority,
                        title=title,
                        description=description,
                        learning_assignment_text=learning_assignment_text,
                        assigned_to_id=assigned_to_id,
                        creator_name=creator_name,
                    )

                    created_tasks.append({"id": task.id, "user_id": flw_id})

                except Exception as e:
                    errors.append(f"Error creating task for user {flw_id}: {str(e)}")

            data_access.close()

            return JsonResponse(
                {"success": True, "created_count": len(created_tasks), "tasks": created_tasks, "errors": errors}
            )

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON in request body"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


@method_decorator(csrf_exempt, name="dispatch")
class TaskUpdateAPIView(LoginRequiredMixin, View):
    """API endpoint for quick update (status/assignment)."""

    def post(self, request, task_id):
        try:
            data_access = TaskDataAccess(user=request.user, request=request)
            task = data_access.get_task(task_id)

            if not task:
                return JsonResponse({"error": "Task not found"}, status=404)

            # Parse update data
            update_data = json.loads(request.body) if request.body else request.POST.dict()

            changes = []
            actor_name = request.user.username if hasattr(request.user, "username") else "User"

            # Update status
            if "status" in update_data and update_data["status"]:
                data_access.update_status(task, update_data["status"], actor_name, request.user.id)
                changes.append(f"Status changed to {update_data['status']}")

            # Update priority
            if "priority" in update_data and update_data["priority"]:
                task.data["priority"] = update_data["priority"]
                task.save()
                changes.append(f"Priority changed to {update_data['priority']}")

            # Update assignment
            if "assigned_to" in update_data:
                assigned_to_id = int(update_data["assigned_to"]) if update_data["assigned_to"] else None
                data_access.assign_task(task, assigned_to_id, actor_name, request.user.id)
                changes.append("Assignment updated")

            data_access.close()

            return JsonResponse({"success": True, "changes": changes})

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


@login_required
@csrf_exempt
@require_POST
def task_add_comment(request, task_id):
    """Add a comment to a task."""
    try:
        data_access = TaskDataAccess(user=request.user, request=request)
        task = data_access.get_task(task_id)

        if not task:
            return JsonResponse({"error": "Task not found"}, status=404)

        # Parse comment data
        if request.content_type == "application/json":
            data = json.loads(request.body)
            content = data.get("content", "")
        else:
            content = request.POST.get("content", "")

        if not content:
            return JsonResponse({"error": "Comment content is required"}, status=400)

        # Get author name
        author_name = request.user.username
        if hasattr(request.user, "get_full_name"):
            full_name = request.user.get_full_name()
            if full_name:
                author_name = full_name

        # Add comment
        data_access.add_comment(task, request.user.id, author_name, content)

        # Also add event for commented action
        data_access.add_event(
            task,
            event_type="commented",
            actor=author_name,
            actor_user_id=request.user.id,
            description=content,
        )

        data_access.close()

        # Return JSON for AJAX
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "success": True,
                    "comment": {
                        "author": author_name,
                        "content": content,
                        "timestamp": datetime.now().isoformat(),
                    },
                }
            )

        messages.success(request, "Comment added successfully.")
        return redirect("tasks:detail", task_id=task_id)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@csrf_exempt
@require_POST
def task_initiate_ai(request, task_id):
    """Initiate an AI assistant conversation for a task."""
    try:
        data_access = TaskDataAccess(user=request.user, request=request)
        task = data_access.get_task(task_id)

        if not task:
            return JsonResponse({"error": "Task not found"}, status=404)

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

        # Prepare session data
        session_data = {
            "task_id": str(task.id),
            "task_type": task.task_type,
            "opportunity_id": str(task.opportunity_id),
            "flw_user_id": str(task.user_id),
            "created_by": request.user.username,
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

        # Add AI session to task (session_id will be populated later via polling)
        actor_name = request.user.username
        if hasattr(request.user, "get_full_name"):
            full_name = request.user.get_full_name()
            if full_name:
                actor_name = full_name

        data_access.add_ai_session(
            task,
            ocs_session_id=None,  # Will be populated later
            status="pending",
            metadata={
                "parameters": {
                    "identifier": identifier,
                    "experiment": experiment,
                    "platform": platform,
                    "prompt_text": prompt_text,
                    "start_new_session": start_new_session,
                },
                "session_data": session_data,
            },
        )

        # Add event
        data_access.add_event(
            task,
            event_type="ai_conversation",
            actor=actor_name,
            actor_user_id=request.user.id,
            description=f"AI assistant conversation initiated (Platform: {platform}, Bot: {experiment})",
            metadata={
                "platform": platform,
                "bot_id": experiment,
                "identifier": identifier,
            },
        )

        data_access.close()

        return JsonResponse(
            {
                "success": True,
                "message": "AI conversation initiated successfully.",
                "session_id": None,
            }
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON in request body"}, status=400)
    except OCSClientError as e:
        return JsonResponse({"error": f"OCS API error: {str(e)}"}, status=500)
    except Exception as e:
        return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)


@login_required
def task_ai_sessions(request, task_id):
    """Get AI sessions for a task."""
    try:
        data_access = TaskDataAccess(user=request.user, request=request)
        task = data_access.get_task(task_id)

        if not task:
            return JsonResponse({"error": "Task not found"}, status=404)

        # Get AI sessions from task
        sessions = task.ai_sessions

        # Try to populate session_id from OCS for pending sessions
        for session in sessions:
            if not session.get("ocs_session_id") and session.get("metadata"):
                params = session["metadata"].get("parameters", {})
                experiment = params.get("experiment")
                identifier = params.get("identifier")

                if experiment and identifier:
                    try:
                        recent_sessions = get_recent_session(experiment_id=experiment, identifier=identifier, limit=5)

                        if recent_sessions:
                            # Match by timestamp
                            session_timestamp = datetime.fromisoformat(session["timestamp"].replace("Z", "+00:00"))

                            for ocs_session in recent_sessions:
                                ocs_created_str = ocs_session.get("created_at", "")
                                if ocs_created_str:
                                    ocs_created = datetime.fromisoformat(ocs_created_str.replace("Z", "+00:00"))
                                    time_diff = (ocs_created - session_timestamp).total_seconds()

                                    if -5 <= time_diff <= 30:
                                        session["ocs_session_id"] = ocs_session.get("id")
                                        session["status"] = "initiated"
                                        # Save back to task
                                        task.save()
                                        break
                    except Exception as e:
                        logger.warning(f"Could not fetch session from OCS: {e}")

        data_access.close()

        return JsonResponse({"success": True, "sessions": sessions})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def task_ai_transcript(request, task_id):
    """Fetch AI conversation transcript from OCS."""
    try:
        data_access = TaskDataAccess(user=request.user, request=request)
        task = data_access.get_task(task_id)

        if not task:
            return JsonResponse({"error": "Task not found"}, status=404)

        # Get first AI session with OCS session ID
        ai_sessions = task.ai_sessions
        ocs_session_id = None

        for session in ai_sessions:
            if session.get("ocs_session_id"):
                ocs_session_id = session["ocs_session_id"]
                break

        if not ocs_session_id:
            return JsonResponse({"success": False, "error": "No session ID available yet"}, status=404)

        # Fetch transcript from OCS
        transcript = get_transcript(ocs_session_id)

        # Transform to UI format
        if isinstance(transcript, dict) and transcript.get("messages"):
            messages_list = []
            for msg in transcript["messages"]:
                messages_list.append(
                    {
                        "actor": "AI Assistant" if msg.get("role") == "assistant" else f"User {task.user_id}",
                        "message": msg.get("content", ""),
                        "timestamp": msg.get("created_at", ""),
                    }
                )

            data_access.close()
            return JsonResponse({"success": True, "session_id": ocs_session_id, "messages": messages_list})
        else:
            data_access.close()
            return JsonResponse({"success": True, "session_id": ocs_session_id, "transcript": transcript})

    except OCSClientError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# Database Management Views


class DatabaseStatsAPIView(LoginRequiredMixin, View):
    """API endpoint for getting database statistics."""

    def get(self, request):
        try:
            from commcare_connect.labs.models import ExperimentRecord

            stats = {
                "tasks": ExperimentRecord.objects.filter(experiment="tasks", type="Task").count(),
                "events": 0,  # Events are nested in task JSON
                "comments": 0,  # Comments are nested in task JSON
                "ai_sessions": 0,  # AI sessions are nested in task JSON
            }

            # Count nested items
            tasks = ExperimentRecord.objects.filter(experiment="tasks", type="Task")
            for task in tasks:
                stats["events"] += len(task.data.get("events", []))
                stats["comments"] += len(task.data.get("comments", []))
                stats["ai_sessions"] += len(task.data.get("ai_sessions", []))

            return JsonResponse({"success": True, "stats": stats})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


@method_decorator(csrf_exempt, name="dispatch")
class DatabaseResetAPIView(LoginRequiredMixin, View):
    """API endpoint for resetting tasks-related database tables."""

    def post(self, request):
        try:
            from commcare_connect.labs.models import ExperimentRecord

            # Delete all task experiment records
            deleted = ExperimentRecord.objects.filter(experiment="tasks").delete()

            return JsonResponse({"success": True, "deleted": deleted})
        except Exception as e:
            import traceback

            return JsonResponse({"error": str(e), "traceback": traceback.format_exc()}, status=500)
