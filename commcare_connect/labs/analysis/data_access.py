"""
Data access utilities for analysis framework.

Provides utility functions for fetching data from Connect API.
"""

import logging
from io import StringIO

import httpx
import pandas as pd
from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest

from commcare_connect.labs.analysis.utils import DJANGO_CACHE_TTL

logger = logging.getLogger(__name__)


def get_flw_names_for_opportunity(request: HttpRequest) -> dict[str, str]:
    """
    Get FLW display names for the opportunity in request context.

    Fetches username to display name mapping from Connect API and caches it.

    Args:
        request: HttpRequest with labs_oauth and labs_context in session

    Returns:
        Dictionary mapping username to display name
        Example: {"e5e685ae3f024fb6848d0d87138d526f": "John Doe"}

    Raises:
        ValueError: If no OAuth token or opportunity context found
    """
    access_token = request.session.get("labs_oauth", {}).get("access_token")
    labs_context = getattr(request, "labs_context", {})
    opportunity_id = labs_context.get("opportunity_id")

    if not access_token:
        raise ValueError("No labs OAuth token found in session")

    if not opportunity_id:
        raise ValueError("No opportunity selected in labs context")

    # Try cache first
    cache_key = f"flw_names_{opportunity_id}"
    try:
        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug(f"FLW names loaded from cache for opp {opportunity_id}")
            return cached
    except Exception as e:
        logger.warning(f"Cache get failed for {cache_key}: {e}")

    # Fetch from API
    url = f"{settings.CONNECT_PRODUCTION_URL}/export/opportunity/{opportunity_id}/user_data/"
    logger.info(f"Fetching FLW names from {url}")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept-Encoding": "gzip, deflate",
    }
    try:
        response = httpx.get(url, headers=headers, timeout=30.0)
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

    # Cache the result
    try:
        cache.set(cache_key, flw_names, DJANGO_CACHE_TTL)
        logger.debug(f"FLW names cached for opp {opportunity_id}")
    except Exception as e:
        logger.warning(f"Cache set failed for {cache_key}: {e}")

    return flw_names
