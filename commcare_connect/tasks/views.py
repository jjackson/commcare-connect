from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from commcare_connect.tasks.forms import TaskCommentForm, TaskCreateForm, TaskQuickUpdateForm, TaskUpdateForm
from commcare_connect.tasks.helpers import get_user_tasks_queryset, user_can_access_task
from commcare_connect.tasks.models import Task, TaskAISession, TaskEvent, TaskEventType
from commcare_connect.tasks.ocs_client import OCSClientError, get_transcript, trigger_bot


class TaskAccessMixin(UserPassesTestMixin):
    """Mixin to check if user can access a task."""

    def test_func(self):
        task = self.get_object()
        return user_can_access_task(self.request.user, task)


class TaskListView(LoginRequiredMixin, ListView):
    """List view for tasks with filtering and statistics."""

    model = Task
    template_name = "tasks/tasks_list.html"
    context_object_name = "tasks"
    paginate_by = 50

    def get_queryset(self):
        """Get tasks the user can access with filtering."""
        queryset = get_user_tasks_queryset(self.request.user)

        # Apply filters from GET parameters
        status_filter = self.request.GET.get("status")
        if status_filter and status_filter != "all":
            queryset = queryset.filter(status=status_filter)

        action_type_filter = self.request.GET.get("action_type")
        if action_type_filter and action_type_filter != "all":
            queryset = queryset.filter(task_type=action_type_filter)

        search_query = self.request.GET.get("search")
        if search_query:
            queryset = queryset.filter(
                Q(user__name__icontains=search_query)
                | Q(user__email__icontains=search_query)
                | Q(title__icontains=search_query)
                | Q(description__icontains=search_query)
            )

        # Optimize queries
        queryset = queryset.select_related("user", "opportunity", "assigned_to")

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get all tasks for stats (before filtering)
        all_tasks = get_user_tasks_queryset(self.request.user)

        # Calculate statistics
        stats = {
            "total": all_tasks.count(),
            "unassigned": all_tasks.filter(status="unassigned").count(),
            "network_manager": all_tasks.filter(status="network_manager").count(),
            "program_manager": all_tasks.filter(status="program_manager").count(),
            "action_underway": all_tasks.filter(status="action_underway").count(),
            "resolved": all_tasks.filter(status="resolved").count(),
        }

        # Get unique values for filter dropdowns
        statuses = Task._meta.get_field("status").choices
        action_types = Task._meta.get_field("task_type").choices

        context.update(
            {
                "stats": stats,
                "statuses": [choice[0] for choice in statuses],
                "action_types": [choice[0] for choice in action_types],
                "selected_status": self.request.GET.get("status", "all"),
                "selected_action_type": self.request.GET.get("action_type", "all"),
            }
        )

        return context


