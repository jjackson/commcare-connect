"""
FLW-level analysis implementation.

Provides one-row-per-FLW analysis with aggregated visit computations.
"""

import logging
from collections import defaultdict
from typing import Any

from django.http import HttpRequest

from commcare_connect.labs.analysis.base import Analyzer, LocalUserVisit
from commcare_connect.labs.analysis.computations import (
    aggregate_histogram_from_values,
    compute_fields_batch,
    compute_histograms_batch,
)
from commcare_connect.labs.analysis.config import AnalysisConfig
from commcare_connect.labs.analysis.models import FLWAnalysisResult, FLWRow, VisitAnalysisResult, VisitRow

logger = logging.getLogger(__name__)


class FLWAnalyzer(Analyzer):
    """
    Analyzes visits at FLW level: one row per worker with aggregated visit data.

    Standard metrics computed for all FLWs:
    - Total visits (overall and by status)
    - Date range (first/last visit)
    - Days active
    - Approval rate

    Custom metrics from config:
    - Any fields defined in AnalysisConfig.fields
    - Aggregated according to specified rules
    """

    def __init__(self, request: HttpRequest, config: AnalysisConfig):
        """
        Initialize FLW analyzer.

        Args:
            request: HttpRequest with labs context
            config: AnalysisConfig with field computations (grouping_key should be "username")
        """
        super().__init__(request, config)

        # Validate grouping key for FLW analysis
        if config.grouping_key not in ["username", "user_id"]:
            logger.warning(
                f"FLW analysis typically uses 'username' or 'user_id' as grouping key, "
                f"but got '{config.grouping_key}'. Results may be unexpected."
            )

    def compute(self) -> FLWAnalysisResult:
        """
        Compute FLW-level analysis.

        Returns:
            FLWAnalysisResult with one FLWRow per worker
        """
        logger.info("Starting FLW analysis computation")

        # Fetch and filter visits
        all_visits = self.fetch_visits()
        filtered_visits = self.filter_visits(all_visits)

        # Group by FLW
        groups = self.group_visits(filtered_visits)

        logger.info(f"Computing analysis for {len(groups)} FLWs")

        # Compute row for each FLW
        rows = []
        for group_key, visits in groups.items():
            row = self._compute_flw_row(group_key, visits)
            rows.append(row)

        # Sort by total visits descending
        rows.sort(key=lambda r: r.total_visits, reverse=True)

        # Create result
        opportunity_id = self.data_access.opportunity_id
        opportunity_name = self.data_access.labs_context.get("opportunity_name")

        result = FLWAnalysisResult(
            opportunity_id=opportunity_id,
            opportunity_name=opportunity_name,
            rows=rows,
            metadata={
                "total_visits": len(filtered_visits),
                "total_flws": len(rows),
                "grouping_key": self.config.grouping_key,
                "filters_applied": self.config.filters,
                "custom_fields": [f.name for f in self.config.fields],
            },
        )

        logger.info(f"Computed FLW analysis: {len(rows)} FLWs, {len(filtered_visits)} visits")

        return result

    def _compute_flw_row(self, group_key: Any, visits: list[LocalUserVisit]) -> FLWRow:
        """
        Compute a single FLW row from visits.

        Args:
            group_key: Value of grouping key (username or user_id)
            visits: List of visits for this FLW

        Returns:
            FLWRow with standard and custom fields
        """
        # Standard fields
        username = visits[0].username if visits else str(group_key)
        user_id = visits[0].user_id if visits else None
        flw_name = visits[0].username if visits else username  # Could extract from user data if available

        # Visit counts by status
        total_visits = len(visits)
        status_counts = defaultdict(int)
        for visit in visits:
            status_counts[visit.status] += 1

        approved_visits = status_counts.get("approved", 0)
        pending_visits = status_counts.get("pending", 0)
        rejected_visits = status_counts.get("rejected", 0)

        # Flagged visits
        flagged_visits = sum(1 for v in visits if v.flagged)

        # Date tracking
        visit_dates = [v.visit_date.date() for v in visits if v.visit_date]
        visit_dates_sorted = sorted(visit_dates)

        first_visit_date = visit_dates_sorted[0] if visit_dates_sorted else None
        last_visit_date = visit_dates_sorted[-1] if visit_dates_sorted else None
        unique_dates = sorted(list(set(visit_dates)))

        # Create row with standard fields
        row = FLWRow(
            username=username,
            user_id=user_id,
            flw_name=flw_name,
            total_visits=total_visits,
            approved_visits=approved_visits,
            pending_visits=pending_visits,
            rejected_visits=rejected_visits,
            flagged_visits=flagged_visits,
            first_visit_date=first_visit_date,
            last_visit_date=last_visit_date,
            dates_active=unique_dates,
        )

        # Compute all custom fields at once (optimized batch operation)
        if self.config.fields:
            custom_field_values = compute_fields_batch(visits, self.config.fields)
            row.custom_fields.update(custom_field_values)

        # Compute histograms
        if self.config.histograms:
            histogram_values = compute_histograms_batch(visits, self.config.histograms)
            row.custom_fields.update(histogram_values)

        return row

    def get_result_summary(self, result: FLWAnalysisResult) -> dict:
        """
        Get summary statistics from result.

        Args:
            result: FLWAnalysisResult to summarize

        Returns:
            Dictionary of summary statistics
        """
        return result.get_summary_stats()

    def from_visit_result(self, visit_result: VisitAnalysisResult) -> FLWAnalysisResult:
        """
        Aggregate a pre-computed VisitAnalysisResult into FLW rows.

        This enables a pipeline pattern where visit-level analysis is computed
        and cached first, then reused for FLW aggregation without re-fetching.

        Args:
            visit_result: Pre-computed VisitAnalysisResult with VisitRows

        Returns:
            FLWAnalysisResult with one FLWRow per worker

        Example:
            from commcare_connect.labs.analysis import VisitAnalyzer, FLWAnalyzer

            # First, get cached visit-level result
            visit_result = compute_visit_analysis(request, config)

            # Then aggregate to FLW level (no re-fetch needed)
            flw_result = FLWAnalyzer(request, config).from_visit_result(visit_result)
        """

        # Group visit rows by username
        groups: dict[str, list[VisitRow]] = defaultdict(list)
        for row in visit_result.rows:
            key = row.username if self.config.grouping_key == "username" else row.user_id
            groups[key].append(row)

        logger.info(f"Aggregating visits for {len(groups)} FLWs")

        # Compute FLW row for each group
        rows = []
        for group_key, visit_rows in groups.items():
            row = self._compute_flw_row_from_visits(group_key, visit_rows)
            rows.append(row)

        # Sort by total visits descending
        rows.sort(key=lambda r: r.total_visits, reverse=True)

        # Create result
        result = FLWAnalysisResult(
            opportunity_id=visit_result.opportunity_id,
            opportunity_name=visit_result.opportunity_name,
            rows=rows,
            metadata={
                "total_visits": len(visit_result.rows),
                "total_flws": len(rows),
                "grouping_key": self.config.grouping_key,
                "filters_applied": self.config.filters,
                "custom_fields": [f.name for f in self.config.fields],
                "from_visit_result": True,
            },
        )

        logger.info(f"Aggregated FLW analysis: {len(rows)} FLWs from {len(visit_result.rows)} visits")

        return result

    def _compute_flw_row_from_visits(self, group_key: Any, visit_rows: list[VisitRow]) -> FLWRow:
        """
        Compute a single FLW row from pre-computed VisitRows.

        Args:
            group_key: Value of grouping key (username or user_id)
            visit_rows: List of VisitRows for this FLW

        Returns:
            FLWRow with standard and aggregated custom fields
        """
        # Standard fields
        username = visit_rows[0].username if visit_rows else str(group_key)
        user_id = visit_rows[0].user_id if visit_rows else None
        flw_name = username

        # Visit counts by status
        total_visits = len(visit_rows)
        status_counts = defaultdict(int)
        for visit in visit_rows:
            status_counts[visit.status] += 1

        approved_visits = status_counts.get("approved", 0)
        pending_visits = status_counts.get("pending", 0)
        rejected_visits = status_counts.get("rejected", 0)

        # Flagged visits
        flagged_visits = sum(1 for v in visit_rows if v.flagged)

        # Date tracking
        visit_dates = [v.visit_date.date() for v in visit_rows if v.visit_date]
        visit_dates_sorted = sorted(visit_dates)

        first_visit_date = visit_dates_sorted[0] if visit_dates_sorted else None
        last_visit_date = visit_dates_sorted[-1] if visit_dates_sorted else None
        unique_dates = sorted(list(set(visit_dates)))

        # Create row with standard fields
        row = FLWRow(
            username=username,
            user_id=user_id,
            flw_name=flw_name,
            total_visits=total_visits,
            approved_visits=approved_visits,
            pending_visits=pending_visits,
            rejected_visits=rejected_visits,
            flagged_visits=flagged_visits,
            first_visit_date=first_visit_date,
            last_visit_date=last_visit_date,
            dates_active=unique_dates,
        )

        # Aggregate pre-computed custom fields
        if self.config.fields:
            aggregated = self._aggregate_computed_fields(visit_rows)
            row.custom_fields.update(aggregated)

        # Aggregate pre-computed histogram values
        if self.config.histograms:
            histogram_results = self._aggregate_histogram_fields(visit_rows)
            row.custom_fields.update(histogram_results)

        return row

    def _aggregate_computed_fields(self, visit_rows: list[VisitRow]) -> dict[str, Any]:
        """
        Aggregate pre-computed field values from VisitRows.

        Uses the aggregation rules from config to combine values.

        Args:
            visit_rows: List of VisitRows with computed fields

        Returns:
            Dictionary of aggregated field values
        """
        result = {}

        for field_comp in self.config.fields:
            field_name = field_comp.name
            # Collect values from all visits (skip None)
            values = [v.computed.get(field_name) for v in visit_rows if v.computed.get(field_name) is not None]

            if not values:
                result[field_name] = field_comp.default
                continue

            # Apply aggregation
            agg = field_comp.aggregation
            if agg == "sum":
                result[field_name] = sum(values)
            elif agg == "avg":
                result[field_name] = sum(values) / len(values) if values else 0
            elif agg == "count":
                result[field_name] = len(values)
            elif agg == "count_unique":
                result[field_name] = len(set(values))
            elif agg == "min":
                result[field_name] = min(values)
            elif agg == "max":
                result[field_name] = max(values)
            elif agg == "first":
                result[field_name] = values[0]
            elif agg == "last":
                result[field_name] = values[-1]
            elif agg == "list":
                result[field_name] = values
            else:
                # Default to sum for numeric, first for others
                try:
                    result[field_name] = sum(values)
                except TypeError:
                    result[field_name] = values[0] if values else field_comp.default

        return result

    def _aggregate_histogram_fields(self, visit_rows: list[VisitRow]) -> dict[str, Any]:
        """
        Aggregate pre-computed histogram values from VisitRows.

        Histogram raw values are stored in the computed dict with _hist_ prefix
        by the VisitAnalyzer. This method aggregates them into bin counts.

        Args:
            visit_rows: List of VisitRows with computed histogram values

        Returns:
            Dictionary of histogram results (bins, sparkline, mean, count)
        """
        result = {}

        for hist_comp in self.config.histograms:
            # Collect raw histogram values (stored with _hist_ prefix)
            hist_key = f"_hist_{hist_comp.name}"
            values = [v.computed.get(hist_key) for v in visit_rows]

            # Use the aggregation function to build histogram from values
            hist_results = aggregate_histogram_from_values(values, hist_comp)
            result.update(hist_results)

        return result


