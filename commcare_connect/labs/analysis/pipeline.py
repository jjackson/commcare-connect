"""
Analysis pipeline with streaming and backend abstraction.

Provides stream_analysis_pipeline() - the main entry point for all analysis.
Yields progress events as analysis progresses, enabling real-time UI updates.

Backend selection is based on settings.LABS_ANALYSIS_BACKEND:
- "python_redis" (default): Redis/file caching with pandas computation
- "sql": PostgreSQL table caching with SQL computation

Usage:
    from commcare_connect.labs.analysis.pipeline import stream_analysis_pipeline

    for event_type, event_data in stream_analysis_pipeline(request, config):
        if event_type == "status":
            yield format_sse(event_data["message"])
        elif event_type == "download":
            yield format_download_progress(event_data["bytes"], event_data["total"])
        elif event_type == "result":
            return event_data
"""

import logging
from collections.abc import Generator
from typing import Any, Protocol

from django.conf import settings
from django.http import HttpRequest

from commcare_connect.labs.analysis.config import AnalysisPipelineConfig, CacheStage
from commcare_connect.labs.analysis.models import FLWAnalysisResult, VisitAnalysisResult

logger = logging.getLogger(__name__)

# Event type constants
EVENT_STATUS = "status"
EVENT_DOWNLOAD = "download"
EVENT_RESULT = "result"
EVENT_ERROR = "error"


class AnalysisBackend(Protocol):
    """Protocol defining the interface for analysis backends."""

    def get_cached_flw_result(
        self, opportunity_id: int, config: AnalysisPipelineConfig, visit_count: int
    ) -> FLWAnalysisResult | None:
        """Get cached FLW result if valid."""
        ...

    def get_cached_visit_result(
        self, opportunity_id: int, config: AnalysisPipelineConfig, visit_count: int
    ) -> VisitAnalysisResult | None:
        """Get cached visit result if valid."""
        ...

    def process_and_cache(
        self,
        request: HttpRequest,
        config: AnalysisPipelineConfig,
        opportunity_id: int,
        visit_dicts: list[dict],
    ) -> FLWAnalysisResult | VisitAnalysisResult:
        """Process visits and cache results. Returns appropriate result based on terminal_stage."""
        ...


def _get_backend_name() -> str:
    """Get configured backend name from settings."""
    return getattr(settings, "LABS_ANALYSIS_BACKEND", "python_redis")


def _get_backend() -> AnalysisBackend:
    """Get the configured backend instance."""
    backend_name = _get_backend_name()

    if backend_name == "sql":
        from commcare_connect.labs.analysis.backends.sql.backend import SQLBackend

        return SQLBackend()
    else:
        from commcare_connect.labs.analysis.backends.python_redis.backend import PythonRedisBackend

        return PythonRedisBackend()


def stream_analysis_pipeline(
    request: HttpRequest,
    config: AnalysisPipelineConfig,
    opportunity_id: int | None = None,
) -> Generator[tuple[str, Any], None, None]:
    """
    Stream analysis pipeline with progress events.

    Yields:
        Tuples of (event_type, event_data):
        - ("status", {"message": "..."}) - progress updates
        - ("download", {"bytes": N, "total": M}) - download progress
        - ("result", FLWAnalysisResult|VisitAnalysisResult) - final result
        - ("error", {"message": "..."}) - error (terminates stream)
    """
    from commcare_connect.labs.api_cache import _parse_csv_bytes, stream_user_visits_with_progress

    backend = _get_backend()
    backend_name = _get_backend_name()

    # Extract context
    labs_context = getattr(request, "labs_context", {})
    if opportunity_id is None:
        opportunity_id = labs_context.get("opportunity_id")

    force_refresh = request.GET.get("refresh") == "1"
    terminal_stage = config.terminal_stage

    try:
        # Check cache
        yield (EVENT_STATUS, {"message": "Checking cache..."})

        opportunity = labs_context.get("opportunity", {})
        current_visit_count = opportunity.get("visit_count", 0)

        if not force_refresh:
            cached_result = None
            if terminal_stage == CacheStage.AGGREGATED:
                cached_result = backend.get_cached_flw_result(opportunity_id, config, current_visit_count)
            else:
                cached_result = backend.get_cached_visit_result(opportunity_id, config, current_visit_count)

            if cached_result:
                yield (EVENT_STATUS, {"message": "Cache hit!"})
                logger.info(f"[Pipeline/{backend_name}] Cache HIT for opp {opportunity_id}")
                yield (EVENT_RESULT, cached_result)
                return

        # Download data
        yield (EVENT_STATUS, {"message": "Connecting to API..."})
        logger.info(f"[Pipeline/{backend_name}] Downloading data for opp {opportunity_id}")

        access_token = request.session.get("labs_oauth", {}).get("access_token")
        csv_bytes = None

        for event in stream_user_visits_with_progress(
            opportunity_id=opportunity_id,
            access_token=access_token,
            current_visit_count=current_visit_count,
            force_refresh=force_refresh,
        ):
            event_type = event[0]
            if event_type == "cached":
                csv_bytes = event[1]
                yield (EVENT_STATUS, {"message": "Using cached data..."})
            elif event_type == "progress":
                _, bytes_downloaded, total_bytes = event
                yield (EVENT_DOWNLOAD, {"bytes": bytes_downloaded, "total": total_bytes})
            elif event_type == "complete":
                csv_bytes = event[1]
                yield (EVENT_STATUS, {"message": "Download complete"})

        if csv_bytes is None:
            raise RuntimeError("No data received from API")

        # Parse data
        yield (EVENT_STATUS, {"message": "Parsing visit data..."})
        visit_dicts = _parse_csv_bytes(csv_bytes, opportunity_id, skip_form_json=False)

        # Process with backend
        yield (EVENT_STATUS, {"message": f"Processing {len(visit_dicts)} visits..."})
        logger.info(f"[Pipeline/{backend_name}] Processing {len(visit_dicts)} visits")

        result = backend.process_and_cache(request, config, opportunity_id, visit_dicts)

        yield (EVENT_STATUS, {"message": "Complete!"})
        logger.info(f"[Pipeline/{backend_name}] Complete: {len(result.rows)} rows")

        yield (EVENT_RESULT, result)

    except Exception as e:
        logger.error(f"[Pipeline/{backend_name}] Error: {e}", exc_info=True)
        yield (EVENT_ERROR, {"message": str(e)})


def run_analysis_pipeline(
    request: HttpRequest,
    config: AnalysisPipelineConfig,
    opportunity_id: int | None = None,
) -> VisitAnalysisResult | FLWAnalysisResult:
    """
    Synchronous wrapper around stream_analysis_pipeline.

    Consumes the stream and returns the final result.
    """
    for event_type, data in stream_analysis_pipeline(request, config, opportunity_id):
        if event_type == EVENT_RESULT:
            return data
        elif event_type == EVENT_ERROR:
            raise RuntimeError(f"Analysis pipeline failed: {data.get('message', 'Unknown error')}")

    raise RuntimeError("Analysis pipeline completed without returning a result")
