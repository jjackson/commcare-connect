"""
SQL backend implementation.

Uses PostgreSQL tables for caching AND computation.
All analysis is done via SQL queries, not Python/pandas.
"""

import logging
from collections.abc import Generator
from decimal import Decimal
from typing import Any

import httpx
from django.conf import settings
from django.http import HttpRequest

from commcare_connect.labs.analysis.backends.csv_parsing import parse_csv_bytes
from commcare_connect.labs.analysis.backends.sql.cache import SQLCacheManager
from commcare_connect.labs.analysis.backends.sql.query_builder import execute_flw_aggregation
from commcare_connect.labs.analysis.config import AnalysisPipelineConfig
from commcare_connect.labs.analysis.models import FLWAnalysisResult, FLWRow, VisitAnalysisResult

logger = logging.getLogger(__name__)


def _model_to_visit_dict(row) -> dict:
    """Convert RawVisitCache model instance to visit dict."""
    return {
        "id": row.visit_id,
        "opportunity_id": row.opportunity_id,
        "username": row.username,
        "deliver_unit": row.deliver_unit,
        "deliver_unit_id": row.deliver_unit_id,
        "entity_id": row.entity_id,
        "entity_name": row.entity_name,
        "visit_date": row.visit_date.isoformat() if row.visit_date else None,
        "status": row.status,
        "reason": row.reason,
        "location": row.location,
        "flagged": row.flagged,
        "flag_reason": row.flag_reason,
        "form_json": row.form_json,
        "completed_work": row.completed_work,
        "status_modified_date": row.status_modified_date.isoformat() if row.status_modified_date else None,
        "review_status": row.review_status,
        "review_created_on": row.review_created_on.isoformat() if row.review_created_on else None,
        "justification": row.justification,
        "date_created": row.date_created.isoformat() if row.date_created else None,
        "completed_work_id": row.completed_work_id,
        "images": row.images,
    }