# Convenience function for quick analysis


def compute_flw_analysis(
    request: HttpRequest, config: AnalysisConfig, use_cache: bool = True, cache_tolerance_minutes: int | None = None
) -> FLWAnalysisResult:
    """
    Compute FLW analysis using the pipeline pattern.

    Pipeline:
    1. Get cached VisitAnalysisResult (or compute if miss)
    2. Check FLW cache - if valid, return cached FLW result
    3. Aggregate VisitRows into FLWRows
    4. Cache FLW result for next time

    This enables reusing the same visit-level computation for both
    FLW aggregation and coverage visualization.

    Cache invalidation:
    - Visit count changes -> invalidate all
    - Config hash changes -> invalidate (automatic via cache key)
    - Manual refresh -> invalidate via ?refresh=1 parameter
    - Optional tolerance for accepting slightly stale cache

    Args:
        request: HttpRequest with labs context
        config: AnalysisConfig defining computations
        use_cache: Whether to use file/Redis cache (default: True)
        cache_tolerance_minutes: Accept cache if age < N minutes (even if counts mismatch)

    Returns:
        FLWAnalysisResult

    Example:
        from commcare_connect.labs.analysis import compute_flw_analysis, AnalysisConfig, FieldComputation

        config = AnalysisConfig(
            grouping_key="username",
            fields=[
                FieldComputation(
                    name="total_muac_measurements",
                    path="form.case.update.soliciter_muac_cm",
                    aggregation="count"
                )
            ]
        )

        result = compute_flw_analysis(request, config)
        for flw in result.rows:
            print(f"{flw.username}: {flw.total_visits} visits")
    """
    from commcare_connect.labs.analysis.base import AnalysisDataAccess
    from commcare_connect.labs.analysis.cache import AnalysisCacheManager
    from commcare_connect.labs.analysis.visit_analyzer import compute_visit_analysis

    opportunity_id = getattr(request, "labs_context", {}).get("opportunity_id")
    force_refresh = request.GET.get("refresh") == "1"

    # Initialize cache manager for FLW results
    cache_manager = AnalysisCacheManager(opportunity_id, config)

    # Extract tolerance from request if not explicitly provided
    if cache_tolerance_minutes is None:
        from commcare_connect.labs.analysis.cache import get_cache_tolerance_from_request

        cache_tolerance_minutes = get_cache_tolerance_from_request(request)

    # Check FLW cache first (fastest path)
    if use_cache and not force_refresh:
        try:
            data_access = AnalysisDataAccess(request)
            current_visit_count = data_access.fetch_visit_count()

            cached_flw = cache_manager.get_results_cache()
            if cached_flw and cache_manager.validate_cache(current_visit_count, cached_flw, cache_tolerance_minutes):
                logger.info(f"Using cached FLW results for opp {opportunity_id}")
                return cached_flw["result"]
        except Exception as e:
            logger.warning(f"Failed to check FLW cache: {e}")

    # Get visit-level analysis (cached or computed)
    # This is the foundation of the pipeline
    logger.info(f"Getting visit analysis for FLW aggregation (opp {opportunity_id})")
    visit_result = compute_visit_analysis(
        request, config, use_cache=use_cache, cache_tolerance_minutes=cache_tolerance_minutes
    )

    # Aggregate to FLW level
    analyzer = FLWAnalyzer(request, config)
    flw_result = analyzer.from_visit_result(visit_result)

    # Cache the FLW results
    if use_cache:
        visit_count = flw_result.metadata.get("total_visits", 0)
        cache_manager.set_results_cache(visit_count, flw_result)
        logger.info(f"Cached FLW results for opp {opportunity_id}")

        # Sync labs_context with actual visit count to prevent future cache misses
        from commcare_connect.labs.analysis.cache import sync_labs_context_visit_count

        sync_labs_context_visit_count(request, visit_count, opportunity_id)

    return flw_result
