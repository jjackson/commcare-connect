"""
Session caching utilities for analysis results.

Uses pickle + base64 encoding to store results in Django sessions.
Similar pattern to coverage app's caching.
"""

import base64
import logging
import pickle
from typing import Any

from django.http import HttpRequest

from commcare_connect.labs.analysis.models import AnalysisResult

logger = logging.getLogger(__name__)


class SessionCacheManager:
    """
    Manages session-based caching of analysis results.

    Uses pickle serialization with base64 encoding for session storage.
    """

    @staticmethod
    def get_cached(request: HttpRequest, cache_key: str) -> AnalysisResult | None:
        """
        Get cached analysis result from session.

        Args:
            request: Django HttpRequest with session
            cache_key: Cache key to lookup

        Returns:
            AnalysisResult if found and valid, None otherwise
        """
        if not hasattr(request, "session"):
            logger.warning("Request has no session, cannot retrieve cache")
            return None

        cached = request.session.get(cache_key)
        if not cached:
            logger.debug(f"No cached data found for key: {cache_key}")
            return None

        try:
            result = pickle.loads(base64.b64decode(cached))
            logger.info(f"Loaded analysis result from cache: {cache_key}")
            return result
        except Exception as e:
            logger.warning(f"Failed to deserialize cached result for {cache_key}: {e}")
            # Clear invalid cache
            try:
                del request.session[cache_key]
            except KeyError:
                pass
            return None

    @staticmethod
    def set_cached(request: HttpRequest, cache_key: str, result: AnalysisResult, ttl: int = 600) -> bool:
        """
        Cache analysis result in session.

        Args:
            request: Django HttpRequest with session
            cache_key: Cache key to store under
            result: AnalysisResult to cache
            ttl: Time to live in seconds (default 10 minutes)

        Returns:
            True if cached successfully, False otherwise
        """
        if not hasattr(request, "session"):
            logger.warning("Request has no session, cannot cache")
            return False

        try:
            serialized = base64.b64encode(pickle.dumps(result)).decode()
            request.session[cache_key] = serialized
            request.session.set_expiry(ttl)
            logger.info(f"Cached analysis result: {cache_key} (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.warning(f"Failed to cache result for {cache_key}: {e}")
            return False

    @staticmethod
    def clear_cached(request: HttpRequest, cache_key: str) -> bool:
        """
        Clear cached result from session.

        Args:
            request: Django HttpRequest with session
            cache_key: Cache key to clear

        Returns:
            True if cleared, False if not found
        """
        if not hasattr(request, "session"):
            return False

        if cache_key in request.session:
            del request.session[cache_key]
            logger.info(f"Cleared cache: {cache_key}")
            return True

        return False

    @staticmethod
    def clear_all_analysis_caches(request: HttpRequest, experiment: str | None = None) -> int:
        """
        Clear all analysis caches from session.

        Args:
            request: Django HttpRequest with session
            experiment: Optional experiment name to filter by

        Returns:
            Number of caches cleared
        """
        if not hasattr(request, "session"):
            return 0

        cleared = 0
        keys_to_delete = []

        for key in request.session.keys():
            if key.startswith("analysis_"):
                if experiment is None or key.startswith(f"analysis_{experiment}_"):
                    keys_to_delete.append(key)

        for key in keys_to_delete:
            del request.session[key]
            cleared += 1

        if cleared > 0:
            logger.info(f"Cleared {cleared} analysis caches for experiment: {experiment or 'all'}")

        return cleared

    @staticmethod
    def get_cache_info(request: HttpRequest, cache_key: str) -> dict[str, Any] | None:
        """
        Get metadata about a cached result without deserializing it.

        Args:
            request: Django HttpRequest with session
            cache_key: Cache key to check

        Returns:
            Dict with size info or None if not found
        """
        if not hasattr(request, "session"):
            return None

        cached = request.session.get(cache_key)
        if not cached:
            return None

        return {
            "key": cache_key,
            "size_bytes": len(cached),
            "size_kb": round(len(cached) / 1024, 2),
            "exists": True,
        }
