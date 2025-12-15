"""
Backend protocol definition for analysis framework.

Defines the interface that all backends must implement.
"""

from collections.abc import Generator
from typing import Any, Protocol

from django.http import HttpRequest

from commcare_connect.labs.analysis.config import AnalysisPipelineConfig
from commcare_connect.labs.analysis.models import FLWAnalysisResult, VisitAnalysisResult


class AnalysisBackend(Protocol):
    """
    Protocol defining the interface for analysis backends.

    Backends handle:
    1. Raw data fetching and caching (from Connect API)
    2. Analysis computation
    3. Result caching
    """

    # -------------------------------------------------------------------------
    # Raw Data Layer
    # -------------------------------------------------------------------------

    def fetch_raw_visits(
        self,
        opportunity_id: int,
        access_token: str,
        expected_visit_count: int | None = None,
        force_refresh: bool = False,
        skip_form_json: bool = False,
        filter_visit_ids: set[int] | None = None,
    ) -> list[dict]:
        """
        Fetch raw visit data. Backend handles caching internally.

        Args:
            opportunity_id: Opportunity ID to fetch visits for
            access_token: OAuth access token for Connect API
            expected_visit_count: Expected visit count for cache validation
            force_refresh: If True, bypass cache and fetch fresh data
            skip_form_json: If True, exclude form_json (slim mode for audit selection)
            filter_visit_ids: If provided, only return visits with these IDs

        Returns:
            List of visit dicts
        """
        ...

    def stream_raw_visits(
        self,
        opportunity_id: int,
        access_token: str,
        expected_visit_count: int | None = None,
        force_refresh: bool = False,
    ) -> Generator[tuple[str, Any], None, None]:
        """
        Stream raw visit data with progress events.

        Yields:
            Tuples of (event_type, event_data):
            - ("cached", visit_dicts) - cache hit, returns data immediately
            - ("progress", bytes_downloaded, total_bytes) - download progress
            - ("complete", visit_dicts) - download complete, returns data

        Args:
            opportunity_id: Opportunity ID to fetch visits for
            access_token: OAuth access token for Connect API
            expected_visit_count: Expected visit count for cache validation
            force_refresh: If True, bypass cache and fetch fresh data
        """
        ...

    def has_valid_raw_cache(self, opportunity_id: int, expected_visit_count: int) -> bool:
        """Check if valid raw cache exists for this opportunity."""
        ...

    # -------------------------------------------------------------------------
    # Analysis Results Layer
    # -------------------------------------------------------------------------

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

    # -------------------------------------------------------------------------
    # Visit Filtering (for Audit)
    # -------------------------------------------------------------------------

    def filter_visits_for_audit(
        self,
        opportunity_id: int,
        access_token: str,
        expected_visit_count: int | None,
        usernames: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        last_n_per_user: int | None = None,
        last_n_total: int | None = None,
        sample_percentage: int = 100,
        return_visit_data: bool = False,
    ) -> list[int] | tuple[list[int], list[dict]]:
        """
        Filter visits based on audit criteria and return matching visit IDs.

        Each backend implements this optimally:
        - SQL backend: Uses database queries with indexes
        - Python/Redis backend: Uses pandas filtering on cached data

        Args:
            opportunity_id: Opportunity to filter visits for
            access_token: OAuth token for cache population if needed
            expected_visit_count: For cache validation
            usernames: Filter to specific FLW usernames (None = all)
            start_date: Filter visits on or after this date (ISO format)
            end_date: Filter visits on or before this date (ISO format)
            last_n_per_user: Take only last N visits per user
            last_n_total: Take only last N visits total
            sample_percentage: Random sample percentage (1-100)
            return_visit_data: If True, also return filtered visit dicts (slim, no form_json)

        Returns:
            List of visit IDs, or (visit_ids, visit_dicts) if return_visit_data=True
        """
        ...

    # -------------------------------------------------------------------------
    # Cache Management
    # -------------------------------------------------------------------------

    def delete_all_cache(self, opportunity_id: int) -> dict[str, int]:
        """
        Delete all cache for an opportunity (all cache types, all configs).

        Args:
            opportunity_id: Opportunity to delete cache for

        Returns:
            Dict with deletion counts: {"raw": count, "computed_visit": count, "computed_flw": count}
        """
        ...

    def delete_config_cache(self, opportunity_id: int, config_hash: str) -> dict[str, int]:
        """
        Delete cache for a specific opportunity and config combination.

        Args:
            opportunity_id: Opportunity to delete cache for
            config_hash: Config hash to delete cache for

        Returns:
            Dict with deletion counts: {"computed_visit": count, "computed_flw": count}
        """
        ...

    def get_cache_stats(self, opportunity_id: int) -> dict[str, dict]:
        """
        Get comprehensive cache statistics for an opportunity.

        Args:
            opportunity_id: Opportunity to get stats for

        Returns:
            Dict with stats for each cache type:
            {
                "raw": {"count": int, "total_size": int, "configs": []},
                "computed_visit": {"count": int, "total_size": int, "configs": [config_hash, ...]},
                "computed_flw": {"count": int, "total_size": int, "configs": [config_hash, ...]}
            }
        """
        ...

    def get_all_opportunities_with_cache(self) -> list[int]:
        """
        Get list of all opportunity IDs that have any cache.

        Returns:
            List of opportunity IDs
        """
        ...

    def get_configs_for_opportunity(self, opportunity_id: int) -> list[str]:
        """
        Get list of config hashes for a specific opportunity.

        Args:
            opportunity_id: Opportunity to get configs for

        Returns:
            List of unique config hashes
        """
        ...

    def get_cache_details(self) -> list[dict]:
        """
        Get comprehensive details about all cache entries.

        Returns:
            List of dicts, each containing:
            {
                "opportunity_id": int,
                "cache_type": str,  # "raw", "computed_visit", or "computed_flw"
                "config_hash": str | None,  # None for raw cache
                "row_count": int,
                "expires_at": datetime,
                "created_at": datetime,
                "visit_count": int
            }
        """
        ...
