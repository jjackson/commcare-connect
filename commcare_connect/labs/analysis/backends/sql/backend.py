"""
SQL backend implementation.

Uses PostgreSQL tables for caching AND computation.
All analysis is done via SQL queries, not Python/pandas.
"""

import logging
from collections.abc import Generator
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import httpx
import sentry_sdk
from django.conf import settings
from django.http import HttpRequest
from django.utils.dateparse import parse_date

from commcare_connect.labs.analysis.backends.csv_parsing import parse_csv_bytes
from commcare_connect.labs.analysis.backends.sql.cache import SQLCacheManager
from commcare_connect.labs.analysis.backends.sql.query_builder import execute_flw_aggregation, execute_visit_extraction
from commcare_connect.labs.analysis.config import AnalysisPipelineConfig, CacheStage
from commcare_connect.labs.analysis.models import FLWAnalysisResult, FLWRow, VisitAnalysisResult, VisitRow

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
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept-Encoding": "gzip, deflate",
        }

        # Use shared progress interval from SSE streaming module
        from commcare_connect.labs.analysis.sse_streaming import DOWNLOAD_PROGRESS_INTERVAL_BYTES

        chunks = []
        bytes_downloaded = 0
        progress_interval = DOWNLOAD_PROGRESS_INTERVAL_BYTES  # 5MB progress intervals

        try:
            with httpx.stream("GET", url, headers=headers, timeout=580.0) as response:
                response.raise_for_status()
                total_bytes = int(response.headers.get("content-length", 0))
                last_progress_at = 0

                for chunk in response.iter_bytes(chunk_size=65536):
                    chunks.append(chunk)
                    # Use num_bytes_downloaded to track actual network traffic (compressed bytes)
                    bytes_downloaded = response.num_bytes_downloaded

                    # Yield progress every 5MB for real-time UI updates
                    if bytes_downloaded - last_progress_at >= progress_interval:
                        yield ("progress", bytes_downloaded, total_bytes)
                        last_progress_at = bytes_downloaded

                # Always yield final progress to ensure UI shows 100%
                if bytes_downloaded > last_progress_at:
                    yield ("progress", bytes_downloaded, total_bytes)

        except httpx.TimeoutException as e:
            logger.error(f"[SQL] Timeout downloading for opp {opportunity_id}: {e}")
            sentry_sdk.capture_exception(e)
            raise RuntimeError("Connect API timeout") from e

        csv_bytes = b"".join(chunks)

        # Yield status before slow CSV parsing so frontend can show progress
        yield ("parsing", len(csv_bytes))

        visit_dicts = parse_csv_bytes(csv_bytes, opportunity_id, skip_form_json=False)

        # NOTE: Don't store to SQL here - let process_and_cache handle it.
        # Storage happens in process_and_cache after pipeline yields "Processing X visits..."

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
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept-Encoding": "gzip, deflate",
        }

        try:
            response = httpx.get(url, headers=headers, timeout=580.0)
            response.raise_for_status()
            return response.content
        except httpx.TimeoutException as e:
            logger.error(f"[SQL] Timeout fetching visits for opp {opportunity_id}: {e}")
            sentry_sdk.capture_exception(e)
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
        """Get cached visit result if valid, applying filters at query time."""
        cache_manager = SQLCacheManager(opportunity_id, config)

        if not cache_manager.has_valid_computed_visit_cache(visit_count):
            return None

        logger.info(f"[SQL] Visit cache HIT for opp {opportunity_id}")

        # Load computed visits (no join needed - all fields are in ComputedVisitCache now)
        computed_qs = cache_manager.get_computed_visits_queryset()

        # Apply filters at query time (OPTIMIZATION: filters not in cache hash)
        if config.filters:
            for key, value in config.filters.items():
                # entity_id is a column, filter directly
                if key == "entity_id":
                    computed_qs = computed_qs.filter(entity_id=value)
                    logger.info(f"[SQL] Applying entity_id filter: {value}")
                # All other filters are treated as computed field filters
                # This enables linking by fields like beneficiary_case_id, rutf_case_id, etc.
                else:
                    # Use Django's JSONB contains lookup for exact match
                    computed_qs = computed_qs.filter(computed_fields__contains={key: value})
                    logger.info(f"[SQL] Applying computed field filter: {key}={value}")

        # Build VisitRow objects directly from ComputedVisitCache
        visit_rows = []
        for cached_row in computed_qs:
            # Parse GPS from location string (format: "lat lon alt accuracy")
            latitude, longitude, accuracy = None, None, None
            if cached_row.location:
                parts = cached_row.location.split()
                if len(parts) >= 2:
                    try:
                        latitude = float(parts[0])
                        longitude = float(parts[1])
                        if len(parts) >= 4:
                            accuracy = float(parts[3])
                    except (ValueError, IndexError):
                        pass

            visit_row = VisitRow(
                id=str(cached_row.visit_id),
                user_id=None,
                username=cached_row.username,
                visit_date=datetime.combine(cached_row.visit_date, datetime.min.time())
                if cached_row.visit_date
                else None,
                status=cached_row.status,
                flagged=cached_row.flagged,
                latitude=latitude,
                longitude=longitude,
                accuracy_in_m=accuracy,
                deliver_unit_id=cached_row.deliver_unit_id,
                deliver_unit_name=cached_row.deliver_unit,
                entity_id=cached_row.entity_id,
                entity_name=cached_row.entity_name,
                computed=cached_row.computed_fields,
            )
            visit_rows.append(visit_row)

        # Build field metadata from config
        field_metadata = [{"name": f.name, "description": f.description} for f in config.fields]

        return VisitAnalysisResult(
            opportunity_id=opportunity_id,
            rows=visit_rows,
            metadata={"total_visits": len(visit_rows), "from_sql_cache": True},
            field_metadata=field_metadata,
        )

    def process_and_cache(
        self,
        request: HttpRequest,
        config: AnalysisPipelineConfig,
        opportunity_id: int,
        visit_dicts: list[dict],
    ) -> FLWAnalysisResult | VisitAnalysisResult:
        """
        Process visits using SQL and cache results.

        For VISIT_LEVEL:
        1. Store raw visits in SQL
        2. Execute visit extraction query (no aggregation)
        3. Cache computed visits and return VisitAnalysisResult

        For AGGREGATED:
        1. Store raw visits in SQL
        2. Execute FLW aggregation query
        3. Cache and return FLWAnalysisResult
        """
        cache_manager = SQLCacheManager(opportunity_id, config)
        visit_count = len(visit_dicts)

        # Step 1: Store raw visits to SQL (idempotent - replaces existing)
        logger.info(f"[SQL] Storing {visit_count} raw visits to SQL")
        cache_manager.store_raw_visits(visit_dicts, visit_count)

        # Branch based on terminal stage
        if config.terminal_stage == CacheStage.VISIT_LEVEL:
            return self._process_visit_level(config, opportunity_id, visit_count, cache_manager)
        else:
            return self._process_flw_level(config, opportunity_id, visit_count, cache_manager)

    def _process_visit_level(
        self,
        config: AnalysisPipelineConfig,
        opportunity_id: int,
        visit_count: int,
        cache_manager: SQLCacheManager,
    ) -> VisitAnalysisResult:
        """Process and cache visit-level analysis (no aggregation)."""
        logger.info("[SQL] Executing visit extraction query")
        visit_data, computed_field_names = execute_visit_extraction(config, opportunity_id)

        # Build VisitRow objects
        visit_rows = []
        for row in visit_data:
            # Parse GPS from location string (format: "lat lon alt accuracy")
            latitude, longitude, accuracy = None, None, None
            location = row.get("location") or ""
            if location:
                parts = location.split()
                if len(parts) >= 2:
                    try:
                        latitude = float(parts[0])
                        longitude = float(parts[1])
                        if len(parts) >= 4:
                            accuracy = float(parts[3])
                    except (ValueError, IndexError):
                        pass

            # Separate computed fields from base fields
            computed = {name: row.get(name) for name in computed_field_names}

            # Apply post-processing transforms that need full visit context
            # (e.g., extract_images_with_question_ids needs both form_json and images)
            for field in config.fields:
                if field.name not in computed_field_names:
                    continue

                if field.transform and callable(field.transform):
                    # Check if this transform needs full visit data (has form_json/images params)
                    import inspect

                    sig = inspect.signature(field.transform)
                    params = list(sig.parameters.keys())

                    # If transform takes 'visit_data' param, it needs full context
                    if "visit_data" in params or len(params) == 0:
                        try:
                            import json

                            # Build full visit dict for transform
                            # Note: form_json and images come back as JSON strings from SQL
                            form_json = row.get("form_json", {})
                            if isinstance(form_json, str):
                                form_json = json.loads(form_json) if form_json else {}

                            images = row.get("images", [])
                            if isinstance(images, str):
                                images = json.loads(images) if images else []

                            visit_dict = {
                                "form_json": form_json,
                                "images": images,
                                "username": row.get("username"),
                                "visit_date": row.get("visit_date"),
                                "entity_name": row.get("entity_name"),
                            }
                            computed[field.name] = field.transform(visit_dict)
                        except Exception as e:
                            logger.warning(f"Transform for {field.name} failed: {e}")
                            computed[field.name] = None

            # Parse visit_date
            visit_date_val = row.get("visit_date")
            if visit_date_val and isinstance(visit_date_val, date):
                visit_date_val = datetime.combine(visit_date_val, datetime.min.time())

            visit_row = VisitRow(
                id=str(row.get("visit_id", "")),
                user_id=None,
                username=row.get("username", ""),
                visit_date=visit_date_val,
                status=row.get("status", ""),
                flagged=row.get("flagged", False),
                latitude=latitude,
                longitude=longitude,
                accuracy_in_m=accuracy,
                deliver_unit_id=row.get("deliver_unit_id"),
                deliver_unit_name=row.get("deliver_unit", ""),
                entity_id=row.get("entity_id", ""),
                entity_name=row.get("entity_name", ""),
                computed=computed,
            )
            visit_rows.append(visit_row)

        # Cache computed visits (store base fields as columns to avoid joins later)
        computed_cache_data = [
            {
                "visit_id": int(row.id),
                "username": row.username,
                "visit_date": row.visit_date.date() if row.visit_date else None,
                "status": row.status,
                "flagged": row.flagged,
                "location": row.location
                if hasattr(row, "location")
                else (f"{row.latitude} {row.longitude}" if row.latitude and row.longitude else ""),
                "deliver_unit": row.deliver_unit_name,
                "deliver_unit_id": row.deliver_unit_id,
                "entity_id": row.entity_id,
                "entity_name": row.entity_name,
                "computed_fields": row.computed,
            }
            for row in visit_rows
        ]
        cache_manager.store_computed_visits(computed_cache_data, visit_count)

        # Build field metadata from config
        field_metadata = [{"name": f.name, "description": f.description} for f in config.fields]

        visit_result = VisitAnalysisResult(
            opportunity_id=opportunity_id,
            rows=visit_rows,
            metadata={
                "total_visits": len(visit_rows),
                "computed_via": "sql",
            },
            field_metadata=field_metadata,
        )

        logger.info(f"[SQL] Processed {len(visit_rows)} visits with {len(computed_field_names)} computed fields")
        return visit_result

    def _process_flw_level(
        self,
        config: AnalysisPipelineConfig,
        opportunity_id: int,
        visit_count: int,
        cache_manager: SQLCacheManager,
    ) -> FLWAnalysisResult:
        """
        Process and cache FLW-level aggregation.

        Like Python/Redis backend, we ALWAYS cache visit-level first,
        then aggregate to FLW. This allows visit-level cache to be
        reused by coverage map and other visit-level consumers.
        """
        # Step 1: Extract and cache visit-level data first (for cache sharing)
        logger.info("[SQL] Step 1: Extracting visit-level data for cache")
        visit_data, computed_field_names = execute_visit_extraction(config, opportunity_id)

        # Cache computed visits (so coverage can reuse this)
        computed_cache_data = [
            {
                "visit_id": v.get("visit_id", 0),
                "username": v.get("username", ""),
                "computed_fields": {name: v.get(name) for name in computed_field_names},
            }
            for v in visit_data
        ]
        cache_manager.store_computed_visits(computed_cache_data, visit_count)
        logger.info(f"[SQL] Cached {len(computed_cache_data)} visit-level rows")

        # Step 2: Execute FLW aggregation query
        logger.info("[SQL] Step 2: Executing FLW aggregation query")
        flw_data = execute_flw_aggregation(config, opportunity_id)

        # Convert to FLWRow objects
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

        # Build result
        flw_result = FLWAnalysisResult(
            opportunity_id=opportunity_id,
            rows=flw_rows,
            metadata={
                "total_visits": total_visits,
                "total_flws": len(flw_rows),
                "computed_via": "sql",
            },
        )

        # Cache FLW results
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

    # -------------------------------------------------------------------------
    # Visit Filtering (for Audit) - SQL-optimized
    # -------------------------------------------------------------------------

    def filter_visits_for_audit(
        self,
        opportunity_id: int,
        access_token: str,
        expected_visit_count: int | None,
        usernames: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        last_n_per_user: int | None = None,
        last_n_total: int | None = None,
        sample_percentage: int = 100,
        return_visit_data: bool = False,
    ) -> list[int] | tuple[list[int], list[dict]]:
        """
        Filter visits using SQL queries (much faster than Python/pandas).

        Pushes all filtering into PostgreSQL using indexes and window functions.
        """
        cache_manager = SQLCacheManager(opportunity_id, config=None)

        # Ensure cache is populated
        if not cache_manager.has_valid_raw_cache(expected_visit_count or 0):
            logger.info(f"[SQL] Cache miss during filter, populating for opp {opportunity_id}")
            self.fetch_raw_visits(opportunity_id, access_token, expected_visit_count)

        # Parse date strings to date objects
        start_date_obj: date | None = None
        end_date_obj: date | None = None
        if start_date:
            start_date_obj = parse_date(start_date)
        if end_date:
            end_date_obj = parse_date(end_date)

        if return_visit_data:
            # Get both IDs and slim visit data in one query
            visits = cache_manager.get_filtered_visits_slim(
                usernames=usernames,
                start_date=start_date_obj,
                end_date=end_date_obj,
                last_n_per_user=last_n_per_user,
                last_n_total=last_n_total,
                sample_percentage=sample_percentage,
            )
            visit_ids = [v["id"] for v in visits]
            logger.info(f"[SQL] Filtered to {len(visit_ids)} visits (with data)")
            return visit_ids, visits
        else:
            # Get only IDs (fastest path)
            visit_ids = cache_manager.get_filtered_visit_ids(
                usernames=usernames,
                start_date=start_date_obj,
                end_date=end_date_obj,
                last_n_per_user=last_n_per_user,
                last_n_total=last_n_total,
                sample_percentage=sample_percentage,
            )
            logger.info(f"[SQL] Filtered to {len(visit_ids)} visit IDs")
            return visit_ids
