"""
Views for Pydantic AI demo.
"""
import logging
import uuid

from celery.result import AsyncResult
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from commcare_connect.utils.celery import CELERY_TASK_SUCCESS, get_task_progress_message

from .session_store import get_message_history
from .tasks import simple_echo_task

logger = logging.getLogger(__name__)


@login_required
def ai_demo_view(request):
    """
    Main view for the Pydantic AI demo.
    Shows a form where users can enter a prompt.
    """
    return render(request, "ai/ai_demo.html")


@login_required
@require_POST
def ai_demo_submit(request):
    """
    Submit a prompt and trigger a Celery task.
    Returns the task ID for polling.
    """
    prompt = request.POST.get("prompt", "").strip()
    session_id = request.POST.get("session_id", "").strip()

    if not prompt:
        return JsonResponse({"error": "Prompt is required"}, status=400)

    # Validate session_id format if provided
    if session_id:
        try:
            uuid.UUID(session_id)
        except ValueError:
            logger.warning(f"Invalid session_id format: {session_id}")
            session_id = None

    # Trigger the Celery task with prompt and session_id
    # The task will retrieve history itself
    result = simple_echo_task.delay(prompt, session_id=session_id)

    return JsonResponse(
        {
            "success": True,
            "task_id": result.id,
            "session_id": session_id,
        }
    )


@login_required
@require_GET
def ai_demo_status(request):
    """
    Check the status of a Celery task.
    Returns task status and result when complete.
    """
    task_id = request.GET.get("task_id")

    if not task_id:
        return JsonResponse({"error": "task_id is required"}, status=400)

    try:
        task = AsyncResult(task_id)
        task_meta = task._get_task_meta()
        status = task_meta.get("status")

        response_data = {
            "status": status,
            "complete": status == CELERY_TASK_SUCCESS,
            "message": get_task_progress_message(task),
        }

        # If task is complete, include the result
        if status == CELERY_TASK_SUCCESS:
            task_result = task.result
            response_data["result"] = task_result
        elif status == "FAILURE":
            response_data["error"] = str(task.result) if hasattr(task, "result") else str(task_meta.get("result"))

        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"Error checking task status: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_GET
def ai_demo_history(request):
    """
    Retrieve message history for a session.
    Returns the full conversation history.
    """
    session_id = request.GET.get("session_id", "").strip()

    if not session_id:
        return JsonResponse({"error": "session_id is required"}, status=400)

    # Validate session_id format
    try:
        uuid.UUID(session_id)
    except ValueError:
        return JsonResponse({"error": "Invalid session_id format"}, status=400)

    try:
        message_history = get_message_history(session_id)
        return JsonResponse(
            {
                "success": True,
                "session_id": session_id,
                "messages": message_history,
            }
        )
    except Exception as e:
        logger.error(f"Error retrieving history for session {session_id}: {e}")
        return JsonResponse({"error": str(e)}, status=500)
