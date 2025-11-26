"""
Centralized API caching for all Labs projects.

Provides cached_api_call() wrapper that handles caching transparently.
Any project can use this to cache API responses without implementing caching logic.
"""

import logging
import tempfile
from collections.abc import Callable

import pandas as pd
from django.http import HttpRequest

from commcare_connect.labs.analysis.file_cache import RawAPICache

logger = logging.getLogger(__name__)


def fetch_user_visits_cached(
    request: HttpRequest,
    opportunity_id: int,
    api_call_func: Callable,
    force_refresh: bool = False,
) -> list[dict]:
    """
    Fetch user visits with automatic caching.

    Centralized caching logic for user_visits endpoint - any project can use this.
    Handles cache checking, invalidation, and storage automatically.

    Args:
        request: HttpRequest with labs_context (for visit count validation)
        opportunity_id: Opportunity ID
        api_call_func: Function that makes the API call (should return httpx.Response)
        force_refresh: If True, skip cache and fetch fresh data from API

    Returns:
        List of visit dicts

    Example:
        # In audit/data_access.py:
        def _fetch_visits_for_opportunity(self, opportunity_id):
            def make_api_call():
                return self._call_connect_api(
                    f"/export/opportunity/{opportunity_id}/user_visits/"
                )

            return fetch_user_visits_cached(
                self.request, opportunity_id, make_api_call
            )
    """
    # Initialize cache (managed by Labs)
    cache = RawAPICache(opportunity_id)

    # Get current visit count for cache validation (if available)
    current_visit_count = None
    if hasattr(request, "labs_context"):
        labs_context = request.labs_context or {}
        opportunity = labs_context.get("opportunity", {})
        current_visit_count = opportunity.get("visit_count")

    # Skip cache if force_refresh is True
    if not force_refresh:
        # Try to get from cache
        cached_data = cache.get("user_visits")
        if cached_data and cache.is_valid(cached_data, current_visit_count):
            logger.info(f"Cache HIT for user_visits (opportunity {opportunity_id})")
            return cached_data["data"]
    else:
        logger.info(f"Force refresh requested - bypassing cache (opportunity {opportunity_id})")

    # Cache miss - fetch from API
    logger.info(f"Cache MISS for user_visits (opportunity {opportunity_id}) - fetching from API")

    # Call the provided API function
    response = api_call_func()

    # Parse CSV response
    with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".csv") as tmp_file:
        for chunk in response.iter_bytes():
            tmp_file.write(chunk)
        tmp_path = tmp_file.name

    try:
        df = pd.read_csv(tmp_path)

        # Convert to list of dicts
        visits = []
        for _, row in df.iterrows():
            # Extract visit ID
            visit_id = None
            if "id" in row and pd.notna(row["id"]):
                visit_id = int(row["id"])

            # Extract user_id
            user_id = None
            if "user_id" in row and pd.notna(row["user_id"]):
                try:
                    user_id = int(row["user_id"])
                except (ValueError, TypeError):
                    pass

            # Extract xform_id and form_json from CSV
            # NOTE: The API returns form_json as Python repr format (single quotes, Python literals)
            # not valid JSON (double quotes, null/true/false). We try JSON first, then ast.literal_eval.
            xform_id = None
            form_json = {}
            if "form_json" in row and pd.notna(row["form_json"]):
                import ast
                import json

                raw_json = row["form_json"]
                # First try json.loads for valid JSON
                try:
                    form_json = json.loads(raw_json)
                except (json.JSONDecodeError, TypeError):
                    # Fall back to ast.literal_eval for Python dict repr format
                    try:
                        form_json = ast.literal_eval(raw_json)
                    except (ValueError, SyntaxError):
                        logger.warning(f"Failed to parse form_json: {str(raw_json)[:100]}...")
                        form_json = {}

                if form_json:
                    xform_id = form_json.get("id")

            # Extract images from CSV
            images = []
            if "images" in row and pd.notna(row["images"]):
                try:
                    import ast

                    images = ast.literal_eval(row["images"])
                except (ValueError, SyntaxError):
                    pass

            visit_dict = {
                "id": visit_id,
                "xform_id": xform_id,
                "visit_date": str(row["visit_date"]) if pd.notna(row.get("visit_date")) else None,
                "entity_id": str(row["entity_id"]) if pd.notna(row.get("entity_id")) else None,
                "entity_name": str(row["entity_name"]) if pd.notna(row.get("entity_name")) else None,
                "status": str(row["status"]) if pd.notna(row.get("status")) else None,
                "flagged": bool(row["flagged"]) if pd.notna(row.get("flagged")) else False,
                "user_id": user_id,
                "username": str(row["username"]) if pd.notna(row.get("username")) else None,
                "opportunity_id": opportunity_id,
                "form_json": form_json,
                "images": images,
            }
            visits.append(visit_dict)

        # Cache the result (managed by Labs)
        cache.set("user_visits", visits, current_visit_count)
        logger.info(f"Cached {len(visits)} visits for opportunity {opportunity_id}")

        return visits

    finally:
        # Clean up temp file
        import os

        os.unlink(tmp_path)


def clear_opportunity_cache(opportunity_id: int, endpoint: str = "user_visits") -> bool:
    """
    Clear cache for a specific opportunity endpoint.

    Args:
        opportunity_id: Opportunity ID
        endpoint: API endpoint name (default: "user_visits")

    Returns:
        True if cleared successfully

    Example:
        from commcare_connect.labs.api_cache import clear_opportunity_cache

        # Clear after data is updated
        clear_opportunity_cache(814)
    """
    cache = RawAPICache(opportunity_id)
    return cache.clear(endpoint)
