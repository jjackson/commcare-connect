"""
Labs Analysis Caching

Multi-tier caching system for analysis results with auto-detected backend.

Cache tiers (in order of preference):
1. LabsRecordCacheManager - Persistent in production DB, cross-user shareable
2. AnalysisCacheManager - Redis (preferred) or file-based pickle cache
3. RawAPICacheManager - Raw API response caching (Redis or file)

Cache invalidation based on:
- Visit count changes (data freshness)
- Config hash changes (analysis approach changes)
"""

import hashlib
import logging
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any

from django.conf import settings
from django.http import HttpRequest

from commcare_connect.labs.analysis.config import AnalysisPipelineConfig

logger = logging.getLogger(__name__)

# Cache directory for local file-based caching
CACHE_DIR = Path(settings.BASE_DIR) / ".analysis_cache"

# TTL for Django cache backend (1 hour)
DJANGO_CACHE_TTL = 3600


# =============================================================================
# Utility Functions
# =============================================================================


def get_config_hash(config: AnalysisPipelineConfig) -> str:
    """
    Generate a hash of the analysis config to detect changes.

    Includes field paths, aggregations, histograms, and filters.
    Changes to any of these will produce a different hash.
    """
    # Build a string representation of the config
    parts = []

    # Add field computations
    for field in config.fields:
        parts.append(f"field:{field.name}:{field.path}:{field.aggregation}")
        # Include transform function bytecode if present (detects lambda changes)
        if field.transform:
            try:
                parts.append(f"transform:{field.transform.__code__.co_code.hex()}")
            except AttributeError:
                parts.append(f"transform:{str(field.transform)}")

    # Add histogram computations
    for hist in config.histograms:
        parts.append(f"hist:{hist.name}:{hist.path}:{hist.lower_bound}:{hist.upper_bound}:{hist.num_bins}")
        if hist.transform:
            try:
                parts.append(f"hist_transform:{hist.transform.__code__.co_code.hex()}")
            except AttributeError:
                parts.append(f"hist_transform:{str(hist.transform)}")

    # Add filters
    for key, value in sorted(config.filters.items()):
        parts.append(f"filter:{key}:{value}")

    # Add grouping key
    parts.append(f"grouping:{config.grouping_key}")

    # Generate hash
    config_str = "|".join(parts)
    return hashlib.md5(config_str.encode()).hexdigest()[:12]


def _use_django_cache() -> bool:
    """
    Determine if we should use Django cache (Redis) or file cache.

    Prefers Django cache (Redis) whenever it's available and working.
    Falls back to file-based cache only if Redis is unavailable.
    """
    # Always try Redis first (works in labs AND local dev if Redis is running)
    try:
        from django.core.cache import cache

        # Test if cache backend is working
        test_key = "_cache_backend_test"
        test_value = "test_value"
        cache.set(test_key, test_value, 1)
        result = cache.get(test_key)

        if result == test_value:
            logger.debug("Using Django cache backend (Redis)")
            cache.delete(test_key)  # Clean up test key
            return True
        else:
            logger.debug("Django cache test failed - value mismatch")
    except Exception as e:
        logger.debug(f"Django cache not available: {e}")

    # Fall back to file-based cache
    logger.debug("Using file-based cache")
    return False


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


def clear_all_analysis_caches() -> int:
    """
    Clear all file-based analysis caches.

    Returns:
        Number of cache files deleted
    """
    if not CACHE_DIR.exists():
        return 0

    count = 0
    for cache_file in CACHE_DIR.glob("*.pkl"):
        try:
            cache_file.unlink()
            count += 1
        except Exception as e:
            logger.warning(f"Failed to delete {cache_file}: {e}")

    logger.info(f"Cleared {count} analysis cache files")
    return count


# =============================================================================
# Cache Managers
# =============================================================================


