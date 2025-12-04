"""
Visit-level analysis implementation for python_redis backend.

Provides one-row-per-visit analysis with computed fields (no aggregation).
Uses pandas for data processing.
"""

import logging

import pandas as pd
from django.http import HttpRequest

from commcare_connect.labs.analysis.backends.python_redis.computations import compute_visit_fields
from commcare_connect.labs.analysis.config import AnalysisPipelineConfig, FieldComputation
from commcare_connect.labs.analysis.models import LocalUserVisit, VisitAnalysisResult, VisitRow
from commcare_connect.labs.analysis.pipeline import AnalysisPipeline

logger = logging.getLogger(__name__)


class VisitAnalyzer:
    """
    Analyzes visits at individual level: one row per visit with computed fields.

    Unlike FLWAnalyzer which aggregates visits by worker, this preserves each
    visit and computes field values individually from form_json.
    """

    def __init__(self, request: HttpRequest, config: AnalysisPipelineConfig | None = None):
        """
        Initialize visit analyzer.

        Args:
            request: HttpRequest with labs context
            config: Optional AnalysisPipelineConfig with field computations.
                    If None, only base visit properties are included.
        """
        # Use empty config if none provided
        if config is None:
            config = AnalysisPipelineConfig(grouping_key="username", fields=[])

        self.request = request
        self.config = config
        self._pipeline = AnalysisPipeline(request)

    def fetch_visits(self) -> list[LocalUserVisit]:
        """Fetch user visits from API."""
        visit_dicts = self._pipeline.fetch_raw_visits()
        return [LocalUserVisit(d) for d in visit_dicts]

    def filter_visits(self, visits: list[LocalUserVisit]) -> list[LocalUserVisit]:
        """
        Apply filters from config to visits.

        Args:
            visits: List of visits to filter

        Returns:
            Filtered list of visits
        """
        filtered = visits

        # Apply status filter
        if "status" in self.config.filters:
            statuses = self.config.filters["status"]
            if not isinstance(statuses, list):
                statuses = [statuses]
            filtered = [v for v in filtered if v.status in statuses]

        # Apply date range filter
        if "date_from" in self.config.filters:
            date_from = pd.to_datetime(self.config.filters["date_from"])
            filtered = [v for v in filtered if v.visit_date and v.visit_date >= date_from]

        if "date_to" in self.config.filters:
            date_to = pd.to_datetime(self.config.filters["date_to"])
            filtered = [v for v in filtered if v.visit_date and v.visit_date <= date_to]

        # Apply flagged filter
        if "flagged" in self.config.filters:
            flagged = self.config.filters["flagged"]
            filtered = [v for v in filtered if v.flagged == flagged]

        return filtered

    def compute(self, prefetched_visits: list[LocalUserVisit] | None = None) -> VisitAnalysisResult:
        """
        Compute visit-level analysis.

        Args:
            prefetched_visits: Optional pre-fetched visits to use instead of fetching.
                              This allows callers to provide visits they already have in memory,
                              avoiding redundant API calls or cache reads.

        Returns:
            VisitAnalysisResult with one VisitRow per visit
        """
        logger.info("Starting visit-level analysis computation")

        # Use prefetched visits if provided, otherwise fetch from API/cache
        if prefetched_visits is not None:
            logger.info(f"Using {len(prefetched_visits)} prefetched visits (skipping fetch)")
            all_visits = prefetched_visits
        else:
            all_visits = self.fetch_visits()

        filtered_visits = self.filter_visits(all_visits)

        # Compute fields for each visit (include histogram raw values for later aggregation)
        computed_list = []
        if self.config.fields or self.config.histograms:
            computed_list = compute_visit_fields(
                filtered_visits,
                self.config.fields,
                hist_comps=self.config.histograms if self.config.histograms else None,
            )
            logger.info(
                f"Computed {len(self.config.fields)} fields and "
                f"{len(self.config.histograms) if self.config.histograms else 0} histogram values "
                f"for {len(filtered_visits)} visits"
            )

        # Build VisitRow for each visit
        rows = []
        for i, visit in enumerate(filtered_visits):
            # Get computed fields for this visit
            computed = {}
            if computed_list and i < len(computed_list):
                computed = {k: v for k, v in computed_list[i].items() if k != "visit_id"}

            row = VisitRow(
                id=visit.id,
                user_id=visit.user_id,
                username=visit.username,
                commcare_userid=visit.commcare_userid,
                visit_date=visit.visit_date,
                status=visit.status,
                flagged=visit.flagged,
                latitude=visit.latitude,
                longitude=visit.longitude,
                accuracy_in_m=visit.accuracy_in_m,
                deliver_unit_id=visit.deliver_unit_id,
                deliver_unit_name=visit.deliver_unit_name,
                entity_id=visit.entity_id,
                entity_name=visit.entity_name,
                computed=computed,
            )
            rows.append(row)

        # Create result
        opportunity_id = self._pipeline.opportunity_id
        opportunity_name = self._pipeline.labs_context.get("opportunity_name")

        result = VisitAnalysisResult(
            opportunity_id=opportunity_id,
            opportunity_name=opportunity_name,
            rows=rows,
            field_metadata=self.get_field_metadata(),
            metadata={
                "total_visits": len(rows),
                "visits_with_gps": sum(1 for r in rows if r.has_gps),
                "filters_applied": self.config.filters,
                "computed_fields": [f.name for f in self.config.fields],
            },
        )

        return result

    def get_field_metadata(self) -> list[dict]:
        """
        Get metadata about computed fields for filter UI.

        Returns:
            List of field info dicts: [{name, description, type}, ...]
        """
        if not self.config:
            return []

        metadata = []
        for fc in self.config.fields:
            field_info = {
                "name": fc.name,
                "description": fc.description or fc.name,
                "type": self._infer_field_type(fc),
            }
            metadata.append(field_info)

        return metadata

    def _infer_field_type(self, fc: FieldComputation) -> str:
        """Infer field type for filter UI."""
        # Check aggregation type for hints
        if fc.aggregation in ["count", "count_unique", "sum"]:
            return "number"
        if fc.aggregation in ["avg", "min", "max"]:
            return "number"
        if fc.aggregation == "list":
            return "list"

        # Check if transform suggests boolean
        if fc.transform:
            # If transform returns 1 for yes/true, likely boolean
            transform_str = str(fc.transform)
            if "yes" in transform_str.lower() or "true" in transform_str.lower():
                return "boolean"

        # Default to string
        return "string"