class SQLBackend:
    """
    SQL backend for analysis.

    Uses PostgreSQL for both storage AND computation:
    - Raw visits stored in SQL tables
    - Field extraction via JSONB operators
    - Aggregation via GROUP BY queries
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
        Fetch raw visit data from SQL cache or API.

        SQL backend stores visits in RawVisitCache table. If cache is valid,
        reads directly from PostgreSQL. Otherwise, fetches from API and stores.
        """
        cache_manager = SQLCacheManager(opportunity_id, config=None)

        # Check if we have valid cached data in SQL
        if not force_refresh and expected_visit_count:
            if cache_manager.has_valid_raw_cache(expected_visit_count):
                logger.info(f"[SQL] Raw cache HIT for opp {opportunity_id}")
                return self._load_from_cache(cache_manager, skip_form_json, filter_visit_ids)

        # Cache miss or force refresh - fetch from API
        logger.info(f"[SQL] Raw cache MISS for opp {opportunity_id}, fetching from API")
        csv_bytes = self._fetch_from_api(opportunity_id, access_token)

        # Parse full data (always with form_json for storage)
        visit_dicts = parse_csv_bytes(csv_bytes, opportunity_id, skip_form_json=False)

        # Store full data to SQL cache
        visit_count = len(visit_dicts)
        cache_manager.store_raw_visits(visit_dicts, visit_count)
        logger.info(f"[SQL] Stored {visit_count} visits to RawVisitCache")

        # Apply filters for return value
        if filter_visit_ids:
            visit_dicts = [v for v in visit_dicts if v.get("id") in filter_visit_ids]

        if skip_form_json:
            for v in visit_dicts:
                v["form_json"] = {}

        return visit_dicts

    def stream_raw_visits(
        self,
        opportunity_id: int,
        access_token: str,
        expected_visit_count: int | None = None,
        force_refresh: bool = False,
    ) -> Generator[tuple[str, Any], None, None]:
        """
        Stream raw visit data with progress events.

        SQL backend checks RawVisitCache first. If hit, yields immediately.
        Otherwise streams download from API with progress.
        """
        cache_manager = SQLCacheManager(opportunity_id, config=None)

        # Check SQL cache first
        if not force_refresh and expected_visit_count:
            if cache_manager.has_valid_raw_cache(expected_visit_count):
                logger.info(f"[SQL] Raw cache HIT for opp {opportunity_id}")
                visit_dicts = self._load_from_cache(cache_manager, skip_form_json=False, filter_visit_ids=None)
                yield ("cached", visit_dicts)
                return

        # Cache miss - stream download from API
        logger.info(f"[SQL] Raw cache MISS for opp {opportunity_id}, streaming from API")

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
            logger.error(f"[SQL] Timeout downloading for opp {opportunity_id}: {e}")
            raise RuntimeError("Connect API timeout") from e

        csv_bytes = b"".join(chunks)
        visit_dicts = parse_csv_bytes(csv_bytes, opportunity_id, skip_form_json=False)

        # Store to SQL cache
        visit_count = len(visit_dicts)
        cache_manager.store_raw_visits(visit_dicts, visit_count)
        logger.info(f"[SQL] Stored {visit_count} visits to RawVisitCache")

        yield ("complete", visit_dicts)

    def has_valid_raw_cache(self, opportunity_id: int, expected_visit_count: int) -> bool:
        """Check if valid raw cache exists in SQL."""
        cache_manager = SQLCacheManager(opportunity_id, config=None)
        return cache_manager.has_valid_raw_cache(expected_visit_count)

    def _load_from_cache(
        self,
        cache_manager: SQLCacheManager,
        skip_form_json: bool,
        filter_visit_ids: set[int] | None,
    ) -> list[dict]:
        """Load visits from RawVisitCache table."""
        qs = cache_manager.get_raw_visits_queryset()

        if filter_visit_ids:
            qs = qs.filter(visit_id__in=filter_visit_ids)

        if skip_form_json:
            # Exclude form_json from query for efficiency
            qs = qs.defer("form_json")

        visits = []
        for row in qs.iterator():
            visit = _model_to_visit_dict(row)
            if skip_form_json:
                visit["form_json"] = {}
            visits.append(visit)

        logger.info(f"[SQL] Loaded {len(visits)} visits from RawVisitCache")
        return visits

    def _fetch_from_api(self, opportunity_id: int, access_token: str) -> bytes:
        """Fetch raw CSV bytes from Connect API."""
        url = f"{settings.CONNECT_PRODUCTION_URL}/export/opportunity/{opportunity_id}/user_visits/"
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            response = httpx.get(url, headers=headers, timeout=580.0)
            response.raise_for_status()
            return response.content
        except httpx.TimeoutException as e:
            logger.error(f"[SQL] Timeout fetching visits for opp {opportunity_id}: {e}")
            raise RuntimeError("Connect API timeout") from e

    # -------------------------------------------------------------------------
    # Analysis Results Layer
    # -------------------------------------------------------------------------

    def get_cached_flw_result(
        self, opportunity_id: int, config: AnalysisPipelineConfig, visit_count: int
    ) -> FLWAnalysisResult | None:
        """Get cached FLW result if valid."""
        cache_manager = SQLCacheManager(opportunity_id, config)

        if not cache_manager.has_valid_flw_cache(visit_count):
            return None

        logger.info(f"[SQL] FLW cache HIT for opp {opportunity_id}")

        # Load FLW results from SQL cache
        flw_qs = cache_manager.get_flw_results_queryset()
        flw_rows = []
        for row in flw_qs:
            flw_row = FLWRow(
                username=row.username,
                total_visits=row.total_visits,
                approved_visits=row.approved_visits,
                pending_visits=row.pending_visits,
                rejected_visits=row.rejected_visits,
                flagged_visits=row.flagged_visits,
                first_visit_date=row.first_visit_date,
                last_visit_date=row.last_visit_date,
            )
            flw_row.custom_fields = row.aggregated_fields
            flw_rows.append(flw_row)

        return FLWAnalysisResult(
            opportunity_id=opportunity_id,
            rows=flw_rows,
            metadata={"total_visits": visit_count, "from_sql_cache": True},
        )

    def get_cached_visit_result(
        self, opportunity_id: int, config: AnalysisPipelineConfig, visit_count: int
    ) -> VisitAnalysisResult | None:
        """Get cached visit result if valid."""
        # SQL backend focuses on FLW-level aggregation
        # Visit-level results would require different approach
        return None

    def process_and_cache(
        self,
        request: HttpRequest,
        config: AnalysisPipelineConfig,
        opportunity_id: int,
        visit_dicts: list[dict],
    ) -> FLWAnalysisResult | VisitAnalysisResult:
        """
        Process visits using SQL and cache results.

        1. Store raw visits in SQL (if not already stored)
        2. Execute aggregation query
        3. Cache and return results
        """
        cache_manager = SQLCacheManager(opportunity_id, config)
        visit_count = len(visit_dicts)

        # Step 1: Store raw visits to SQL (idempotent - replaces existing)
        logger.info(f"[SQL] Storing {visit_count} raw visits to SQL")
        cache_manager.store_raw_visits(visit_dicts, visit_count)

        # Step 2: Execute SQL aggregation query
        logger.info("[SQL] Executing SQL aggregation query")
        flw_data = execute_flw_aggregation(config, opportunity_id)

        # Step 3: Convert to FLWRow objects
        flw_rows = []
        total_visits = 0

        for row in flw_data:
            # Standard fields
            flw_row = FLWRow(
                username=row["username"],
                total_visits=row.get("total_visits", 0),
                approved_visits=row.get("approved_visits", 0),
                pending_visits=row.get("pending_visits", 0),
                rejected_visits=row.get("rejected_visits", 0),
                flagged_visits=row.get("flagged_visits", 0),
                first_visit_date=row.get("first_visit_date"),
                last_visit_date=row.get("last_visit_date"),
            )

            # Custom fields (from config fields + histograms)
            custom = {}
            for field in config.fields:
                if field.name in row:
                    custom[field.name] = row[field.name]

            # Add histogram fields
            for hist in config.histograms:
                bin_width = (hist.upper_bound - hist.lower_bound) / hist.num_bins
                for i in range(hist.num_bins):
                    bin_lower = hist.lower_bound + (i * bin_width)
                    bin_upper = bin_lower + bin_width
                    lower_str = str(bin_lower).replace(".", "_")
                    upper_str = str(bin_upper).replace(".", "_")
                    bin_name = f"{hist.bin_name_prefix}_{lower_str}_{upper_str}_visits"
                    if bin_name in row:
                        custom[bin_name] = row[bin_name] or 0

                # Add summary stats (convert Decimal to float for JSON compatibility)
                if f"{hist.name}_mean" in row:
                    mean_val = row[f"{hist.name}_mean"]
                    if isinstance(mean_val, Decimal):
                        mean_val = float(mean_val)
                    custom[f"{hist.name}_mean"] = mean_val
                if f"{hist.name}_count" in row:
                    custom[f"{hist.name}_count"] = row[f"{hist.name}_count"]

            flw_row.custom_fields = custom

            flw_rows.append(flw_row)
            total_visits += flw_row.total_visits

        # Step 4: Build result
        flw_result = FLWAnalysisResult(
            opportunity_id=opportunity_id,
            rows=flw_rows,
            metadata={
                "total_visits": total_visits,
                "total_flws": len(flw_rows),
                "computed_via": "sql",
            },
        )

        # Step 5: Cache FLW results
        flw_cache_data = [
            {
                "username": row.username,
                "aggregated_fields": row.custom_fields,
                "total_visits": row.total_visits,
                "approved_visits": row.approved_visits,
                "pending_visits": row.pending_visits,
                "rejected_visits": row.rejected_visits,
                "flagged_visits": row.flagged_visits,
                "first_visit_date": row.first_visit_date,
                "last_visit_date": row.last_visit_date,
            }
            for row in flw_rows
        ]
        cache_manager.store_flw_results(flw_cache_data, total_visits)

        logger.info(f"[SQL] Processed {len(flw_rows)} FLWs, {total_visits} visits (via SQL)")
        return flw_result