class TaskDetailView(LoginRequiredMixin, TaskAccessMixin, DetailView):
    """Detail view for a single task."""

    model = Task
    template_name = "tasks/task_detail_streamlined.html"
    context_object_name = "task"
    pk_url_kwarg = "task_id"

    def get_queryset(self):
        """Optimize query with related objects."""
        return (
            Task.objects.select_related("user", "opportunity", "assigned_to", "created_by_user")
            .prefetch_related("events", "comments__author", "ai_sessions")
            .all()
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        task = self.object

        # Prepare timeline data (events and comments combined)
        timeline = []

        # Add events to timeline
        for event in task.events.all():
            timeline_item = {
                "timestamp": event.date_created,
                "actor": event.actor,
                "action": event.get_event_type_display(),
                "description": event.description,
                "icon": self._get_event_icon(event.event_type),
                "color": self._get_event_color(event.event_type),
                "display_name": event.actor,
                "type": "event",
            }

            # Add role badge if actor is PM or NM
            if event.actor_user:
                if hasattr(event.actor_user, "memberships"):
                    memberships = event.actor_user.memberships.all()
                    for membership in memberships:
                        if membership.is_admin:
                            if membership.is_program_manager:
                                timeline_item["actor_role"] = "program_manager"
                                break
                            else:
                                timeline_item["actor_role"] = "network_manager"
                                break

            # If this is an AI conversation event, include session info
            if event.event_type == TaskEventType.AI_CONVERSATION:
                ai_session = task.ai_sessions.first()  # Get the most recent AI session
                if ai_session:
                    timeline_item["session_id"] = ai_session.ocs_session_id
                    timeline_item["session_status"] = ai_session.status
                    # Include cached conversation if available
                    if ai_session.session_metadata and "conversation" in ai_session.session_metadata:
                        timeline_item["conversation"] = ai_session.session_metadata["conversation"]

            timeline.append(timeline_item)

        # Add comments to timeline
        for comment in task.comments.all():
            comment_item = {
                "timestamp": comment.date_created,
                "actor": comment.author.name,
                "action": "Commented",
                "description": comment.content,
                "icon": "fa-comment",
                "color": "gray",
                "display_name": comment.author.name,
                "type": "comment",
            }

            # Add role badge if commenter is PM or NM
            if hasattr(comment.author, "memberships"):
                memberships = comment.author.memberships.all()
                for membership in memberships:
                    if membership.is_admin:
                        if membership.is_program_manager:
                            comment_item["actor_role"] = "program_manager"
                            break
                        else:
                            comment_item["actor_role"] = "network_manager"
                            break

            timeline.append(comment_item)

        # Sort timeline by timestamp (newest first)
        timeline.sort(key=lambda x: x["timestamp"], reverse=True)

        # Get FLW history (past tasks for the same user)
        flw_history = (
            Task.objects.filter(user=task.user)
            .exclude(id=task.id)
            .order_by("-date_created")[:5]
            .values("id", "date_created", "task_type", "status", "title")
        )

        context.update(
            {
                "task": {
                    **task.__dict__,
                    "flw_name": task.user.name,
                    "flw_username": task.user.email,
                    "opportunity": task.opportunity.name,
                    "action_type": task.task_type,
                    "created": task.date_created,
                    "timeline": timeline,
                    "flw_history": list(flw_history),
                },
                "comment_form": TaskCommentForm(),
                "update_form": TaskUpdateForm(instance=task),
            }
        )

        return context

    def _get_event_icon(self, event_type):
        """Get FontAwesome icon for event type."""
        icon_map = {
            "created": "fa-plus-circle",
            "status_changed": "fa-exchange-alt",
            "assigned": "fa-user-check",
            "commented": "fa-comment",
            "learning_assigned": "fa-graduation-cap",
            "learning_completed": "fa-check-circle",
            "ai_conversation": "fa-robot",
            "notification_sent": "fa-envelope",
            "flw_acknowledged": "fa-check",
            "pattern_detected": "fa-exclamation-circle",
        }
        return icon_map.get(event_type, "fa-circle")

    def _get_event_color(self, event_type):
        """Get color for event type."""
        color_map = {
            "created": "blue",
            "status_changed": "purple",
            "assigned": "indigo",
            "commented": "gray",
            "learning_assigned": "blue",
            "learning_completed": "green",
            "ai_conversation": "green",
            "notification_sent": "green",
            "flw_acknowledged": "green",
            "pattern_detected": "red",
        }
        return color_map.get(event_type, "gray")


class TaskCreateView(LoginRequiredMixin, CreateView):
    """Create a new task."""

    model = Task
    form_class = TaskCreateForm
    template_name = "tasks/task_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        # Set created_by_user
        form.instance.created_by_user = self.request.user
        form.instance.created_by = self.request.user.email
        form.instance.modified_by = self.request.user.email

        response = super().form_valid(form)

        # Create initial event
        TaskEvent.objects.create(
            task=self.object,
            event_type=TaskEventType.CREATED,
            actor=self.request.user.name,
            actor_user=self.request.user,
            description=f"Task created by {self.request.user.name}",
            created_by=self.request.user.email,
            modified_by=self.request.user.email,
        )

        messages.success(self.request, f"Task #{self.object.id} created successfully.")
        return response

    def get_success_url(self):
        return reverse("tasks:detail", kwargs={"task_id": self.object.id})


class TaskUpdateView(LoginRequiredMixin, TaskAccessMixin, UpdateView):
    """Update an existing task."""

    model = Task
    form_class = TaskUpdateForm
    template_name = "tasks/task_form.html"
    pk_url_kwarg = "task_id"

    def form_valid(self, form):
        # Track what changed
        changes = []
        old_instance = Task.objects.get(pk=self.object.pk)

        if old_instance.status != form.instance.status:
            changes.append(
                f"Status changed from {old_instance.get_status_display()} to {form.instance.get_status_display()}"
            )

        if old_instance.priority != form.instance.priority:
            old_priority = old_instance.get_priority_display()
            new_priority = form.instance.get_priority_display()
            changes.append(f"Priority changed from {old_priority} to {new_priority}")

        if old_instance.assigned_to != form.instance.assigned_to:
            old_name = old_instance.assigned_to.name if old_instance.assigned_to else "Unassigned"
            new_name = form.instance.assigned_to.name if form.instance.assigned_to else "Unassigned"
            changes.append(f"Assigned to changed from {old_name} to {new_name}")

        form.instance.modified_by = self.request.user.email
        response = super().form_valid(form)

        # Create events for changes
        for change in changes:
            TaskEvent.objects.create(
                task=self.object,
                event_type=TaskEventType.STATUS_CHANGED if "Status" in change else TaskEventType.ASSIGNED,
                actor=self.request.user.name,
                actor_user=self.request.user,
                description=change,
                created_by=self.request.user.email,
                modified_by=self.request.user.email,
            )

        messages.success(self.request, "Task updated successfully.")
        return response

    def get_success_url(self):
        return reverse("tasks:detail", kwargs={"task_id": self.object.id})


@login_required
@require_POST
def task_add_comment(request, task_id):
    """Add a comment to a task."""
    task = get_object_or_404(Task, id=task_id)

    if not user_can_access_task(request.user, task):
        return JsonResponse({"error": "Access denied"}, status=403)

    form = TaskCommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.task = task
        comment.author = request.user
        comment.created_by = request.user.email
        comment.modified_by = request.user.email
        comment.save()

        # Create event
        TaskEvent.objects.create(
            task=task,
            event_type=TaskEventType.COMMENTED,
            actor=request.user.name,
            actor_user=request.user,
            description=comment.content,
            created_by=request.user.email,
            modified_by=request.user.email,
        )

        # Return JSON for AJAX
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "success": True,
                    "comment": {
                        "id": comment.id,
                        "author": comment.author.name,
                        "content": comment.content,
                        "date": comment.date_created.isoformat(),
                    },
                }
            )

        messages.success(request, "Comment added successfully.")
        return redirect("tasks:detail", task_id=task_id)

    return JsonResponse({"error": "Invalid form data"}, status=400)


