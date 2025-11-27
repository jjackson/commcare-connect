"""
Centralized API caching for all Labs projects.

Provides cached_api_call() wrapper that handles caching transparently.
Any project can use this to cache API responses without implementing caching logic.

Memory Optimization (2024-11):
- Caches raw CSV bytes instead of parsed Python objects
- Parses on-demand with selective column loading
- skip_form_json=True skips the expensive form_json column (~90% memory reduction)
- filter_visit_ids uses chunked reading for specific IDs only
"""

import ast
import io
import json
import logging
from collections.abc import Callable

import pandas as pd
from django.http import HttpRequest

from commcare_connect.labs.analysis.cache import RawAPICacheManager

logger = logging.getLogger(__name__)

# Exact columns from UserVisitDataSerialier (data_export/serializer.py)
# form_json is optional - excluded for slim mode
ALL_COLUMNS = [
    "id",
    "opportunity_id",
    "username",
    "deliver_unit",
    "entity_id",
    "entity_name",
    "visit_date",
    "status",
    "reason",
    "location",
    "flagged",
    "flag_reason",
    "form_json",
    "completed_work",
    "status_modified_date",
    "review_status",
    "review_created_on",
    "justification",
    "date_created",
    "completed_work_id",
    "deliver_unit_id",
    "images",
]

# Columns to load in slim mode (excludes form_json)
SLIM_COLUMNS = [col for col in ALL_COLUMNS if col != "form_json"]


def _parse_form_json(raw_json: str) -> dict:
    """
    Parse form_json from CSV string to Python dict.

    The API returns form_json as Python repr format (single quotes, Python literals)
    not valid JSON (double quotes, null/true/false). We try JSON first, then ast.literal_eval.
    """
    if not raw_json or pd.isna(raw_json):
        return {}

    # First try json.loads for valid JSON
    try:
        return json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        pass

    # Fall back to ast.literal_eval for Python dict repr format
    try:
        return ast.literal_eval(raw_json)
    except (ValueError, SyntaxError):
        logger.warning(f"Failed to parse form_json: {str(raw_json)[:100]}...")
        return {}


def _parse_images(raw_images: str) -> list:
    """Parse images column from CSV string to Python list."""
    if not raw_images or pd.isna(raw_images):
        return []

    try:
        return ast.literal_eval(raw_images)
    except (ValueError, SyntaxError):
        return []


def _row_to_visit_dict(row: pd.Series, opportunity_id: int, include_form_json: bool = True) -> dict:
    """
    Convert a pandas row to a visit dict.

    Columns match UserVisitDataSerialier from data_export/serializer.py.

    Args:
        row: pandas Series from DataFrame
        opportunity_id: Opportunity ID (passed in, but also in CSV)
        include_form_json: If True, parse and include form_json; if False, use empty dict
    """

    def _get_str(col: str) -> str | None:
        return str(row[col]) if col in row.index and pd.notna(row[col]) else None

    def _get_int(col: str) -> int | None:
        if col in row.index and pd.notna(row[col]):
            try:
                return int(row[col])
            except (ValueError, TypeError):
                return None
        return None

    def _get_bool(col: str) -> bool:
        return bool(row[col]) if col in row.index and pd.notna(row[col]) else False

    # Parse form_json if requested
    form_json = {}
    xform_id = None
    if include_form_json and "form_json" in row.index:
        form_json = _parse_form_json(row["form_json"])
        if form_json:
            xform_id = form_json.get("id")

    # Parse images
    images = []
    if "images" in row.index:
        images = _parse_images(row["images"])

    return {
        "id": _get_int("id"),
        "xform_id": xform_id,
        "opportunity_id": _get_int("opportunity_id") or opportunity_id,
        "username": _get_str("username"),
        "deliver_unit": _get_str("deliver_unit"),
        "entity_id": _get_str("entity_id"),
        "entity_name": _get_str("entity_name"),
        "visit_date": _get_str("visit_date"),
        "status": _get_str("status"),
        "reason": _get_str("reason"),
        "location": _get_str("location"),
        "flagged": _get_bool("flagged"),
        "flag_reason": _get_str("flag_reason"),
        "form_json": form_json,
        "completed_work": _get_str("completed_work"),
        "status_modified_date": _get_str("status_modified_date"),
        "review_status": _get_str("review_status"),
        "review_created_on": _get_str("review_created_on"),
        "justification": _get_str("justification"),
        "date_created": _get_str("date_created"),
        "completed_work_id": _get_int("completed_work_id"),
        "deliver_unit_id": _get_int("deliver_unit_id"),
        "images": images,
    }


def _parse_csv_bytes(
    csv_bytes: bytes,
    opportunity_id: int,
    skip_form_json: bool = False,
) -> list[dict]:
    """
    Parse CSV bytes into list of visit dicts.

    Args:
        csv_bytes: Raw CSV content as bytes
        opportunity_id: Opportunity ID to include in each dict
        skip_form_json: If True, skip parsing form_json column (major memory savings)

    Returns:
        List of visit dicts
    """
    # Determine which columns to load
    if skip_form_json:
        # Use usecols to skip form_json column entirely - pandas won't load it into memory
        usecols = SLIM_COLUMNS
        logger.info("Parsing CSV without form_json column (memory-efficient mode)")
    else:
        usecols = None  # Load all columns

    try:
        df = pd.read_csv(io.BytesIO(csv_bytes), usecols=usecols)
    except ValueError as e:
        # Handle case where some columns don't exist in CSV
        if "not in list" in str(e) and skip_form_json:
            logger.warning(f"Some slim columns not found in CSV, falling back to all columns: {e}")
            df = pd.read_csv(io.BytesIO(csv_bytes))
        else:
            raise

    visits = []
    for _, row in df.iterrows():
        visit_dict = _row_to_visit_dict(row, opportunity_id, include_form_json=not skip_form_json)
        visits.append(visit_dict)

    return visits


