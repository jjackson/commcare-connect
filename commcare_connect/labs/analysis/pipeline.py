"""
Unified analysis pipeline with multi-tier caching.

Provides run_analysis_pipeline() which handles:
1. LabsRecord cache (persistent, cross-session) - if ?use_labs_record_cache=true
2. Redis/file cache (fast, ephemeral)
3. Fresh computation when caches miss

The pipeline automatically determines the terminal stage from the config
and returns the appropriate result type.

TROUBLESHOOTING: Duplicate Analysis Runs
----------------------------------------
If you see the pipeline running twice for a single page load, check the Alpine.js
template for duplicate init() calls. In Alpine.js v3, if your x-data returns an
object with an init() method, Alpine calls it automatically. Having BOTH:

    x-data="myComponent()" x-init="init()"

will call init() TWICE. Remove the x-init attribute:

    x-data="myComponent()"

This has caused duplicate API calls twice now - check templates first!
"""

import logging

from django.http import HttpRequest

from commcare_connect.labs.analysis.config import AnalysisPipelineConfig, CacheStage
from commcare_connect.labs.analysis.models import FLWAnalysisResult, VisitAnalysisResult

logger = logging.getLogger(__name__)


def run_analysis_pipeline(
    request: HttpRequest,
    config: AnalysisPipelineConfig,
) -> VisitAnalysisResult | FLWAnalysisResult:
    """
    Run complete analysis pipeline based on config.

    This is the unified entry point for all analysis operations. It handles:
    1. Checking caches in order (LabsRecord -> Redis/file)
    2. Computing fresh results when needed
    3. Populating caches after computation
    4. Returning the appropriate result type based on terminal_stage

    Cache hierarchy:
    1. LabsRecord (if ?use_labs_record_cache=true) - persistent, cross-session
    2. Redis/file cache - fast, ephemeral
    3. Fresh computation

    Args:
        request: HttpRequest with labs context
        config: AnalysisPipelineConfig with computation and pipeline metadata

    Returns:
        VisitAnalysisResult if terminal_stage=VISIT_LEVEL
        FLWAnalysisResult if terminal_stage=AGGREGATED

    Example:
        from commcare_connect.labs.analysis.pipeline import run_analysis_pipeline

        config = AnalysisPipelineConfig(
            grouping_key="username",
            fields=[...],
            experiment="chc_nutrition",
            terminal_stage=CacheStage.AGGREGATED,
        )

        result = run_analysis_pipeline(request, config)
        # Returns FLWAnalysisResult because terminal_stage=AGGREGATED
    """
    from commcare_connect.labs.analysis.cache import (
        AnalysisCacheManager,
        LabsRecordCacheManager,
        sync_labs_context_visit_count,
    )
    from commcare_connect.labs.analysis.flw_analyzer import FLWAnalyzer
    from commcare_connect.labs.analysis.visit_analyzer import VisitAnalyzer

    opportunity_id = getattr(request, "labs_context", {}).get("opportunity_id")
    force_refresh = request.GET.get("refresh") == "1"
    use_labs_record_cache = request.GET.get("use_labs_record_cache") == "true"

    experiment = config.experiment or "analysis"
    terminal_stage = config.terminal_stage
    analysis_type = "flw_analysis" if terminal_stage == CacheStage.AGGREGATED else "visit_analysis"

    logger.info(
        f"[Pipeline] Starting analysis pipeline: experiment={experiment}, "
        f"terminal_stage={terminal_stage.value}, opp={opportunity_id}, "
        f"labs_record_cache={use_labs_record_cache}, refresh={force_refresh}"
    )

    # Get current visit count for cache validation
    current_visit_count = _get_current_visit_count(request)

    # ---------------------------------------------------------------------
    # Stage 1: Check LabsRecord cache (if enabled and not force refresh)
    # ---------------------------------------------------------------------
    if use_labs_record_cache and not force_refresh and experiment:
        labs_cache = LabsRecordCacheManager(request, experiment)
        cached_data = labs_cache.get(analysis_type)

        if cached_data and labs_cache.is_valid(cached_data, current_visit_count):
            logger.info(f"[Pipeline] LabsRecord CACHE HIT for {experiment}/{analysis_type}")
            result = _deserialize_result(cached_data["result"], terminal_stage)
            if result:
                return result
            logger.warning("[Pipeline] Failed to deserialize LabsRecord cache, computing fresh")

    # ---------------------------------------------------------------------
    # Stage 2: Check Redis/file cache (if not force refresh)
    # ---------------------------------------------------------------------
    cache_manager = AnalysisCacheManager(opportunity_id, config)

    if not force_refresh:
        if terminal_stage == CacheStage.AGGREGATED:
            cached = cache_manager.get_results_cache()
            if cached and cache_manager.validate_cache(current_visit_count, cached):
                logger.info(f"[Pipeline] Redis/file CACHE HIT for FLW results (opp {opportunity_id})")
                return cached["result"]
        else:
            cached = cache_manager.get_visit_results_cache()
            if cached and cache_manager.validate_cache(current_visit_count, cached):
                logger.info(f"[Pipeline] Redis/file CACHE HIT for visit results (opp {opportunity_id})")
                return cached["result"]

    # ---------------------------------------------------------------------
    # Stage 3: Compute fresh results
    # ---------------------------------------------------------------------
    logger.info(f"[Pipeline] Computing fresh analysis (opp {opportunity_id})")

    # Always compute visit-level first
    visit_analyzer = VisitAnalyzer(request, config)
    visit_result = visit_analyzer.compute()
    visit_count = visit_result.metadata.get("total_visits", 0)

    # Cache visit results
    cache_manager.set_visit_results_cache(visit_count, visit_result)

    if terminal_stage == CacheStage.VISIT_LEVEL:
        # Visit-level is terminal - sync context and return
        sync_labs_context_visit_count(request, visit_count, opportunity_id)

        if use_labs_record_cache and experiment:
            labs_cache = LabsRecordCacheManager(request, experiment)
            labs_cache.set(analysis_type, visit_result, visit_count)

        logger.info(f"[Pipeline] Returning visit result ({visit_count} visits)")
        return visit_result

    # Aggregate to FLW level
    flw_analyzer = FLWAnalyzer(request, config)
    flw_result = flw_analyzer.from_visit_result(visit_result)

    # Cache FLW results
    cache_manager.set_results_cache(visit_count, flw_result)

    # Sync context
    sync_labs_context_visit_count(request, visit_count, opportunity_id)

    # Save to LabsRecord if enabled
    if use_labs_record_cache and experiment:
        labs_cache = LabsRecordCacheManager(request, experiment)
        labs_cache.set(analysis_type, flw_result, visit_count)

    logger.info(f"[Pipeline] Returning FLW result ({len(flw_result.rows)} FLWs, {visit_count} visits)")
    return flw_result


def _get_current_visit_count(request: HttpRequest) -> int:
    """Get current visit count from labs_context for cache validation."""
    opportunity = getattr(request, "labs_context", {}).get("opportunity", {})
    count = opportunity.get("visit_count", 0)
    return count


def _deserialize_result(data: dict, terminal_stage: CacheStage) -> VisitAnalysisResult | FLWAnalysisResult | None:
    """
    Deserialize cached result data back to result object.

    Args:
        data: Serialized result dict from cache
        terminal_stage: Expected result type

    Returns:
        Result object or None if deserialization fails
    """
    try:
        if terminal_stage == CacheStage.AGGREGATED:
            return FLWAnalysisResult.from_dict(data)
        else:
            return VisitAnalysisResult.from_dict(data)
    except Exception as e:
        logger.warning(f"Failed to deserialize cached result: {e}")
        return None
