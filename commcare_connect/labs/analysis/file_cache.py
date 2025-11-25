"""
Two-level analysis caching with environment-aware backend.

- Labs server: Uses Django cache (Redis)
- Local dev: Uses file-based pickle cache

Cache invalidation based on:
- Visit count changes (data freshness)
- Config hash changes (analysis approach changes)
"""

import hashlib
import logging
import os
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any

from django.conf import settings

from commcare_connect.labs.analysis.config import AnalysisConfig

logger = logging.getLogger(__name__)

# Cache directory for local file-based caching
CACHE_DIR = Path(settings.BASE_DIR) / ".analysis_cache"

# TTL for Django cache backend (1 hour)
DJANGO_CACHE_TTL = 3600


def get_config_hash(config: AnalysisConfig) -> str:
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
    """Determine if we should use Django cache (Redis) or file cache."""
    # Use Django cache if in labs environment
    if getattr(settings, "IS_LABS_ENVIRONMENT", False):
        return True

    # Also use Django cache if Redis is available and working
    try:
        from django.core.cache import cache

        cache.set("_test_key", "test", 1)
        if cache.get("_test_key") == "test":
            return True
    except Exception:
        pass

    return False


class AnalysisCacheManager:
    """
    Manages two-level caching for analysis results.

    Level 1: Extracted visit data (allows re-aggregation)
    Level 2: Aggregated FLW results (fastest load)

    Backend is auto-selected based on environment:
    - Labs: Django cache (Redis)
    - Local: File pickle cache
    """

    def __init__(self, opportunity_id: int, config: AnalysisConfig):
        """
        Initialize cache manager.

        Args:
            opportunity_id: Opportunity ID for cache scoping
            config: AnalysisConfig for hash generation
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

    def validate_cache(self, current_visit_count: int, cached_data: dict) -> bool:
        """
        Validate cached data against current visit count.

        Args:
            current_visit_count: Current visit count from API
            cached_data: Cached data dict with 'visit_count' key

        Returns:
            True if cache is valid, False if stale
        """
        if not cached_data:
            return False

        cached_count = cached_data.get("visit_count", 0)
        is_valid = cached_count == current_visit_count

        if not is_valid:
            logger.info(f"Cache invalid: cached={cached_count}, current={current_visit_count}")

        return is_valid


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
