"""
Labs Analysis Framework

Provides reusable components for analyzing UserVisit data in labs projects.

Two main analysis patterns:
- FLW Analysis: One row per FLW with aggregated computations
- Visit Analysis: One row per visit with computed fields (no aggregation)

Usage:
    # FLW-level analysis (aggregated)
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

from commcare_connect.labs.analysis.config import AnalysisConfig, FieldComputation, HistogramComputation
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
    "AnalysisConfig",
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
