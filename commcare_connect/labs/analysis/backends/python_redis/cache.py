"""
Redis caching for python_redis backend.

Uses Django cache (Redis) for analysis results.

Cache tiers:
1. AnalysisCacheManager - Analysis results with config-based keys
2. RawAPICacheManager - Raw API response caching

Cache invalidation based on:
- Visit count changes (data freshness)
- Config hash changes (analysis approach changes)
"""

import logging
from datetime import datetime
from typing import Any

from django.core.cache import cache
from django.http import HttpRequest

from commcare_connect.labs.analysis.config import AnalysisPipelineConfig
from commcare_connect.labs.analysis.utils import DJANGO_CACHE_TTL, get_config_hash

logger = logging.getLogger(__name__)


# =============================================================================
# Request Utility Functions
# =============================================================================


def sync_labs_context_visit_count(request: HttpRequest, visit_count: int, opportunity_id: int | None = None) -> None:
    """
    Sync visit count to labs_context and session after computing analysis.

    This ensures future cache checks use the correct visit count, preventing
    unnecessary cache misses when the labs_context was loaded with stale data.

    Updates both:
    - request.labs_context["opportunity"]["visit_count"]
    - request.session["labs_context"]["opportunity"]["visit_count"]

    Args:
        request: HttpRequest with labs_context
        visit_count: Actual visit count from computed analysis
        opportunity_id: Opportunity ID for logging (optional)
    """
    if not hasattr(request, "labs_context") or not request.labs_context.get("opportunity"):
        return

    old_count = request.labs_context["opportunity"].get("visit_count", 0)
    if old_count == visit_count:
        return  # No change needed

    logger.info(f"[Cache] Syncing labs_context visit count: {old_count} -> {visit_count} (opp {opportunity_id})")

    # Update the current request's labs_context
    request.labs_context["opportunity"]["visit_count"] = visit_count

    # Also update the session's OAuth data so it persists across requests
    # The middleware rebuilds labs_context from session["labs_oauth"]["organization_data"]["opportunities"]
    # so we need to update the source there
    if hasattr(request, "session") and "labs_oauth" in request.session:
        labs_oauth = request.session["labs_oauth"]
        org_data = labs_oauth.get("organization_data", {})
        opportunities = org_data.get("opportunities", [])

        target_opp_id = opportunity_id or request.labs_context.get("opportunity_id")
        for opp in opportunities:
            if opp.get("id") == target_opp_id:
                opp["visit_count"] = visit_count
                # Mark session as modified if it's a real Django session
                if hasattr(request.session, "modified"):
                    request.session.modified = True
                logger.debug(f"[Cache] Updated session OAuth data with visit_count={visit_count}")
                break


def get_cache_tolerance_from_request(request: HttpRequest) -> int | None:
    """
    Extract cache_tolerance from URL parameters.

    Looks for ?cache_tolerance=N where N is minutes.

    Args:
        request: HttpRequest with GET parameters

    Returns:
        Tolerance in minutes or None if not specified

    Example:
        # In view:
        tolerance = get_cache_tolerance_from_request(request)
        result = compute_visit_analysis(request, config, cache_tolerance_minutes=tolerance)
    """
    try:
        tolerance_str = request.GET.get("cache_tolerance")
        if tolerance_str:
            tolerance = int(tolerance_str)
            if tolerance < 0:
                logger.warning(f"Invalid cache_tolerance={tolerance}, must be >= 0")
                return None
            logger.info(f"Using cache tolerance: {tolerance} minutes from URL parameter")
            return tolerance
    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to parse cache_tolerance parameter: {e}")

    return None


def get_cache_tolerance_pct_from_request(request: HttpRequest) -> float | None:
    """
    Extract cache_tolerance_pct from URL parameters.

    Looks for ?cache_tolerance_pct=N where N is a percentage (0-100).
    For example, cache_tolerance_pct=98 means accept cache if it has at least 98% of expected visits.

    Args:
        request: HttpRequest with GET parameters

    Returns:
        Tolerance percentage (0-100) or None if not specified

    Example:
        # In view:
        tolerance_pct = get_cache_tolerance_pct_from_request(request)
        result = compute_visit_analysis(request, config, cache_tolerance_pct=tolerance_pct)

        # URL usage: ?cache_tolerance_pct=98
        # If expected visits = 1000 and cache has 980, cache is valid (980/1000 = 98%)
    """
    try:
        tolerance_str = request.GET.get("cache_tolerance_pct")
        if tolerance_str:
            tolerance = float(tolerance_str)
            if tolerance < 0 or tolerance > 100:
                logger.warning(f"Invalid cache_tolerance_pct={tolerance}, must be 0-100")
                return None
            logger.info(f"Using cache tolerance: {tolerance}% from URL parameter")
            return tolerance
    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to parse cache_tolerance_pct parameter: {e}")

    return None


