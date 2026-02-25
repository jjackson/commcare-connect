"""
Labs Analysis Framework

Provides reusable components for analyzing UserVisit data in labs projects.

Two main analysis patterns:
- FLW Analysis: One row per FLW with aggregated computations
- Visit Analysis: One row per visit with computed fields (no aggregation)

Uses PostgreSQL table caching with SQL computation (SQLBackend).

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

# Shared computation functions (used by audit and pipeline backends)
from commcare_connect.labs.analysis.computations import compute_visit_fields
from commcare_connect.labs.analysis.config import (
    AnalysisConfig,
    AnalysisPipelineConfig,
    CacheStage,
    FieldComputation,
    HistogramComputation,
)
from commcare_connect.labs.analysis.data_access import fetch_flw_names, get_flw_names_for_opportunity
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
    AnalysisPipeline,
    run_analysis_pipeline,
    stream_analysis_pipeline,
)

__all__ = [
    # Pipeline (recommended entry points)
    "AnalysisPipeline",
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
    "FLWAnalysisResult",
    "FLWRow",
    # Visit Analysis
    "VisitAnalysisResult",
    "VisitRow",
    "compute_visit_fields",
    # Data models
    "AnalysisResult",
    "LocalUserVisit",
    # Data access
    "fetch_flw_names",
    "get_flw_names_for_opportunity",
]
