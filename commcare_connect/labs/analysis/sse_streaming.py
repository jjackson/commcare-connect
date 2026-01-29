"""
Base classes and utilities for Server-Sent Events (SSE) streaming views.

Provides reusable infrastructure for streaming analysis progress to the frontend.
Includes support for both AnalysisPipeline streaming and Celery task progress streaming.
"""

import json
import logging
import time
from collections.abc import Callable, Generator

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, StreamingHttpResponse
from django.views import View

logger = logging.getLogger(__name__)

# Download progress interval - yield progress updates every 5MB
# This is used by backends to throttle download progress events
DOWNLOAD_PROGRESS_INTERVAL_BYTES = 5 * 1024 * 1024  # 5MB


def send_sse_event(message: str, data: dict | None = None, error: str | None = None) -> str:
    """
    Format a message as a Server-Sent Event.

    Args:
        message: Status message to display
        data: Optional data payload (signals completion if present)
        error: Optional error message

    Returns:
        Formatted SSE event string

    Example:
        >>> send_sse_event("Processing data...")
        'data: {"message": "Processing data...", "complete": false}\\n\\n'

        >>> send_sse_event("Complete", data={"count": 100})
        'data: {"message": "Complete", "complete": true, "data": {"count": 100}}\\n\\n'
    """
    event = {"message": message, "complete": data is not None}
    if data:
        event["data"] = data
    if error:
        event["error"] = error
    return f"data: {json.dumps(event)}\n\n"