def compute_visit_analysis(
    request: HttpRequest,
    config: AnalysisPipelineConfig,
    use_cache: bool = True,
    cache_tolerance_minutes: int | None = None,
) -> VisitAnalysisResult:
    """
    Compute visit-level analysis with caching.

    Orchestration layer that handles caching outside the analyzer.
    The VisitAnalyzer itself has no cache knowledge.

    Caching strategy:
    - Cache key includes opportunity_id and config hash
    - Invalidation based on visit count changes
    - Manual refresh via ?refresh=1 parameter
    - Optional tolerance for accepting slightly stale cache

    Args:
        request: HttpRequest with labs context
        config: AnalysisPipelineConfig defining field computations
        use_cache: Whether to use caching (default: True)
        cache_tolerance_minutes: Accept cache if age < N minutes (even if counts mismatch)

    Returns:
        VisitAnalysisResult with one VisitRow per visit
    """
    from commcare_connect.labs.analysis.backends.python_redis.cache import (
        AnalysisCacheManager,
        get_cache_tolerance_from_request,
        sync_labs_context_visit_count,
    )

    opportunity_id = getattr(request, "labs_context", {}).get("opportunity_id")
    force_refresh = request.GET.get("refresh") == "1"

    logger.info(f"[Analysis] compute_visit_analysis called (opp {opportunity_id}, cache={use_cache})")

    # Skip cache if disabled or refresh requested
    if not use_cache or force_refresh:
        logger.info(f"[Analysis] Skipping cache (disabled={not use_cache}, refresh={force_refresh})")
        analyzer = VisitAnalyzer(request, config)
        result = analyzer.compute()

        # Still populate cache for next time if caching is enabled
        if use_cache:
            cache_manager = AnalysisCacheManager(opportunity_id, config)
            visit_count = result.metadata.get("total_visits", 0)
            cache_manager.set_visit_results_cache(visit_count, result)
            sync_labs_context_visit_count(request, visit_count, opportunity_id)

        return result

    # Initialize cache manager
    cache_manager = AnalysisCacheManager(opportunity_id, config)
    logger.info(f"[Analysis] Config hash: {cache_manager.config_hash}")

    # Extract tolerance from request if not explicitly provided
    if cache_tolerance_minutes is None:
        cache_tolerance_minutes = get_cache_tolerance_from_request(request)

    # Get current visit count for validation
    try:
        pipeline = AnalysisPipeline(request)
        current_visit_count = pipeline.visit_count
        logger.info(f"[Analysis] Current visit count: {current_visit_count}")
    except Exception as e:
        logger.warning(f"[Analysis] Failed to fetch visit count: {e}")
        # Fall back to computing fresh
        analyzer = VisitAnalyzer(request, config)
        return analyzer.compute()

    # Try cache
    cached = cache_manager.get_visit_results_cache()
    if cached and cache_manager.validate_cache(current_visit_count, cached, cache_tolerance_minutes):
        logger.info(f"[Analysis] CACHE HIT - using cached visit results (opp {opportunity_id})")
        return cached["result"]

    # Cache miss - compute fresh
    logger.info(f"[Analysis] CACHE MISS - computing fresh (opp {opportunity_id})")
    analyzer = VisitAnalyzer(request, config)
    result = analyzer.compute()

    # Cache the results
    visit_count = result.metadata.get("total_visits", 0)
    cache_manager.set_visit_results_cache(visit_count, result)
    logger.info(f"[Analysis] Cached {visit_count} visits for next time")

    # Sync labs_context with actual visit count to prevent future cache misses
    sync_labs_context_visit_count(request, visit_count, opportunity_id)

    return result
