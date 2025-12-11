"""
Base classes and utilities for Server-Sent Events (SSE) streaming views.

Provides reusable infrastructure for streaming analysis progress to the frontend.
"""

import json
import logging
from collections.abc import Callable, Generator

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, StreamingHttpResponse
from django.views import View

logger = logging.getLogger(__name__)


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
    """

    @staticmethod
    def stream_pipeline_events(
        pipeline_stream: Generator,
        send_sse_func: Callable[[str, dict | None, str | None], str] = send_sse_event,
    ) -> Generator[tuple[str, bool], None, None]:
        """
        Convert AnalysisPipeline stream events to SSE events.

        Args:
            pipeline_stream: Generator from pipeline.stream_analysis()
            send_sse_func: SSE formatting function (defaults to send_sse_event)

        Yields:
            Tuple of (sse_event_string, from_cache_flag)

        Returns:
            Tuple of (result, from_cache)

        Example:
            pipeline = AnalysisPipeline(request)
            stream = pipeline.stream_analysis(config)

            for sse_event in self.stream_pipeline_events(stream):
                yield sse_event
        """
        from commcare_connect.labs.analysis.pipeline import EVENT_DOWNLOAD, EVENT_RESULT, EVENT_STATUS

        result = None
        from_cache = False

        for event_type, event_data in pipeline_stream:
            if event_type == EVENT_STATUS:
                message = event_data.get("message", "Processing...")
                from_cache = from_cache or "cache" in message.lower()
                yield send_sse_func(message), from_cache

            elif event_type == EVENT_DOWNLOAD:
                bytes_dl = event_data.get("bytes", 0)
                total_bytes = event_data.get("total", 0)
                if total_bytes > 0:
                    mb_dl = bytes_dl / (1024 * 1024)
                    mb_total = total_bytes / (1024 * 1024)
                    pct = int(bytes_dl / total_bytes * 100)
                    yield send_sse_func(f"Downloading: {mb_dl:.1f} / {mb_total:.1f} MB ({pct}%)"), from_cache
                else:
                    yield send_sse_func("Downloading data..."), from_cache

            elif event_type == EVENT_RESULT:
                result = event_data
                break

        return result, from_cache
