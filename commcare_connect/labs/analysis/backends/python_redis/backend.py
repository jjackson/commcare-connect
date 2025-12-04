"""
Python/Redis backend implementation.

Uses Redis/file caching with pandas-based computation.
"""

import ast
import io
import json
import logging
from collections.abc import Generator
from typing import Any

import httpx
import pandas as pd
from django.conf import settings
from django.http import HttpRequest

from commcare_connect.labs.analysis.backends.python_redis.cache import (
    AnalysisCacheManager,
    RawAPICacheManager,
    sync_labs_context_visit_count,
)
from commcare_connect.labs.analysis.backends.python_redis.flw_analyzer import FLWAnalyzer
from commcare_connect.labs.analysis.backends.python_redis.visit_analyzer import VisitAnalyzer
from commcare_connect.labs.analysis.config import AnalysisPipelineConfig, CacheStage
from commcare_connect.labs.analysis.models import FLWAnalysisResult, LocalUserVisit, VisitAnalysisResult

logger = logging.getLogger(__name__)


# =============================================================================
# CSV Parsing Helpers (moved from api_cache.py)
# =============================================================================

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

SLIM_COLUMNS = [col for col in ALL_COLUMNS if col != "form_json"]


def _parse_form_json(raw_json: str) -> dict:
    """Parse form_json from CSV string to Python dict."""
    if not raw_json or pd.isna(raw_json):
        return {}
    try:
        return json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        pass
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
    """Convert a pandas row to a visit dict."""

    def get_str(col: str) -> str | None:
        return str(row[col]) if col in row.index and pd.notna(row[col]) else None

    def get_int(col: str) -> int | None:
        if col in row.index and pd.notna(row[col]):
            try:
                return int(row[col])
            except (ValueError, TypeError):
                return None
        return None

    def get_bool(col: str) -> bool:
        return bool(row[col]) if col in row.index and pd.notna(row[col]) else False

    form_json = {}
    xform_id = None
    if include_form_json and "form_json" in row.index:
        form_json = _parse_form_json(row["form_json"])
        if form_json:
            xform_id = form_json.get("id")

    images = []
    if "images" in row.index:
        images = _parse_images(row["images"])

    return {
        "id": get_int("id"),
        "xform_id": xform_id,
        "opportunity_id": get_int("opportunity_id") or opportunity_id,
        "username": get_str("username"),
        "deliver_unit": get_str("deliver_unit"),
        "entity_id": get_str("entity_id"),
        "entity_name": get_str("entity_name"),
        "visit_date": get_str("visit_date"),
        "status": get_str("status"),
        "reason": get_str("reason"),
        "location": get_str("location"),
        "flagged": get_bool("flagged"),
        "flag_reason": get_str("flag_reason"),
        "form_json": form_json,
        "completed_work": get_str("completed_work"),
        "status_modified_date": get_str("status_modified_date"),
        "review_status": get_str("review_status"),
        "review_created_on": get_str("review_created_on"),
        "justification": get_str("justification"),
        "date_created": get_str("date_created"),
        "completed_work_id": get_int("completed_work_id"),
        "deliver_unit_id": get_int("deliver_unit_id"),
        "images": images,
    }


def _parse_csv_bytes(csv_bytes: bytes, opportunity_id: int, skip_form_json: bool = False) -> list[dict]:
    """Parse CSV bytes into list of visit dicts."""
    if skip_form_json:
        usecols = SLIM_COLUMNS
        logger.info("Parsing CSV without form_json column (memory-efficient mode)")
    else:
        usecols = None

    try:
        df = pd.read_csv(io.BytesIO(csv_bytes), usecols=usecols)
    except ValueError as e:
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
    csv_bytes: bytes, opportunity_id: int, visit_ids: set[int], chunksize: int = 1000
) -> list[dict]:
    """Parse CSV in chunks, returning only visits matching specified IDs."""
    matching_visits = []

    for chunk in pd.read_csv(io.BytesIO(csv_bytes), chunksize=chunksize):
        if "id" in chunk.columns:
            filtered = chunk[chunk["id"].isin(visit_ids)]
        else:
            continue

        for _, row in filtered.iterrows():
            visit_dict = _row_to_visit_dict(row, opportunity_id, include_form_json=True)
            matching_visits.append(visit_dict)

    logger.info(f"Chunked parsing found {len(matching_visits)} visits matching {len(visit_ids)} requested IDs")
    return matching_visits


