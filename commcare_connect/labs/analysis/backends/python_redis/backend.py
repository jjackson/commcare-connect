"""
Python/Redis backend implementation.

Uses Redis/file caching with pandas-based computation.
"""

import logging

from django.http import HttpRequest

from commcare_connect.labs.analysis.backends.python_redis.cache import (
    AnalysisCacheManager,
    sync_labs_context_visit_count,
)
from commcare_connect.labs.analysis.backends.python_redis.flw_analyzer import FLWAnalyzer
from commcare_connect.labs.analysis.backends.python_redis.visit_analyzer import VisitAnalyzer
from commcare_connect.labs.analysis.config import AnalysisPipelineConfig, CacheStage
from commcare_connect.labs.analysis.models import FLWAnalysisResult, LocalUserVisit, VisitAnalysisResult

logger = logging.getLogger(__name__)


class PythonRedisBackend:
    """
    Python/Redis backend for analysis.

    Uses Redis (preferred) or file-based caching with pandas-based computation.
    """

    def get_cached_flw_result(
        self, opportunity_id: int, config: AnalysisPipelineConfig, visit_count: int
    ) -> FLWAnalysisResult | None:
        """Get cached FLW result if valid."""
        cache_manager = AnalysisCacheManager(opportunity_id, config)
        cached = cache_manager.get_results_cache()
        if cached and cache_manager.validate_cache(visit_count, cached):
            logger.info(f"[PythonRedis] FLW cache HIT for opp {opportunity_id}")
            return cached["result"]
        return None

    def get_cached_visit_result(
        self, opportunity_id: int, config: AnalysisPipelineConfig, visit_count: int
    ) -> VisitAnalysisResult | None:
        """Get cached visit result if valid."""
        cache_manager = AnalysisCacheManager(opportunity_id, config)
        cached = cache_manager.get_visit_results_cache()
        if cached and cache_manager.validate_cache(visit_count, cached):
            logger.info(f"[PythonRedis] Visit cache HIT for opp {opportunity_id}")
            return cached["result"]
        return None

    def process_and_cache(
        self,
        request: HttpRequest,
        config: AnalysisPipelineConfig,
        opportunity_id: int,
        visit_dicts: list[dict],
    ) -> FLWAnalysisResult | VisitAnalysisResult:
        """
        Process visits and cache results.

        Returns FLWAnalysisResult if terminal_stage=AGGREGATED, else VisitAnalysisResult.
        """
        # Convert to LocalUserVisit objects
        visits = [LocalUserVisit(d) for d in visit_dicts]
        logger.info(f"[PythonRedis] Processing {len(visits)} visits for opp {opportunity_id}")

        # Compute visit-level analysis
        visit_analyzer = VisitAnalyzer(request, config)
        visit_result = visit_analyzer.compute(prefetched_visits=visits)
        visit_count = visit_result.metadata.get("total_visits", 0)

        # Cache visit results
        cache_manager = AnalysisCacheManager(opportunity_id, config)
        cache_manager.set_visit_results_cache(visit_count, visit_result)

        # If visit-level is terminal, return now
        if config.terminal_stage == CacheStage.VISIT_LEVEL:
            sync_labs_context_visit_count(request, visit_count, opportunity_id)
            return visit_result

        # Aggregate to FLW level
        flw_analyzer = FLWAnalyzer(request, config)
        flw_result = flw_analyzer.from_visit_result(visit_result)

        # Cache FLW results
        cache_manager.set_results_cache(visit_count, flw_result)

        # Sync context
        sync_labs_context_visit_count(request, visit_count, opportunity_id)

        logger.info(f"[PythonRedis] Processed {len(flw_result.rows)} FLWs, {visit_count} visits")
        return flw_result