# =============================================================================
# Cache Managers
# =============================================================================


class AnalysisCacheManager:
    """
    Manages caching for analysis results using Django cache (Redis).

    Levels:
    - Level 1: Extracted visit data (allows re-aggregation)
    - Level 2: Visit-level results (VisitAnalysisResult)
    - Level 3: Aggregated FLW results (FLWAnalysisResult)
    """

    def __init__(self, opportunity_id: int, config: AnalysisPipelineConfig):
        """
        Initialize cache manager.

        Args:
            opportunity_id: Opportunity ID for cache scoping
            config: AnalysisPipelineConfig for hash generation
        """
        self.opportunity_id = opportunity_id
        self.config = config
        self.config_hash = get_config_hash(config)

        logger.debug(f"AnalysisCacheManager initialized: opp={opportunity_id}, hash={self.config_hash}")

    def _get_cache_key(self, level: str) -> str:
        """Generate cache key for a given level."""
        return f"analysis_{self.opportunity_id}_{self.config_hash}_{level}"

    def _cache_get(self, key: str) -> Any | None:
        """Get from Django cache."""
        try:
            return cache.get(key)
        except Exception as e:
            logger.warning(f"Cache get failed for {key}: {e}")
            return None

    def _cache_set(self, key: str, value: Any) -> bool:
        """Set in Django cache with TTL."""
        try:
            cache.set(key, value, DJANGO_CACHE_TTL)
            return True
        except Exception as e:
            logger.warning(f"Cache set failed for {key}: {e}")
            return False

    def _cache_delete(self, key: str) -> bool:
        """Delete from Django cache."""
        try:
            cache.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Cache delete failed for {key}: {e}")
            return False

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def get_visits_cache(self) -> dict | None:
        """
        Get cached extracted visit data (Level 1).

        Returns:
            Dict with 'visit_count', 'cached_at', 'visits' or None if not cached
        """
        return self._cache_get(self._get_cache_key("visits"))

    def set_visits_cache(self, visit_count: int, visits: list[dict]) -> bool:
        """
        Cache extracted visit data (Level 1).

        Args:
            visit_count: Total visit count for validation
            visits: List of extracted visit dicts

        Returns:
            True if cached successfully
        """
        data = {
            "visit_count": visit_count,
            "cached_at": datetime.utcnow().isoformat(),
            "visits": visits,
        }
        return self._cache_set(self._get_cache_key("visits"), data)

    def get_visit_results_cache(self) -> dict | None:
        """
        Get cached visit-level results.

        Returns:
            Dict with 'visit_count', 'cached_at', 'result' or None if not cached
        """
        return self._cache_get(self._get_cache_key("visit_results"))

    def set_visit_results_cache(self, visit_count: int, result: Any) -> bool:
        """
        Cache visit-level results (VisitAnalysisResult).

        Args:
            visit_count: Total visit count for validation
            result: VisitAnalysisResult object

        Returns:
            True if cached successfully
        """
        data = {
            "visit_count": visit_count,
            "cached_at": datetime.utcnow().isoformat(),
            "result": result,
        }
        return self._cache_set(self._get_cache_key("visit_results"), data)

    def get_results_cache(self) -> dict | None:
        """
        Get cached aggregated FLW results.

        Returns:
            Dict with 'visit_count', 'cached_at', 'result' or None if not cached
        """
        return self._cache_get(self._get_cache_key("results"))

    def set_results_cache(self, visit_count: int, result: Any) -> bool:
        """
        Cache aggregated FLW results (FLWAnalysisResult).

        Args:
            visit_count: Total visit count for validation
            result: FLWAnalysisResult object

        Returns:
            True if cached successfully
        """
        data = {
            "visit_count": visit_count,
            "cached_at": datetime.utcnow().isoformat(),
            "result": result,
        }
        return self._cache_set(self._get_cache_key("results"), data)

    def clear_cache(self) -> None:
        """Clear all cache levels for this opportunity/config."""
        for level in ["visits", "visit_results", "results"]:
            self._cache_delete(self._get_cache_key(level))

        logger.info(f"Cleared cache for opp={self.opportunity_id}, hash={self.config_hash}")

    def validate_cache(
        self,
        current_visit_count: int,
        cached_data: dict,
        tolerance_minutes: int | None = None,
        tolerance_pct: float | None = None,
    ) -> bool:
        """
        Validate cached data with optional time-based or percentage-based tolerance.

        Validation rules:
        1. If cached_count >= current_visit_count -> VALID (cache has at least as much data)
        2. If tolerance_pct is set and (cached_count / current_visit_count * 100) >= tolerance_pct -> VALID
        3. If tolerance_minutes is set and cache age < tolerance_minutes -> VALID (accept stale data)
        4. Otherwise -> INVALID

        Note: We use >= instead of == because sometimes the API returns more visits
        than what's reported in the opportunity metadata (opp_org_opp endpoint).

        Args:
            current_visit_count: Expected visit count from labs_context
            cached_data: Cached data dict with 'visit_count' and 'cached_at'
            tolerance_minutes: Max age (in minutes) to accept mismatched counts
            tolerance_pct: Min percentage (0-100) of expected visits to accept cache
                           e.g., 98 means accept if cache has >= 98% of expected visits

        Returns:
            True if cache is valid, False if stale
        """
        if not cached_data:
            return False

        cached_count = cached_data.get("visit_count", 0)

        # Cache has at least as much data as expected - valid
        if cached_count >= current_visit_count:
            logger.debug(f"Cache valid: cached={cached_count} >= expected={current_visit_count}")
            return True

        # Cache has fewer visits than expected - check percentage tolerance first
        if tolerance_pct is not None and current_visit_count > 0:
            actual_pct = (cached_count / current_visit_count) * 100
            if actual_pct >= tolerance_pct:
                logger.info(
                    f"Cache ACCEPTED with percentage tolerance: "
                    f"cached={cached_count}, expected={current_visit_count}, "
                    f"actual={actual_pct:.1f}%, tolerance={tolerance_pct}%"
                )
                return True
            else:
                logger.debug(
                    f"Cache percentage check failed: " f"actual={actual_pct:.1f}% < tolerance={tolerance_pct}%"
                )

        # Check time-based tolerance
        if tolerance_minutes is None:
            logger.info(f"Cache invalid: cached={cached_count} < expected={current_visit_count}, no tolerance")
            return False

        # Check cache age
        cached_at_str = cached_data.get("cached_at")
        if not cached_at_str:
            logger.warning("Cache has no 'cached_at' timestamp, cannot apply tolerance")
            return False

        try:
            cached_at = datetime.fromisoformat(cached_at_str)
            age = datetime.utcnow() - cached_at
            age_minutes = age.total_seconds() / 60

            if age_minutes <= tolerance_minutes:
                logger.info(
                    f"Cache ACCEPTED with time tolerance: "
                    f"cached={cached_count}, expected={current_visit_count}, "
                    f"age={age_minutes:.1f}min, tolerance={tolerance_minutes}min"
                )
                return True
            else:
                logger.info(
                    f"Cache REJECTED (too old): "
                    f"cached={cached_count}, expected={current_visit_count}, "
                    f"age={age_minutes:.1f}min > tolerance={tolerance_minutes}min"
                )
                return False
        except Exception as e:
            logger.warning(f"Failed to parse cache timestamp: {e}")
            return False