class AnalysisCacheManager:
    """
    Manages multi-level caching for analysis results.

    Levels:
    - Level 1: Extracted visit data (allows re-aggregation)
    - Level 2: Visit-level results (VisitAnalysisResult)
    - Level 3: Aggregated FLW results (FLWAnalysisResult)

    Backend is auto-selected based on availability:
    - If Redis is available: Django cache (Redis) - preferred
    - If Redis is unavailable: File pickle cache - fallback
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
        self.use_django = _use_django_cache()

        logger.debug(
            f"AnalysisCacheManager initialized: opp={opportunity_id}, "
            f"hash={self.config_hash}, backend={'django' if self.use_django else 'file'}"
        )

    def _get_cache_key(self, level: str) -> str:
        """Generate cache key for a given level."""
        return f"analysis_{self.opportunity_id}_{self.config_hash}_{level}"

    def _get_file_path(self, level: str) -> Path:
        """Get file path for file-based cache."""
        return CACHE_DIR / f"{self.opportunity_id}_{self.config_hash}_{level}.pkl"

    # -------------------------------------------------------------------------
    # Django Cache Backend
    # -------------------------------------------------------------------------

    def _django_get(self, key: str) -> Any | None:
        """Get from Django cache."""
        from django.core.cache import cache

        try:
            return cache.get(key)
        except Exception as e:
            logger.warning(f"Django cache get failed for {key}: {e}")
            return None

    def _django_set(self, key: str, value: Any) -> bool:
        """Set in Django cache with TTL."""
        from django.core.cache import cache

        try:
            cache.set(key, value, DJANGO_CACHE_TTL)
            return True
        except Exception as e:
            logger.warning(f"Django cache set failed for {key}: {e}")
            return False

    def _django_delete(self, key: str) -> bool:
        """Delete from Django cache."""
        from django.core.cache import cache

        try:
            cache.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Django cache delete failed for {key}: {e}")
            return False

    # -------------------------------------------------------------------------
    # File Cache Backend
    # -------------------------------------------------------------------------

    def _file_get(self, path: Path) -> Any | None:
        """Get from file cache."""
        if not path.exists():
            return None
        try:
            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            logger.warning(f"File cache read failed for {path}: {e}")
            return None

    def _file_set(self, path: Path, value: Any) -> bool:
        """Set in file cache."""
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with open(path, "wb") as f:
                pickle.dump(value, f)
            return True
        except Exception as e:
            logger.warning(f"File cache write failed for {path}: {e}")
            return False

    def _file_delete(self, path: Path) -> bool:
        """Delete from file cache."""
        try:
            if path.exists():
                path.unlink()
            return True
        except Exception as e:
            logger.warning(f"File cache delete failed for {path}: {e}")
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
        key = self._get_cache_key("visits")
        if self.use_django:
            return self._django_get(key)
        else:
            return self._file_get(self._get_file_path("visits"))

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
        key = self._get_cache_key("visits")
        if self.use_django:
            return self._django_set(key, data)
        else:
            return self._file_set(self._get_file_path("visits"), data)

    def get_visit_results_cache(self) -> dict | None:
        """
        Get cached visit-level results.

        Returns:
            Dict with 'visit_count', 'cached_at', 'result' or None if not cached
        """
        key = self._get_cache_key("visit_results")
        if self.use_django:
            return self._django_get(key)
        else:
            return self._file_get(self._get_file_path("visit_results"))

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
        key = self._get_cache_key("visit_results")
        if self.use_django:
            return self._django_set(key, data)
        else:
            return self._file_set(self._get_file_path("visit_results"), data)

    def get_results_cache(self) -> dict | None:
        """
        Get cached aggregated FLW results.

        Returns:
            Dict with 'visit_count', 'cached_at', 'result' or None if not cached
        """
        key = self._get_cache_key("results")
        if self.use_django:
            return self._django_get(key)
        else:
            return self._file_get(self._get_file_path("results"))

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
        key = self._get_cache_key("results")
        if self.use_django:
            return self._django_set(key, data)
        else:
            return self._file_set(self._get_file_path("results"), data)

    def clear_cache(self) -> None:
        """Clear all cache levels for this opportunity/config."""
        for level in ["visits", "visit_results", "results"]:
            key = self._get_cache_key(level)
            if self.use_django:
                self._django_delete(key)
            else:
                self._file_delete(self._get_file_path(level))

        logger.info(f"Cleared cache for opp={self.opportunity_id}, hash={self.config_hash}")

    def validate_cache(
        self, current_visit_count: int, cached_data: dict, tolerance_minutes: int | None = None
    ) -> bool:
        """
        Validate cached data with optional time-based tolerance.

        Validation rules:
        1. If visit counts match -> VALID (always)
        2. If tolerance_minutes is None -> check must match exactly
        3. If tolerance_minutes is set:
           - If cache age < tolerance_minutes -> VALID (accept stale data)
           - Otherwise -> INVALID

        Args:
            current_visit_count: Current visit count from API
            cached_data: Cached data dict with 'visit_count' and 'cached_at'
            tolerance_minutes: Max age (in minutes) to accept mismatched counts

        Returns:
            True if cache is valid, False if stale
        """
        if not cached_data:
            return False

        cached_count = cached_data.get("visit_count", 0)

        # Perfect match - always valid
        if cached_count == current_visit_count:
            logger.debug(f"Cache valid: counts match ({cached_count})")
            return True

        # Count mismatch - check tolerance
        if tolerance_minutes is None:
            logger.info(f"Cache invalid: cached={cached_count}, current={current_visit_count}, no tolerance")
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
                    f"Cache ACCEPTED with tolerance: "
                    f"cached={cached_count}, current={current_visit_count}, "
                    f"age={age_minutes:.1f}min, tolerance={tolerance_minutes}min"
                )
                return True
            else:
                logger.info(
                    f"Cache REJECTED (too old): "
                    f"cached={cached_count}, current={current_visit_count}, "
                    f"age={age_minutes:.1f}min > tolerance={tolerance_minutes}min"
                )
                return False
        except Exception as e:
            logger.warning(f"Failed to parse cache timestamp: {e}")
            return False


class RawAPICacheManager:
    """
    Caching for raw API responses (like user_visits CSV data).

    Uses the same backend detection as AnalysisCacheManager:
    - Prefers Django cache (Redis) when available
    - Falls back to file-based pickle cache

    Cache invalidation based on visit count changes.
    """

    def __init__(self, opportunity_id: int):
        """
        Initialize cache for an opportunity.

        Args:
            opportunity_id: Opportunity ID for cache scoping
        """
        self.opportunity_id = opportunity_id
        self.use_django = _use_django_cache()

        logger.debug(
            f"RawAPICacheManager initialized: opp={opportunity_id}, "
            f"backend={'django' if self.use_django else 'file'}"
        )

    def _get_cache_key(self, api_endpoint: str) -> str:
        """Generate cache key for an API endpoint."""
        # Clean endpoint to make it filesystem-safe
        endpoint_clean = api_endpoint.replace("/", "_").replace(":", "")
        return f"raw_api_{self.opportunity_id}_{endpoint_clean}"

    def _get_file_path(self, api_endpoint: str) -> Path:
        """Get file path for file-based cache."""
        endpoint_clean = api_endpoint.replace("/", "_").replace(":", "")
        return CACHE_DIR / f"raw_api_{self.opportunity_id}_{endpoint_clean}.pkl"

    def get(self, api_endpoint: str) -> dict | None:
        """
        Get cached API response.

        Args:
            api_endpoint: API endpoint (e.g., "user_visits")

        Returns:
            Dict with 'visit_count', 'cached_at', 'data' or None if not cached
        """
        key = self._get_cache_key(api_endpoint)
        if self.use_django:
            from django.core.cache import cache

            try:
                return cache.get(key)
            except Exception as e:
                logger.warning(f"Django cache get failed for {key}: {e}")
                return None
        else:
            path = self._get_file_path(api_endpoint)
            if not path.exists():
                return None
            try:
                with open(path, "rb") as f:
                    return pickle.load(f)
            except Exception as e:
                logger.warning(f"File cache read failed for {path}: {e}")
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
        if self.use_django:
            from django.core.cache import cache

            try:
                cache.set(key, cache_data, DJANGO_CACHE_TTL)
                logger.info(f"Cached API response: {api_endpoint} for opp {self.opportunity_id}")
                return True
            except Exception as e:
                logger.warning(f"Django cache set failed for {key}: {e}")
                return False
        else:
            path = self._get_file_path(api_endpoint)
            try:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                with open(path, "wb") as f:
                    pickle.dump(cache_data, f)
                logger.info(f"Cached API response: {api_endpoint} for opp {self.opportunity_id}")
                return True
            except Exception as e:
                logger.warning(f"File cache write failed for {path}: {e}")
                return False

    def is_valid(self, cached_data: dict | None, current_visit_count: int | None = None) -> bool:
        """
        Check if cached data is still valid.

        Args:
            cached_data: Cached data dict
            current_visit_count: Current visit count for validation (optional)

        Returns:
            True if cache is valid
        """
        if not cached_data:
            return False

        # If no visit count validation needed, cache is valid
        if current_visit_count is None:
            return True

        # If cache has visit count, it must match
        cached_count = cached_data.get("visit_count")
        if cached_count is not None:
            if cached_count != current_visit_count:
                logger.info(f"Cache invalid: cached_count={cached_count}, current_count={current_visit_count}")
                return False

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
        if self.use_django:
            from django.core.cache import cache

            try:
                cache.delete(key)
                return True
            except Exception as e:
                logger.warning(f"Django cache delete failed for {key}: {e}")
                return False
        else:
            path = self._get_file_path(api_endpoint)
            try:
                if path.exists():
                    path.unlink()
                return True
            except Exception as e:
                logger.warning(f"File cache delete failed for {path}: {e}")
                return False


class LabsRecordCacheManager:
    """
    Cache backend using LabsRecord API for persistent cross-session storage.

    Third-tier cache after Redis and file:
    - Redis: Fast, in-memory, TTL-based (1 hour)
    - File: Local disk, survives restarts
    - LabsRecord: Persistent in production DB, cross-user shareable

    Uses the LabsRecordAPIClient to store/retrieve serialized analysis results.
    Cache entries are identified by experiment + analysis_type + opportunity_id.

    Cache invalidation is based on visit_count stored in the record metadata.
    """

    def __init__(self, request: HttpRequest, experiment: str):
        """
        Initialize LabsRecord cache.

        Args:
            request: HttpRequest with labs OAuth and context
            experiment: Experiment name (e.g., "chc_nutrition", "coverage")
        """
        self.request = request
        self.experiment = experiment
        self.access_token = request.session.get("labs_oauth", {}).get("access_token")
        self.labs_context = getattr(request, "labs_context", {})
        self.opportunity_id = self.labs_context.get("opportunity_id")

        logger.debug(f"LabsRecordCacheManager initialized: experiment={experiment}, opp={self.opportunity_id}")

    def _get_api_client(self):
        """Get LabsRecordAPIClient instance."""
        from commcare_connect.labs.integrations.connect.api_client import LabsRecordAPIClient

        return LabsRecordAPIClient(
            access_token=self.access_token,
            opportunity_id=self.opportunity_id,
        )

    def get(self, analysis_type: str) -> dict | None:
        """
        Load cached result from LabsRecord.

        Args:
            analysis_type: Type of analysis (e.g., "flw_analysis", "visit_analysis")

        Returns:
            Dict with 'visit_count', 'cached_at', 'result' or None if not found
        """
        if not self.access_token or not self.opportunity_id:
            logger.debug("LabsRecordCacheManager.get() skipped - missing auth or context")
            return None

        try:
            client = self._get_api_client()
            records = client.get_records(
                experiment=self.experiment,
                type=f"cache_{analysis_type}",
            )

            if not records:
                logger.info(
                    f"LabsRecordCacheManager MISS: no record for {self.experiment}/{analysis_type} "
                    f"(opp {self.opportunity_id})"
                )
                return None

            # Get the most recent record
            record = records[0]
            data = record.data

            logger.info(
                f"LabsRecordCacheManager HIT: found record for {self.experiment}/{analysis_type} "
                f"(opp {self.opportunity_id}, visit_count={data.get('visit_count')})"
            )

            return data

        except Exception as e:
            logger.warning(f"LabsRecordCacheManager.get() failed: {e}")
            return None

    def set(self, analysis_type: str, result: Any, visit_count: int) -> bool:
        """
        Save result to LabsRecord.

        Args:
            analysis_type: Type of analysis (e.g., "flw_analysis", "visit_analysis")
            result: Analysis result object to cache
            visit_count: Visit count for cache invalidation

        Returns:
            True if saved successfully
        """
        if not self.access_token or not self.opportunity_id:
            logger.debug("LabsRecordCacheManager.set() skipped - missing auth or context")
            return False

        try:
            # Serialize the result
            cache_data = {
                "visit_count": visit_count,
                "cached_at": datetime.utcnow().isoformat(),
                "result": result.to_dict() if hasattr(result, "to_dict") else result,
            }

            client = self._get_api_client()

            # Check if record already exists
            existing = client.get_records(
                experiment=self.experiment,
                type=f"cache_{analysis_type}",
            )

            if existing:
                # Update existing record
                record = existing[0]
                client.update_record(
                    record_id=record.id,
                    experiment=self.experiment,
                    type=f"cache_{analysis_type}",
                    data=cache_data,
                )
                logger.info(
                    f"LabsRecordCacheManager updated: {self.experiment}/{analysis_type} "
                    f"(opp {self.opportunity_id}, visit_count={visit_count})"
                )
            else:
                # Create new record
                client.create_record(
                    experiment=self.experiment,
                    type=f"cache_{analysis_type}",
                    data=cache_data,
                )
                logger.info(
                    f"LabsRecordCacheManager created: {self.experiment}/{analysis_type} "
                    f"(opp {self.opportunity_id}, visit_count={visit_count})"
                )

            return True

        except Exception as e:
            logger.warning(f"LabsRecordCacheManager.set() failed: {e}")
            return False

    def is_valid(self, cached_data: dict | None, current_visit_count: int | None = None) -> bool:
        """
        Check if cached data is still valid based on visit count.

        Args:
            cached_data: Cached data dict from get()
            current_visit_count: Current visit count for validation

        Returns:
            True if cache is valid
        """
        if not cached_data:
            return False

        # If no visit count validation needed, cache is valid
        if current_visit_count is None:
            return True

        # Visit count must match
        cached_count = cached_data.get("visit_count")
        if cached_count is not None and cached_count != current_visit_count:
            logger.info(
                f"LabsRecordCacheManager invalid: cached_count={cached_count}, " f"current_count={current_visit_count}"
            )
            return False

        return True

    def clear(self, analysis_type: str) -> bool:
        """
        Clear cached record for an analysis type.

        Args:
            analysis_type: Type of analysis to clear

        Returns:
            True if cleared successfully
        """
        if not self.access_token or not self.opportunity_id:
            return False

        try:
            client = self._get_api_client()
            records = client.get_records(
                experiment=self.experiment,
                type=f"cache_{analysis_type}",
            )

            if records:
                record_ids = [r.id for r in records]
                client.delete_records(record_ids)
                logger.info(
                    f"LabsRecordCacheManager cleared: {self.experiment}/{analysis_type} "
                    f"(opp {self.opportunity_id}, deleted {len(record_ids)} records)"
                )

            return True

        except Exception as e:
            logger.warning(f"LabsRecordCacheManager.clear() failed: {e}")
            return False


# =============================================================================
# Backwards Compatibility Aliases
# =============================================================================

# Old names for backwards compatibility
RawAPICache = RawAPICacheManager
LabsRecordCache = LabsRecordCacheManager