class BaseSSEStreamView(LoginRequiredMixin, View):
    """
    Base view for Server-Sent Events (SSE) streaming endpoints.

    Provides common SSE setup, authentication, and error handling.
    Subclasses must implement stream_data() to yield SSE events.

    Features:
    - Automatic authentication check
    - Proper SSE headers (Cache-Control, X-Accel-Buffering)
    - StreamingHttpResponse setup
    - Error handling structure

    Example:
        class MyStreamView(BaseSSEStreamView):
            def stream_data(self, request) -> Generator[str, None, None]:
                yield send_sse_event("Starting...")
                # ... do work ...
                yield send_sse_event("Complete!", data={"result": 123})
    """

    def get(self, request):
        """
        Handle GET request and return streaming response.

        Returns:
            StreamingHttpResponse with text/event-stream content type
        """
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Not authenticated"}, status=401)

        response = StreamingHttpResponse(
            self.stream_data(request),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"  # Disable nginx buffering
        return response

    def stream_data(self, request) -> Generator[str, None, None]:
        """
        Generator that yields SSE events.

        Must be implemented by subclasses.
        Yield strings formatted with send_sse_event().

        Args:
            request: HttpRequest object

        Yields:
            Formatted SSE event strings

        Raises:
            NotImplementedError: If not implemented by subclass
        """
        raise NotImplementedError("Subclasses must implement stream_data()")


class AnalysisPipelineSSEMixin:
    """
    Mixin for SSE views that use AnalysisPipeline.

    Provides common pipeline streaming logic and event conversion.
    Converts AnalysisPipeline events to SSE format.

    Stores result and cache status as instance variables for easy access:
    - self._pipeline_result: The analysis result object
    - self._pipeline_from_cache: Whether the result came from cache

    Example:
        class MyStreamView(AnalysisPipelineSSEMixin, BaseSSEStreamView):
            def stream_data(self, request):
                pipeline = AnalysisPipeline(request)
                stream = pipeline.stream_analysis(config)

                # Stream all progress events as SSE
                yield from self.stream_pipeline_events(stream)

                # Result is now available in self._pipeline_result
                result = self._pipeline_result
                if result:
                    yield send_sse_event("Complete", data={"count": len(result.rows)})
    """

    def __init__(self, *args, **kwargs):
        """Initialize mixin state."""
        super().__init__(*args, **kwargs)
        self._pipeline_result = None
        self._pipeline_from_cache = False

    def stream_pipeline_events(
        self,
        pipeline_stream: Generator,
        send_sse_func: Callable[[str, dict | None, str | None], str] = send_sse_event,
    ) -> Generator[str, None, None]:
        """
        Convert AnalysisPipeline stream events to SSE events.

        Processes all pipeline events (STATUS, DOWNLOAD, RESULT) and yields
        formatted SSE events. Stores the final result in self._pipeline_result
        and cache status in self._pipeline_from_cache.

        Download progress events are yielded every ~5MB (configured by backends
        using DOWNLOAD_PROGRESS_INTERVAL_BYTES). Each download event is immediately
        converted to an SSE event for real-time UI updates.

        Args:
            pipeline_stream: Generator from pipeline.stream_analysis()
            send_sse_func: SSE formatting function (defaults to send_sse_event)

        Yields:
            Formatted SSE event strings

        Side Effects:
            Sets self._pipeline_result and self._pipeline_from_cache
        """
        from commcare_connect.labs.analysis.pipeline import EVENT_DOWNLOAD, EVENT_RESULT, EVENT_STATUS

        self._pipeline_result = None
        self._pipeline_from_cache = False

        for event_type, event_data in pipeline_stream:
            if event_type == EVENT_STATUS:
                message = event_data.get("message", "Processing...")
                self._pipeline_from_cache = self._pipeline_from_cache or "cache" in message.lower()
                logger.debug(f"[SSE Mixin] Status event: {message}")
                yield send_sse_func(message)

            elif event_type == EVENT_DOWNLOAD:
                # Download progress event - yield immediately for real-time UI updates
                # These events are generated every 5MB by the backend (see DOWNLOAD_PROGRESS_INTERVAL_BYTES)
                bytes_dl = event_data.get("bytes", 0)
                total_bytes = event_data.get("total", 0)
                if total_bytes > 0:
                    mb_dl = bytes_dl / (1024 * 1024)
                    mb_total = total_bytes / (1024 * 1024)
                    pct = int(bytes_dl / total_bytes * 100)
                    message = f"Downloading: {mb_dl:.1f} / {mb_total:.1f} MB ({pct}%)"
                else:
                    mb_dl = bytes_dl / (1024 * 1024)
                    message = f"Downloading: {mb_dl:.1f} MB..."
                logger.debug(f"[SSE Mixin] Download progress: {message}")
                yield send_sse_func(message)

            elif event_type == EVENT_RESULT:
                logger.debug("[SSE Mixin] Received result event")
                self._pipeline_result = event_data
                break


class CeleryTaskStreamView(BaseSSEStreamView):
    """
    Base view for streaming Celery task progress via SSE.

    Polls Celery task state and streams progress updates to the frontend.
    Subclasses must implement get_task_id() to extract the task ID from the request.

    Features:
    - Automatic Celery state polling
    - Standard progress data structure (status, message, stage_name, current_stage, etc.)
    - Configurable poll interval
    - Handles SUCCESS, FAILURE, PROGRESS, PENDING states

    Progress data structure:
    {
        "status": "running" | "pending" | "completed" | "failed",
        "message": "Human-readable progress message",
        "stage_name": "Current stage name",
        "current_stage": 1,
        "total_stages": 4,
        "processed": 50,  # Items processed in current stage
        "total": 100,     # Total items in current stage
        "result": {...},  # Only on completion
        "error": "...",   # Only on failure
    }

    Example:
        class MyTaskStreamView(CeleryTaskStreamView):
            def get_task_id(self, request) -> str:
                return self.kwargs.get("task_id")
    """

    poll_interval: float = 0.5  # Seconds between Celery state polls

    def get_task_id(self, request) -> str:
        """
        Extract the Celery task ID from the request.

        Must be implemented by subclasses.

        Args:
            request: HttpRequest object

        Returns:
            Celery task ID string

        Raises:
            NotImplementedError: If not implemented by subclass
        """
        raise NotImplementedError("Subclasses must implement get_task_id()")

    def build_progress_data(self, state: str, info: dict) -> dict:
        """
        Build standard progress data from Celery task state.

        Args:
            state: Celery task state (PENDING, PROGRESS, SUCCESS, FAILURE, etc.)
            info: Task info/meta dict from result.info

        Returns:
            Standard progress data dict
        """
        if state == "PENDING":
            return {
                "status": "pending",
                "message": "Waiting to start...",
            }
        elif state == "PROGRESS":
            return {
                "status": "running",
                "message": info.get("message", "Processing..."),
                "stage_name": info.get("stage_name", ""),
                "current_stage": info.get("current_stage", 1),
                "total_stages": info.get("total_stages", 4),
                "processed": info.get("processed", 0),
                "total": info.get("total", 0),
            }
        elif state == "SUCCESS":
            # When set_task_progress is called with is_complete=True, the result is nested
            # under info['result']. When the task returns naturally, info IS the result.
            if isinstance(info, dict):
                # Check for nested result from set_task_progress(is_complete=True)
                task_result = info.get("result", info)
            else:
                task_result = {}
            return {
                "status": "completed",
                "message": "Complete",
                "result": task_result,
            }
        elif state == "FAILURE":
            error_msg = str(info) if info else "Unknown error"
            return {
                "status": "failed",
                "message": f"Failed: {error_msg}",
                "error": error_msg,
            }
        else:
            return {
                "status": state.lower(),
                "message": f"Status: {state}",
            }

    def stream_data(self, request) -> Generator[str, None, None]:
        """
        Stream Celery task progress as SSE events.

        Polls Celery task state at poll_interval and yields progress updates.
        Only yields when state changes to reduce bandwidth.
        Terminates on SUCCESS or FAILURE.

        Args:
            request: HttpRequest object

        Yields:
            Formatted SSE event strings with progress data
        """
        from celery.result import AsyncResult

        task_id = self.get_task_id(request)
        result = AsyncResult(task_id)
        last_state_json = None

        while True:
            try:
                state = result.state
                # result.info may be an exception object if task failed, so check it's a dict
                info = result.info if isinstance(result.info, dict) else {}

                progress_data = self.build_progress_data(state, info)
                current_json = json.dumps(progress_data)

                # Only send if state changed
                if current_json != last_state_json:
                    yield f"data: {current_json}\n\n"
                    last_state_json = current_json

                # Terminate on final states
                if state in ("SUCCESS", "FAILURE"):
                    break

                time.sleep(self.poll_interval)

            except GeneratorExit:
                break
            except Exception as e:
                logger.error(f"[CeleryTaskStream] Error: {e}")
                yield f"data: {json.dumps({'status': 'error', 'error': str(e)})}\n\n"
                break