class RawAPICacheManager:
    """
    Caching for raw API responses (like user_visits CSV data).

    Uses Django cache (Redis) with visit count-based invalidation.
    """

    def __init__(self, opportunity_id: int):
        """
        Initialize cache for an opportunity.

        Args:
            opportunity_id: Opportunity ID for cache scoping
        """
        self.opportunity_id = opportunity_id

        logger.debug(f"RawAPICacheManager initialized: opp={opportunity_id}")

    def _get_cache_key(self, api_endpoint: str) -> str:
        """Generate cache key for an API endpoint."""
        # Clean endpoint to make it filesystem-safe
        endpoint_clean = api_endpoint.replace("/", "_").replace(":", "")
        return f"raw_api_{self.opportunity_id}_{endpoint_clean}"

    def get(self, api_endpoint: str) -> dict | None:
        """
        Get cached API response.

        Args:
            api_endpoint: API endpoint (e.g., "user_visits")

        Returns:
            Dict with 'visit_count', 'cached_at', 'data' or None if not cached
        """
        key = self._get_cache_key(api_endpoint)
        try:
            return cache.get(key)
        except Exception as e:
            logger.warning(f"Cache get failed for {key}: {e}")
            return None

    def set(self, api_endpoint: str, data: Any, visit_count: int | None = None) -> bool:
        """
        Cache API response.

        Args:
            api_endpoint: API endpoint (e.g., "user_visits")
            data: Response data to cache
            visit_count: Optional visit count for invalidation

        Returns:
            True if cached successfully
        """
        cache_data = {
            "cached_at": datetime.utcnow().isoformat(),
            "data": data,
        }
        if visit_count is not None:
            cache_data["visit_count"] = visit_count

        key = self._get_cache_key(api_endpoint)
        try:
            cache.set(key, cache_data, DJANGO_CACHE_TTL)
            logger.info(f"Cached API response: {api_endpoint} for opp {self.opportunity_id}")
            return True
        except Exception as e:
            logger.warning(f"Cache set failed for {key}: {e}")
            return False

    def is_valid(self, cached_data: dict | None, current_visit_count: int | None = None) -> bool:
        """
        Check if cached data is still valid.

        Cache is valid if cached_count >= expected_count, because sometimes
        the API returns more visits than what's reported in opportunity metadata.

        Args:
            cached_data: Cached data dict
            current_visit_count: Expected visit count for validation (optional)

        Returns:
            True if cache is valid
        """
        if not cached_data:
            return False

        # If no visit count validation needed, cache is valid
        if current_visit_count is None:
            return True

        # If cache has visit count, it must be >= expected
        cached_count = cached_data.get("visit_count")
        if cached_count is not None:
            if cached_count < current_visit_count:
                logger.info(f"Cache invalid: cached_count={cached_count} < expected={current_visit_count}")
                return False
            else:
                logger.debug(f"Cache valid: cached_count={cached_count} >= expected={current_visit_count}")

        return True

    def clear(self, api_endpoint: str) -> bool:
        """
        Clear cached response for an endpoint.

        Args:
            api_endpoint: API endpoint to clear

        Returns:
            True if cleared successfully
        """
        key = self._get_cache_key(api_endpoint)
        try:
            cache.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Cache delete failed for {key}: {e}")
            return False