@login_required
@csrf_exempt
@require_POST
def task_initiate_ai(request, task_id):
    """Initiate an AI assistant conversation for a task."""
    task = get_object_or_404(Task, id=task_id)

    if not user_can_access_task(request.user, task):
        return JsonResponse({"error": "Access denied"}, status=403)

    try:
        # Parse request body
        import json

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
            "opportunity_id": str(task.opportunity.id),
            "opportunity_name": task.opportunity.name,
            "flw_user_id": str(task.user.id),
            "flw_name": task.user.name,
            "created_by": request.user.email,
        }

        # Trigger bot with OCS using manual parameters
        trigger_bot(
            identifier=identifier,
            platform=platform,
            bot_id=experiment,
            prompt_text=prompt_text,
            start_new_session=start_new_session,
            session_data=session_data,
        )

        # The OCS API returns empty on success, so we need to query for the session
        # For now, we'll create the session record without a session_id
        # The user will need to manually link it later
        TaskAISession.objects.create(
            task=task,
            ocs_session_id="",  # Will be filled in later manually
            status="initiated",
            session_metadata={
                "parameters": {
                    "identifier": identifier,
                    "experiment": experiment,
                    "platform": platform,
                    "prompt_text": prompt_text,
                    "start_new_session": start_new_session,
                },
                "session_data": session_data,
            },
            created_by=request.user.email,
            modified_by=request.user.email,
        )

        # Create event
        TaskEvent.objects.create(
            task=task,
            event_type=TaskEventType.AI_CONVERSATION,
            actor=request.user.name,
            actor_user=request.user,
            description=f"AI assistant conversation initiated (Platform: {platform}, Bot: {experiment})",
            created_by=request.user.email,
            modified_by=request.user.email,
            metadata={
                "platform": platform,
                "bot_id": experiment,
                "identifier": identifier,
            },
        )

        message = "AI conversation initiated successfully. You can manually link the session ID once available."
        return JsonResponse({"success": True, "message": message})

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON in request body"}, status=400)
    except OCSClientError as e:
        return JsonResponse({"error": f"OCS API error: {str(e)}"}, status=500)
    except Exception as e:
        return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)


@login_required
@csrf_exempt
@require_POST
def task_add_ai_session(request, task_id):
    """Manually add OCS session ID to a task."""
    task = get_object_or_404(Task, id=task_id)

    if not user_can_access_task(request.user, task):
        return JsonResponse({"error": "Access denied"}, status=403)

    session_id = request.POST.get("session_id", "").strip()

    if not session_id:
        return JsonResponse({"success": False, "error": "Session ID is required"}, status=400)

    # Create or update AI session
    ai_session, created = TaskAISession.objects.update_or_create(
        task=task,
        defaults={
            "ocs_session_id": session_id,
            "status": "completed",
            "created_by": request.user.email,
            "modified_by": request.user.email,
        },
    )

    # Update existing AI conversation event with session ID, or create new one
    ai_event = task.events.filter(event_type=TaskEventType.AI_CONVERSATION).first()
    if ai_event:
        # Update existing event with session ID info
        ai_event.description = f"{ai_event.description} (Session: {session_id})"
        ai_event.modified_by = request.user.email
        ai_event.save(update_fields=["description", "modified_by", "date_modified"])
    else:
        # Create new event if none exists
        TaskEvent.objects.create(
            task=task,
            event_type=TaskEventType.AI_CONVERSATION,
            actor=request.user.name,
            description=f"AI assistant session linked: {session_id}",
            created_by=request.user.email,
            modified_by=request.user.email,
        )

    return JsonResponse({"success": True, "session_id": session_id, "created": created})


