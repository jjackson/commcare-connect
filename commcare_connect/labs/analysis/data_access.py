"""
Data access layer for analysis framework.

Provides AnalysisDataAccess for fetching UserVisit data.
Uses AnalysisPipeline internally for backend-agnostic data access.
"""

import logging
from io import StringIO

import httpx
import pandas as pd
from django.conf import settings
from django.http import HttpRequest

from commcare_connect.labs.analysis.models import LocalUserVisit
from commcare_connect.labs.analysis.pipeline import AnalysisPipeline

logger = logging.getLogger(__name__)


class AnalysisDataAccess:
    """
    Fetches UserVisit data from Connect API.

    Uses AnalysisPipeline for backend-agnostic caching.
    Handles pagination, parsing, and returns list of LocalUserVisit proxies.
    """

    def __init__(self, request: HttpRequest):
        """
        Initialize data access with request context.

        Args:
            request: HttpRequest with labs_oauth and labs_context in session
        """
        self.request = request
        self.access_token = request.session.get("labs_oauth", {}).get("access_token")
        self.labs_context = getattr(request, "labs_context", {})
        self.opportunity_id = self.labs_context.get("opportunity_id")

        if not self.access_token:
            raise ValueError("No labs OAuth token found in session")

        if not self.opportunity_id:
            raise ValueError("No opportunity selected in labs context")

        # Use AnalysisPipeline for data access
        self._pipeline = AnalysisPipeline(request)

    def fetch_user_visits(self) -> list[LocalUserVisit]:
        """
        Fetch all UserVisits for the opportunity from Connect API.

        Uses AnalysisPipeline for backend-agnostic caching.
        Respects ?refresh=1 URL parameter to force cache bypass.

        Returns:
            List of LocalUserVisit proxies

        Raises:
            RuntimeError: If API request fails
        """
        logger.info(f"Fetching user visits for opportunity {self.opportunity_id}")

        # Use AnalysisPipeline for raw data access
        visits_data = self._pipeline.fetch_raw_visits()

        # Convert dicts to LocalUserVisit proxies
        visits = [LocalUserVisit(data) for data in visits_data]

        return visits

    def fetch_visit_count(self) -> int:
        """
        Get visit count for cache validation from labs_context.

        The visit_count is synced from actual data during previous runs.
        Raises an error if not available - this indicates a context loading issue.

        Returns:
            Total visit count for the opportunity

        Raises:
            ValueError: If visit_count is not in labs_context
        """
        opportunity = self.labs_context.get("opportunity", {})
        if opportunity and "visit_count" in opportunity:
            count = opportunity.get("visit_count", 0)
            logger.info(f"Visit count from labs_context for opportunity {self.opportunity_id}: {count}")
            return count

        raise ValueError(
            "Opportunity User Visit count not found in LabsContext. "
            "You did not have access to this opp at the time of LabsContext loading."
        )


def get_flw_names_for_opportunity(request: HttpRequest) -> dict[str, str]:
    """
    Get FLW display names for the opportunity in request context.

    Fetches username to display name mapping from Connect API and caches it.
    Uses the same caching backend as analysis results (Redis if available, file-based fallback).

    Args:
        request: HttpRequest with labs_oauth and labs_context in session

    Returns:
        Dictionary mapping username to display name
        Example: {"e5e685ae3f024fb6848d0d87138d526f": "John Doe"}

    Raises:
        ValueError: If no OAuth token or opportunity context found
    """
    from commcare_connect.labs.analysis.backends.python_redis.cache import CACHE_DIR, _use_django_cache

    access_token = request.session.get("labs_oauth", {}).get("access_token")
    labs_context = getattr(request, "labs_context", {})
    opportunity_id = labs_context.get("opportunity_id")

    if not access_token:
        raise ValueError("No labs OAuth token found in session")

    if not opportunity_id:
        raise ValueError("No opportunity selected in labs context")

    # Try cache first
    cache_key = f"flw_names_{opportunity_id}"
    use_django = _use_django_cache()

    if use_django:
        from django.core.cache import cache

        try:
            cached = cache.get(cache_key)
            if cached is not None:
                logger.debug(f"FLW names loaded from Django cache for opp {opportunity_id}")
                return cached
        except Exception as e:
            logger.warning(f"Django cache get failed for {cache_key}: {e}")
    else:
        # File-based cache
        cache_file = CACHE_DIR / f"flw_names_{opportunity_id}.pkl"
        if cache_file.exists():
            try:
                import pickle

                with open(cache_file, "rb") as f:
                    cached = pickle.load(f)
                logger.debug(f"FLW names loaded from file cache for opp {opportunity_id}")
                return cached
            except Exception as e:
                logger.warning(f"File cache read failed for {cache_key}: {e}")

    # Fetch from API
    url = f"{settings.CONNECT_PRODUCTION_URL}/export/opportunity/{opportunity_id}/user_data/"
    logger.info(f"Fetching FLW names from {url}")

    try:
        response = httpx.get(url, headers={"Authorization": f"Bearer {access_token}"}, timeout=30.0)
        response.raise_for_status()
    except httpx.TimeoutException as e:
        logger.error(f"Timeout fetching FLW names for opportunity {opportunity_id}: {e}")
        raise RuntimeError("Connect API timeout while fetching FLW names") from e
    except httpx.HTTPStatusError as e:
        logger.error(f"Failed to fetch FLW names: {e}")
        raise

    # Parse CSV response
    df = pd.read_csv(StringIO(response.text))
    logger.info(f"Fetched {len(df)} FLWs from Connect")

    # Build mapping: username -> name (fallback to username if name is empty)
    flw_names = {}
    for _, row in df.iterrows():
        username = row.get("username")
        name = row.get("name")
        if username:
            flw_names[username] = name if name else username

    # Cache the result (1 hour TTL)
    if use_django:
        from django.core.cache import cache

        try:
            cache.set(cache_key, flw_names, 3600)
            logger.debug(f"FLW names cached in Django cache for opp {opportunity_id}")
        except Exception as e:
            logger.warning(f"Django cache set failed for {cache_key}: {e}")
    else:
        # File-based cache
        try:
            CACHE_DIR.mkdir(exist_ok=True)
            cache_file = CACHE_DIR / f"flw_names_{opportunity_id}.pkl"
            import pickle

            with open(cache_file, "wb") as f:
                pickle.dump(flw_names, f)
            logger.debug(f"FLW names cached in file cache for opp {opportunity_id}")
        except Exception as e:
            logger.warning(f"File cache write failed for {cache_key}: {e}")

    return flw_names
