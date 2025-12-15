"""
Python/Redis backend implementation.

Uses Redis/file caching with pandas-based computation.
"""

import logging
from collections.abc import Generator
from typing import Any

import httpx
import pandas as pd
from django.conf import settings
from django.http import HttpRequest

from commcare_connect.labs.analysis.backends.csv_parsing import parse_csv_bytes
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
            csv_bytes = self._fetch_from_api(opportunity_id, access_token)

            visit_count = csv_bytes.count(b"\n") - 1 if csv_bytes else 0
            cache.set("user_visits_csv", csv_bytes, visit_count)
            logger.info(f"[PythonRedis] Cached raw CSV ({len(csv_bytes)} bytes)")

        # Parse with unified parser (handles both filter and skip_form_json)
        return parse_csv_bytes(
            csv_bytes,
            opportunity_id,
            skip_form_json=skip_form_json,
            filter_visit_ids=filter_visit_ids,
        )

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
                visit_dicts = parse_csv_bytes(csv_bytes, opportunity_id, skip_form_json=False)
                yield ("cached", visit_dicts)
                return

        # Cache miss - stream download
        logger.info(f"[PythonRedis] Raw cache MISS for opp {opportunity_id}, streaming from API")

        url = f"{settings.CONNECT_PRODUCTION_URL}/export/opportunity/{opportunity_id}/user_visits/"
        headers = {"Authorization": f"Bearer {access_token}"}

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
                    bytes_downloaded += len(chunk)

                    # Yield progress every 5MB for real-time UI updates
                    if bytes_downloaded - last_progress_at >= progress_interval:
                        yield ("progress", bytes_downloaded, total_bytes)
                        last_progress_at = bytes_downloaded

                # Always yield final progress to ensure UI shows 100%
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

        # Yield status before slow CSV parsing so frontend can show progress
        yield ("parsing", len(csv_bytes))

        # Parse and return
        visit_dicts = parse_csv_bytes(csv_bytes, opportunity_id, skip_form_json=False)
        yield ("complete", visit_dicts)

    def has_valid_raw_cache(self, opportunity_id: int, expected_visit_count: int) -> bool:
        """Check if valid raw cache exists."""
        cache = RawAPICacheManager(opportunity_id)
        cached_data = cache.get("user_visits_csv")
        return cached_data is not None and cache.is_valid(cached_data, expected_visit_count)

    def _fetch_from_api(self, opportunity_id: int, access_token: str) -> bytes:
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

    # -------------------------------------------------------------------------
    # Visit Filtering (for Audit)
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
        Filter visits using pandas on cached data.

        Fetches slim visits (no form_json) and applies filters in pandas.
        """
        # Fetch slim visits (no form_json for efficiency)
        visits = self.fetch_raw_visits(
            opportunity_id=opportunity_id,
            access_token=access_token,
            expected_visit_count=expected_visit_count,
            skip_form_json=True,
        )

        if not visits:
            return ([], []) if return_visit_data else []

        # Apply pandas filtering
        df = pd.DataFrame(visits)

        if "id" not in df.columns:
            return ([], []) if return_visit_data else []

        # Parse dates for filtering
        if "visit_date" in df.columns:
            df["visit_date"] = pd.to_datetime(df["visit_date"], format="mixed", utc=True, errors="coerce")

        # Filter by usernames
        if usernames and "username" in df.columns:
            df = df[df["username"].isin(usernames)]

        # Filter by date range
        if start_date and "visit_date" in df.columns:
            start = pd.to_datetime(start_date)
            df = df[df["visit_date"].dt.date >= start.date()]

        if end_date and "visit_date" in df.columns:
            end = pd.to_datetime(end_date)
            df = df[df["visit_date"].dt.date <= end.date()]

        # Apply last_n_per_user (window function equivalent)
        if last_n_per_user and "visit_date" in df.columns and "username" in df.columns:
            df = df.sort_values("visit_date", ascending=False)
            df = df.groupby("username", dropna=False).head(last_n_per_user)

        # Apply last_n_total
        if last_n_total and "visit_date" in df.columns:
            df = df.sort_values("visit_date", ascending=False)
            df = df.head(last_n_total)

        # Apply sampling
        if sample_percentage < 100 and len(df) > 0:
            sample_size = max(1, int(len(df) * sample_percentage / 100))
            df = df.sample(n=min(sample_size, len(df)), random_state=42)

        # Extract results
        visit_ids = df["id"].dropna().astype(int).unique().tolist()

        if return_visit_data:
            # Convert visit_date back to string for JSON compatibility
            if "visit_date" in df.columns:
                df["visit_date"] = df["visit_date"].apply(lambda x: x.isoformat() if pd.notna(x) else None)
            filtered_visits = df.to_dict("records")
            return visit_ids, filtered_visits

        return visit_ids
