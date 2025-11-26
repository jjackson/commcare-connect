"""
Labs Analysis Framework

Provides reusable components for analyzing UserVisit data in labs projects.

Two main analysis patterns:
- FLW Analysis: One row per FLW with aggregated computations
- Visit Analysis: One row per visit with computed fields (no aggregation)

Usage:
    # Using the unified pipeline (recommended)
    from commcare_connect.labs.analysis import AnalysisPipelineConfig, CacheStage
    from commcare_connect.labs.analysis.pipeline import run_analysis_pipeline

    config = AnalysisPipelineConfig(
        grouping_key="username",
        fields=[
            FieldComputation(
                name="buildings_visited",
                path="form.building_count",
                aggregation="sum"
            )
        ],
        experiment="my_project",
        terminal_stage=CacheStage.AGGREGATED,
    )

    result = run_analysis_pipeline(request, config)

    # FLW-level analysis (aggregated) - legacy pattern
    from commcare_connect.labs.analysis import FLWAnalyzer, AnalysisConfig, FieldComputation

    config = AnalysisConfig(
        grouping_key="username",
        fields=[
            FieldComputation(
                name="buildings_visited",
                path="form.building_count",
                aggregation="sum"
            )
        ]
    )

    analyzer = FLWAnalyzer(request=request, config=config)
    result = analyzer.compute()

    # Visit-level analysis (per-visit)
    from commcare_connect.labs.analysis import VisitAnalyzer

    analyzer = VisitAnalyzer(request=request, config=config)
    result = analyzer.compute()  # One row per visit
"""

from commcare_connect.labs.analysis.config import (
    AnalysisConfig,
    AnalysisPipelineConfig,
    CacheStage,
    FieldComputation,
    HistogramComputation,
)
from commcare_connect.labs.analysis.flw_analyzer import FLWAnalyzer, compute_flw_analysis
from commcare_connect.labs.analysis.models import (
    AnalysisResult,
    FLWAnalysisResult,
    FLWRow,
    VisitAnalysisResult,
    VisitRow,
)
from commcare_connect.labs.analysis.visit_analyzer import VisitAnalyzer, compute_visit_analysis

__all__ = [
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
    # Base
    "AnalysisResult",
]