# =============================================================================
# Cache Management Methods (TODO: Implement for Protocol Compliance)
# =============================================================================

# TODO: Implement the following class methods to match the AnalysisBackend protocol:
#
# @classmethod
# def delete_all_cache(cls, opportunity_id: int) -> dict[str, int]:
#     """Delete all cache for an opportunity (all cache types, all configs)."""
#     # Implementation needed: Clear all Redis cache keys for this opportunity
#     pass
#
# @classmethod
# def delete_config_cache(cls, opportunity_id: int, config_hash: str) -> dict[str, int]:
#     """Delete cache for a specific opportunity and config combination."""
#     # Implementation needed: Clear Redis cache keys for this opp + config
#     pass
#
# @classmethod
# def get_cache_stats(cls, opportunity_id: int) -> dict[str, dict]:
#     """Get comprehensive cache statistics for an opportunity."""
#     # Implementation needed: Query Redis for cache stats
#     pass
#
# @classmethod
# def get_all_opportunities_with_cache(cls) -> list[int]:
#     """Get list of all opportunity IDs that have any cache."""
#     # Implementation needed: Scan Redis keys to find all opportunity IDs
#     pass
#
# @classmethod
# def get_configs_for_opportunity(cls, opportunity_id: int) -> list[str]:
#     """Get list of config hashes for a specific opportunity."""
#     # Implementation needed: Scan Redis keys for this opportunity
#     pass
#
# @classmethod
# def get_cache_details(cls) -> list[dict]:
#     """Get comprehensive details about all cache entries."""
#     # Implementation needed: Scan all Redis cache keys and return details
#     pass
