"""
Labs Analysis Framework

Provides reusable components for analyzing UserVisit data in labs projects.

Two main analysis patterns:
- FLW Analysis: One row per FLW with aggregated computations
- Visit Analysis: One row per visit with computed fields (no aggregation)

Backends (configured via settings.LABS_ANALYSIS_BACKEND):
- python_redis: Redis/file caching with pandas computation (default)
- sql: PostgreSQL table caching with SQL computation

Usage:
    # Using the streaming pipeline (recommended for dashboards)
    from commcare_connect.labs.analysis.pipeline import stream_analysis_pipeline

    for event_type, data in stream_analysis_pipeline(request, config):
        if event_type == "status":
            yield format_sse(data)
        elif event_type == "result":
            return data

    # Synchronous use (tests, Celery, management commands)
    from commcare_connect.labs.analysis.pipeline import run_analysis_pipeline

    result = run_analysis_pipeline(request, config)
"""

# Import from python_redis backend for direct access when needed
from commcare_connect.labs.analysis.backends.python_redis.flw_analyzer import FLWAnalyzer, compute_flw_analysis
from commcare_connect.labs.analysis.backends.python_redis.visit_analyzer import VisitAnalyzer, compute_visit_analysis
from commcare_connect.labs.analysis.config import (
    AnalysisConfig,
    AnalysisPipelineConfig,
    CacheStage,
    FieldComputation,
    HistogramComputation,
)
from commcare_connect.labs.analysis.data_access import AnalysisDataAccess, get_flw_names_for_opportunity
from commcare_connect.labs.analysis.models import (
    AnalysisResult,
    FLWAnalysisResult,
    FLWRow,
    LocalUserVisit,
    VisitAnalysisResult,
    VisitRow,
)

# Pipeline - main entry points (backend-agnostic)
from commcare_connect.labs.analysis.pipeline import (
    EVENT_DOWNLOAD,
    EVENT_ERROR,
    EVENT_RESULT,
    EVENT_STATUS,
    run_analysis_pipeline,
    stream_analysis_pipeline,
)

__all__ = [
    # Pipeline (recommended entry points)
    "stream_analysis_pipeline",
    "run_analysis_pipeline",
    "EVENT_STATUS",
    "EVENT_DOWNLOAD",
    "EVENT_RESULT",
    "EVENT_ERROR",
    # Config
    "AnalysisConfig",  # Backwards compatibility alias
    "AnalysisPipelineConfig",
    "CacheStage",
    "FieldComputation",
    "HistogramComputation",
    # FLW Analysis
    "FLWAnalyzer",
    "FLWAnalysisResult",
    "FLWRow",
    "compute_flw_analysis",
    # Visit Analysis
    "VisitAnalyzer",
    "VisitAnalysisResult",
    "VisitRow",
    "compute_visit_analysis",
    # Data models
    "AnalysisResult",
    "LocalUserVisit",
    # Data access
    "AnalysisDataAccess",
    "get_flw_names_for_opportunity",
]