def _parse_csv_chunked(
    csv_bytes: bytes,
    opportunity_id: int,
    visit_ids: set[int],
    chunksize: int = 1000,
) -> list[dict]:
    """
    Parse CSV in chunks, returning only visits matching the specified IDs.

    Memory efficient: only parses form_json for matching rows, processes in chunks.

    Args:
        csv_bytes: Raw CSV content as bytes
        opportunity_id: Opportunity ID to include in each dict
        visit_ids: Set of visit IDs to filter for
        chunksize: Number of rows to process at a time

    Returns:
        List of visit dicts for matching IDs only (with form_json parsed)
    """
    matching_visits = []

    for chunk in pd.read_csv(io.BytesIO(csv_bytes), chunksize=chunksize):
        # Filter to matching IDs
        if "id" in chunk.columns:
            filtered = chunk[chunk["id"].isin(visit_ids)]
        else:
            continue

        # Parse each matching row (including form_json)
        for _, row in filtered.iterrows():
            visit_dict = _row_to_visit_dict(row, opportunity_id, include_form_json=True)
            matching_visits.append(visit_dict)

        # chunk is garbage collected after each iteration

    logger.info(f"Chunked parsing found {len(matching_visits)} visits matching {len(visit_ids)} requested IDs")
    return matching_visits


def fetch_user_visits_cached(
    request: HttpRequest,
    opportunity_id: int,
    api_call_func: Callable,
    force_refresh: bool = False,
    skip_form_json: bool = False,
    filter_visit_ids: set[int] | None = None,
) -> list[dict]:
    """
    Fetch user visits with automatic caching.

    Centralized caching logic for user_visits endpoint - any project can use this.
    Caches raw CSV bytes (not parsed objects) for memory efficiency.
    Parses on-demand with caller-specified options.

    Args:
        request: HttpRequest with labs_context (for visit count validation)
        opportunity_id: Opportunity ID
        api_call_func: Function that makes the API call (should return httpx.Response)
        force_refresh: If True, skip cache and fetch fresh data from API
        skip_form_json: If True, skip parsing form_json column (~90% memory reduction)
        filter_visit_ids: If provided, only return visits with these IDs (uses chunked parsing)

    Returns:
        List of visit dicts

    Example:
        # Basic usage (with form_json):
        visits = fetch_user_visits_cached(request, opp_id, make_api_call)

        # Memory-efficient (skip form_json):
        visits = fetch_user_visits_cached(request, opp_id, make_api_call, skip_form_json=True)

        # Get specific visits with form_json (for audit session creation):
        visits = fetch_user_visits_cached(request, opp_id, make_api_call, filter_visit_ids={1, 2, 3})
    """
    cache = RawAPICacheManager(opportunity_id)

    # Get current visit count for cache validation (if available)
    current_visit_count = None
    if hasattr(request, "labs_context"):
        labs_context = request.labs_context or {}
        opportunity = labs_context.get("opportunity", {})
        current_visit_count = opportunity.get("visit_count")

    # Try to get raw CSV from cache
    csv_bytes = None
    cache_miss_reason = None
    if not force_refresh:
        cached_data = cache.get("user_visits_csv")
        if cached_data:
            if cache.is_valid(cached_data, current_visit_count):
                logger.info(f"Cache HIT for user_visits_csv (opportunity {opportunity_id})")
                csv_bytes = cached_data["data"]
            else:
                # Cache exists but is invalid - determine why
                cached_count = cached_data.get("visit_count")
                cache_miss_reason = f"visit_count mismatch (cached={cached_count}, expected={current_visit_count})"
        else:
            cache_miss_reason = "no cached data found"
    else:
        logger.info(f"Force refresh requested - bypassing cache (opportunity {opportunity_id})")
        cache_miss_reason = "force_refresh=True"

    # If not in cache, fetch from API
    if csv_bytes is None:
        logger.info(
            f"Cache MISS for user_visits_csv (opportunity {opportunity_id}) - "
            f"reason: {cache_miss_reason}, expected_visit_count={current_visit_count}"
        )
        response = api_call_func()
        csv_bytes = response.content

        # Cache the raw CSV bytes (much smaller than parsed objects)
        # Count visits by counting newlines (rough estimate, header is 1 line)
        visit_count = csv_bytes.count(b"\n") - 1 if csv_bytes else 0
        cache.set("user_visits_csv", csv_bytes, visit_count)
        logger.info(f"Cached raw CSV ({len(csv_bytes)} bytes, ~{visit_count} visits) for opportunity {opportunity_id}")

    # Parse based on caller's needs
    if filter_visit_ids:
        # Chunked parsing for specific IDs (memory efficient, includes form_json)
        return _parse_csv_chunked(csv_bytes, opportunity_id, filter_visit_ids)
    else:
        # Standard parsing (optionally skip form_json)
        return _parse_csv_bytes(csv_bytes, opportunity_id, skip_form_json=skip_form_json)


def clear_opportunity_cache(opportunity_id: int, endpoint: str = "user_visits_csv") -> bool:
    """
    Clear cache for a specific opportunity endpoint.

    Args:
        opportunity_id: Opportunity ID
        endpoint: API endpoint name (default: "user_visits_csv")

    Returns:
        True if cleared successfully

    Example:
        from commcare_connect.labs.api_cache import clear_opportunity_cache

        # Clear after data is updated
        clear_opportunity_cache(814)
    """
    cache = RawAPICacheManager(opportunity_id)
    return cache.clear(endpoint)