@login_required
def task_ai_transcript(request, task_id):
    """Fetch AI conversation transcript from OCS."""
    task = get_object_or_404(Task, id=task_id)

    if not user_can_access_task(request.user, task):
        return JsonResponse({"error": "Access denied"}, status=403)

    # Get AI session for this task
    ai_session = task.ai_sessions.first()

    if not ai_session:
        return JsonResponse({"success": False, "error": "No AI session found for this task"}, status=404)

    # Check if we have cached conversation
    if ai_session.session_metadata and "conversation" in ai_session.session_metadata:
        # Transform OCS format to UI format
        messages = []
        for msg in ai_session.session_metadata["conversation"]:
            messages.append(
                {
                    "actor": "AI Assistant" if msg.get("role") == "assistant" else task.user.name,
                    "message": msg.get("content", ""),
                    "timestamp": msg.get("created_at", ""),
                }
            )

        return JsonResponse(
            {"success": True, "session_id": ai_session.ocs_session_id, "messages": messages, "cached": True}
        )

    # Fetch from OCS
    try:
        transcript = get_transcript(ai_session.ocs_session_id)

        # Cache the conversation if successful
        if isinstance(transcript, dict) and transcript.get("messages"):
            ai_session.session_metadata = {"conversation": transcript["messages"]}
            ai_session.save(update_fields=["session_metadata"])

            # Transform OCS format to UI format
            messages = []
            for msg in transcript["messages"]:
                messages.append(
                    {
                        "actor": "AI Assistant" if msg.get("role") == "assistant" else task.user.name,
                        "message": msg.get("content", ""),
                        "timestamp": msg.get("created_at", ""),
                    }
                )

            return JsonResponse(
                {"success": True, "session_id": ai_session.ocs_session_id, "messages": messages, "cached": False}
            )
        else:
            return JsonResponse(
                {
                    "success": True,
                    "session_id": ai_session.ocs_session_id,
                    "transcript": transcript,
                }
            )

    except OCSClientError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@require_POST
def task_quick_update(request, task_id):
    """Quick update for status/assignment via AJAX."""
    task = get_object_or_404(Task, id=task_id)

    if not user_can_access_task(request.user, task):
        return JsonResponse({"error": "Access denied"}, status=403)

    form = TaskQuickUpdateForm(request.POST)
    if form.is_valid():
        changes = []

        if form.cleaned_data.get("status"):
            old_status = task.status
            task.status = form.cleaned_data["status"]
            if old_status != task.status:
                changes.append(f"Status changed to {task.get_status_display()}")

        if form.cleaned_data.get("priority"):
            old_priority = task.priority
            task.priority = form.cleaned_data["priority"]
            if old_priority != task.priority:
                changes.append(f"Priority changed to {task.get_priority_display()}")

        if form.cleaned_data.get("assigned_to"):
            old_assigned = task.assigned_to
            task.assigned_to = form.cleaned_data["assigned_to"]
            if old_assigned != task.assigned_to:
                changes.append(f"Assigned to {task.assigned_to.name}")

        task.modified_by = request.user.email
        task.save()

        # Create events
        for change in changes:
            TaskEvent.objects.create(
                task=task,
                event_type=TaskEventType.STATUS_CHANGED,
                actor=request.user.name,
                actor_user=request.user,
                description=change,
                created_by=request.user.email,
                modified_by=request.user.email,
            )

        return JsonResponse({"success": True, "changes": changes})

    return JsonResponse({"error": "Invalid form data"}, status=400)


# Database management API views
class DatabaseStatsAPIView(LoginRequiredMixin, View):
    """API endpoint for getting database statistics."""

    def get(self, request):
        from commcare_connect.tasks.database_manager import get_database_stats

        try:
            stats = get_database_stats()
            return JsonResponse({"success": True, "stats": stats})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


@method_decorator(csrf_exempt, name="dispatch")
class DatabaseResetAPIView(LoginRequiredMixin, View):
    """API endpoint for resetting tasks-related database tables."""

    def post(self, request):
        from commcare_connect.tasks.database_manager import reset_tasks_database

        try:
            deleted = reset_tasks_database()
            return JsonResponse({"success": True, "deleted": deleted})
        except Exception as e:
            import traceback

            return JsonResponse({"error": str(e), "traceback": traceback.format_exc()}, status=500)


# Keep the old view names for backward compatibility during transition
tasks_list = TaskListView.as_view()
task_detail_streamlined = TaskDetailView.as_view()