# =============================================================================
# Backend Implementation
# =============================================================================


class PythonRedisBackend:
    """
    Python/Redis backend for analysis.

    Uses Redis (preferred) or file-based caching with pandas-based computation.
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
        Fetch raw visit data from Redis/file cache or API.

        Caches raw CSV bytes and parses on-demand based on caller needs.
        """
        cache = RawAPICacheManager(opportunity_id)

        csv_bytes = None
        if not force_refresh:
            cached_data = cache.get("user_visits_csv")
            if cached_data and cache.is_valid(cached_data, expected_visit_count):
                logger.info(f"[PythonRedis] Raw cache HIT for opp {opportunity_id}")
                csv_bytes = cached_data["data"]

        if csv_bytes is None:
            logger.info(f"[PythonRedis] Raw cache MISS for opp {opportunity_id}, fetching from API")
            csv_bytes = self._fetch_csv_from_api(opportunity_id, access_token)

            visit_count = csv_bytes.count(b"\n") - 1 if csv_bytes else 0
            cache.set("user_visits_csv", csv_bytes, visit_count)
            logger.info(f"[PythonRedis] Cached raw CSV ({len(csv_bytes)} bytes)")

        # Parse based on caller's needs
        if filter_visit_ids:
            return _parse_csv_chunked(csv_bytes, opportunity_id, filter_visit_ids)
        else:
            return _parse_csv_bytes(csv_bytes, opportunity_id, skip_form_json)

    def stream_raw_visits(
        self,
        opportunity_id: int,
        access_token: str,
        expected_visit_count: int | None = None,
        force_refresh: bool = False,
    ) -> Generator[tuple[str, Any], None, None]:
        """
        Stream raw visit data with progress events.

        Checks cache first, then streams download from API with progress.
        """
        cache = RawAPICacheManager(opportunity_id)

        # Check cache first
        if not force_refresh:
            cached_data = cache.get("user_visits_csv")
            if cached_data and cache.is_valid(cached_data, expected_visit_count):
                logger.info(f"[PythonRedis] Raw cache HIT for opp {opportunity_id}")
                csv_bytes = cached_data["data"]
                visit_dicts = _parse_csv_bytes(csv_bytes, opportunity_id, skip_form_json=False)
                yield ("cached", visit_dicts)
                return

        # Cache miss - stream download
        logger.info(f"[PythonRedis] Raw cache MISS for opp {opportunity_id}, streaming from API")

        url = f"{settings.CONNECT_PRODUCTION_URL}/export/opportunity/{opportunity_id}/user_visits/"
        headers = {"Authorization": f"Bearer {access_token}"}

        chunks = []
        bytes_downloaded = 0
        chunk_size = 5 * 1024 * 1024  # 5MB progress intervals

        try:
            with httpx.stream("GET", url, headers=headers, timeout=580.0) as response:
                response.raise_for_status()
                total_bytes = int(response.headers.get("content-length", 0))
                last_progress_at = 0

                for chunk in response.iter_bytes(chunk_size=65536):
                    chunks.append(chunk)
                    bytes_downloaded += len(chunk)

                    if bytes_downloaded - last_progress_at >= chunk_size:
                        yield ("progress", bytes_downloaded, total_bytes)
                        last_progress_at = bytes_downloaded

                if bytes_downloaded > last_progress_at:
                    yield ("progress", bytes_downloaded, total_bytes)

        except httpx.TimeoutException as e:
            logger.error(f"[PythonRedis] Timeout downloading for opp {opportunity_id}: {e}")
            raise RuntimeError("Connect API timeout") from e

        csv_bytes = b"".join(chunks)

        # Cache raw bytes
        visit_count = csv_bytes.count(b"\n") - 1 if csv_bytes else 0
        cache.set("user_visits_csv", csv_bytes, visit_count)
        logger.info(f"[PythonRedis] Cached raw CSV ({len(csv_bytes)} bytes)")

        # Parse and return
        visit_dicts = _parse_csv_bytes(csv_bytes, opportunity_id, skip_form_json=False)
        yield ("complete", visit_dicts)

    def has_valid_raw_cache(self, opportunity_id: int, expected_visit_count: int) -> bool:
        """Check if valid raw cache exists."""
        cache = RawAPICacheManager(opportunity_id)
        cached_data = cache.get("user_visits_csv")
        return cached_data is not None and cache.is_valid(cached_data, expected_visit_count)

    def _fetch_csv_from_api(self, opportunity_id: int, access_token: str) -> bytes:
        """Fetch raw CSV bytes from Connect API."""
        url = f"{settings.CONNECT_PRODUCTION_URL}/export/opportunity/{opportunity_id}/user_visits/"
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            response = httpx.get(url, headers=headers, timeout=580.0)
            response.raise_for_status()
            return response.content
        except httpx.TimeoutException as e:
            logger.error(f"[PythonRedis] Timeout fetching visits for opp {opportunity_id}: {e}")
            raise RuntimeError("Connect API timeout") from e

    # -------------------------------------------------------------------------
    # Analysis Results Layer
    # -------------------------------------------------------------------------

    def get_cached_flw_result(
        self, opportunity_id: int, config: AnalysisPipelineConfig, visit_count: int
    ) -> FLWAnalysisResult | None:
        """Get cached FLW result if valid."""
        cache_manager = AnalysisCacheManager(opportunity_id, config)
        cached = cache_manager.get_results_cache()
        if cached and cache_manager.validate_cache(visit_count, cached):
            logger.info(f"[PythonRedis] FLW cache HIT for opp {opportunity_id}")
            return cached["result"]
        return None

    def get_cached_visit_result(
        self, opportunity_id: int, config: AnalysisPipelineConfig, visit_count: int
    ) -> VisitAnalysisResult | None:
        """Get cached visit result if valid."""
        cache_manager = AnalysisCacheManager(opportunity_id, config)
        cached = cache_manager.get_visit_results_cache()
        if cached and cache_manager.validate_cache(visit_count, cached):
            logger.info(f"[PythonRedis] Visit cache HIT for opp {opportunity_id}")
            return cached["result"]
        return None

    def process_and_cache(
        self,
        request: HttpRequest,
        config: AnalysisPipelineConfig,
        opportunity_id: int,
        visit_dicts: list[dict],
    ) -> FLWAnalysisResult | VisitAnalysisResult:
        """
        Process visits and cache results.

        Returns FLWAnalysisResult if terminal_stage=AGGREGATED, else VisitAnalysisResult.
        """
        # Convert to LocalUserVisit objects
        visits = [LocalUserVisit(d) for d in visit_dicts]
        logger.info(f"[PythonRedis] Processing {len(visits)} visits for opp {opportunity_id}")

        # Compute visit-level analysis
        visit_analyzer = VisitAnalyzer(request, config)
        visit_result = visit_analyzer.compute(prefetched_visits=visits)
        visit_count = visit_result.metadata.get("total_visits", 0)

        # Cache visit results
        cache_manager = AnalysisCacheManager(opportunity_id, config)
        cache_manager.set_visit_results_cache(visit_count, visit_result)

        # If visit-level is terminal, return now
        if config.terminal_stage == CacheStage.VISIT_LEVEL:
            sync_labs_context_visit_count(request, visit_count, opportunity_id)
            return visit_result

        # Aggregate to FLW level
        flw_analyzer = FLWAnalyzer(request, config)
        flw_result = flw_analyzer.from_visit_result(visit_result)

        # Cache FLW results
        cache_manager.set_results_cache(visit_count, flw_result)

        # Sync context
        sync_labs_context_visit_count(request, visit_count, opportunity_id)

        logger.info(f"[PythonRedis] Processed {len(flw_result.rows)} FLWs, {visit_count} visits")
        return flw_result
