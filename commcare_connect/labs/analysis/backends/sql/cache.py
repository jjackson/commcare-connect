"""
SQL cache manager for the analysis framework.

Handles reading/writing cache data to PostgreSQL tables.
"""

import logging
from datetime import date, datetime, timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from commcare_connect.labs.analysis.backends.sql.models import ComputedFLWCache, ComputedVisitCache, RawVisitCache
from commcare_connect.labs.analysis.config import AnalysisPipelineConfig
from commcare_connect.labs.analysis.utils import get_config_hash

logger = logging.getLogger(__name__)

# Default cache TTL (1 hour)
DEFAULT_TTL_HOURS = 1


def _parse_date(value) -> date | None:
    """Parse a date value from various formats."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        # Try parsing as datetime first (for ISO format with time)
        dt = parse_datetime(value)
        if dt:
            return dt.date()
        # Try parsing as date
        return parse_date(value)
    return None


def _parse_datetime(value) -> datetime | None:
    """Parse a datetime value from various formats."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return parse_datetime(value)
    return None


class SQLCacheManager:
    """
    Manages SQL-based caching for analysis results.

    Three cache levels:
    - Raw visits: One row per visit, shared across configs
    - Computed visits: One row per visit per config
    - Computed FLWs: One row per FLW per config
    """

    def __init__(self, opportunity_id: int, config: AnalysisPipelineConfig | None = None):
        self.opportunity_id = opportunity_id
        self.config = config
        self.config_hash = get_config_hash(config) if config else None
        self.ttl = timedelta(hours=DEFAULT_TTL_HOURS)

    def _get_expires_at(self):
        return timezone.now() + self.ttl

    # -------------------------------------------------------------------------
    # Raw Visit Cache
    # -------------------------------------------------------------------------

    def has_valid_raw_cache(self, expected_visit_count: int) -> bool:
        """Check if we have valid raw visit cache."""
        return RawVisitCache.objects.filter(
            opportunity_id=self.opportunity_id,
            visit_count__gte=expected_visit_count,
            expires_at__gt=timezone.now(),
        ).exists()

    def get_raw_visit_count(self) -> int:
        """Get count of cached raw visits."""
        return RawVisitCache.objects.filter(
            opportunity_id=self.opportunity_id,
            expires_at__gt=timezone.now(),
        ).count()

    def store_raw_visits(self, visit_dicts: list[dict], visit_count: int):
        """
        Store raw visit data to SQL cache.

        Args:
            visit_dicts: List of visit dicts from CSV parsing
            visit_count: Total visit count for invalidation
        """
        expires_at = self._get_expires_at()

        # Clear old cache for this opportunity
        RawVisitCache.objects.filter(opportunity_id=self.opportunity_id).delete()

        # Bulk create new rows
        rows = []
        for v in visit_dicts:
            rows.append(
                RawVisitCache(
                    opportunity_id=self.opportunity_id,
                    visit_count=visit_count,
                    expires_at=expires_at,
                    visit_id=v.get("id", 0),
                    username=v.get("username") or "",
                    deliver_unit=v.get("deliver_unit") or "",
                    deliver_unit_id=v.get("deliver_unit_id"),
                    entity_id=v.get("entity_id") or "",
                    entity_name=v.get("entity_name") or "",
                    visit_date=_parse_date(v.get("visit_date")),
                    status=v.get("status") or "",
                    reason=v.get("reason") or "",
                    location=v.get("location") or "",
                    flagged=v.get("flagged") or False,
                    flag_reason=v.get("flag_reason") or {},
                    form_json=v.get("form_json") or {},
                    completed_work=v.get("completed_work") or {},
                    status_modified_date=_parse_datetime(v.get("status_modified_date")),
                    review_status=v.get("review_status") or "",
                    review_created_on=_parse_datetime(v.get("review_created_on")),
                    justification=v.get("justification") or "",
                    date_created=_parse_datetime(v.get("date_created")),
                    completed_work_id=v.get("completed_work_id"),
                    images=v.get("images") or [],
                )
            )

        with transaction.atomic():
            RawVisitCache.objects.bulk_create(rows, batch_size=1000)

        logger.info(f"[SQLCache] Stored {len(rows)} raw visits for opp {self.opportunity_id}")

    def get_raw_visits_queryset(self):
        """Get queryset of cached raw visits."""
        return RawVisitCache.objects.filter(
            opportunity_id=self.opportunity_id,
            expires_at__gt=timezone.now(),
        )

    # -------------------------------------------------------------------------
    # Computed Visit Cache
    # -------------------------------------------------------------------------

    def has_valid_computed_visit_cache(self, expected_visit_count: int) -> bool:
        """Check if we have valid computed visit cache for this config."""
        if not self.config_hash:
            return False
        return ComputedVisitCache.objects.filter(
            opportunity_id=self.opportunity_id,
            config_hash=self.config_hash,
            visit_count__gte=expected_visit_count,
            expires_at__gt=timezone.now(),
        ).exists()

    def store_computed_visits(self, visits_data: list[dict], visit_count: int):
        """
        Store computed visit results.

        Args:
            visits_data: List of dicts with visit_id, username, computed_fields
            visit_count: Total visit count for invalidation
        """
        if not self.config_hash:
            return

        expires_at = self._get_expires_at()

        # Clear old cache for this config
        ComputedVisitCache.objects.filter(
            opportunity_id=self.opportunity_id,
            config_hash=self.config_hash,
        ).delete()

        rows = [
            ComputedVisitCache(
                opportunity_id=self.opportunity_id,
                config_hash=self.config_hash,
                visit_count=visit_count,
                expires_at=expires_at,
                visit_id=v["visit_id"],
                username=v["username"],
                computed_fields=v["computed_fields"],
            )
            for v in visits_data
        ]

        with transaction.atomic():
            ComputedVisitCache.objects.bulk_create(rows, batch_size=1000)

        logger.info(f"[SQLCache] Stored {len(rows)} computed visits for opp {self.opportunity_id}")

    def get_computed_visits_queryset(self):
        """Get queryset of computed visits for this config."""
        if not self.config_hash:
            return ComputedVisitCache.objects.none()
        return ComputedVisitCache.objects.filter(
            opportunity_id=self.opportunity_id,
            config_hash=self.config_hash,
            expires_at__gt=timezone.now(),
        )

    # -------------------------------------------------------------------------
    # Computed FLW Cache
    # -------------------------------------------------------------------------

    def has_valid_flw_cache(self, expected_visit_count: int) -> bool:
        """Check if we have valid FLW cache for this config."""
        if not self.config_hash:
            return False
        return ComputedFLWCache.objects.filter(
            opportunity_id=self.opportunity_id,
            config_hash=self.config_hash,
            visit_count__gte=expected_visit_count,
            expires_at__gt=timezone.now(),
        ).exists()

    def store_flw_results(self, flw_data: list[dict], visit_count: int):
        """
        Store aggregated FLW results.

        Args:
            flw_data: List of dicts with FLW aggregated data
            visit_count: Total visit count for invalidation
        """
        if not self.config_hash:
            return

        expires_at = self._get_expires_at()

        # Clear old cache for this config
        ComputedFLWCache.objects.filter(
            opportunity_id=self.opportunity_id,
            config_hash=self.config_hash,
        ).delete()

        rows = [
            ComputedFLWCache(
                opportunity_id=self.opportunity_id,
                config_hash=self.config_hash,
                visit_count=visit_count,
                expires_at=expires_at,
                username=f["username"],
                aggregated_fields=f.get("aggregated_fields", {}),
                total_visits=f.get("total_visits", 0),
                approved_visits=f.get("approved_visits", 0),
                pending_visits=f.get("pending_visits", 0),
                rejected_visits=f.get("rejected_visits", 0),
                flagged_visits=f.get("flagged_visits", 0),
                first_visit_date=f.get("first_visit_date"),
                last_visit_date=f.get("last_visit_date"),
            )
            for f in flw_data
        ]

        with transaction.atomic():
            ComputedFLWCache.objects.bulk_create(rows, batch_size=1000)

        logger.info(f"[SQLCache] Stored {len(rows)} FLW results for opp {self.opportunity_id}")

    def get_flw_results_queryset(self):
        """Get queryset of FLW results for this config."""
        if not self.config_hash:
            return ComputedFLWCache.objects.none()
        return ComputedFLWCache.objects.filter(
            opportunity_id=self.opportunity_id,
            config_hash=self.config_hash,
            expires_at__gt=timezone.now(),
        )

    # -------------------------------------------------------------------------
    # Cache Invalidation
    # -------------------------------------------------------------------------

    def invalidate_all(self):
        """Invalidate all cache for this opportunity."""
        RawVisitCache.objects.filter(opportunity_id=self.opportunity_id).delete()
        ComputedVisitCache.objects.filter(opportunity_id=self.opportunity_id).delete()
        ComputedFLWCache.objects.filter(opportunity_id=self.opportunity_id).delete()
        logger.info(f"[SQLCache] Invalidated all cache for opp {self.opportunity_id}")

    # -------------------------------------------------------------------------
    # Visit Filtering (for Audit)
    # -------------------------------------------------------------------------

    def filter_visits(
        self,
        usernames: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        last_n_per_user: int | None = None,
        last_n_total: int | None = None,
        sample_percentage: int = 100,
    ):
        """
        Build a filtered queryset of visits using SQL.

        Returns a queryset that can be further processed or converted to values.
        Uses window functions for last_n_per_user (much faster than Python groupby).
        """
        from django.db.models import F, Window
        from django.db.models.functions import RowNumber

        # Start with base queryset (valid cache)
        qs = self.get_raw_visits_queryset()

        # Filter by usernames
        if usernames:
            qs = qs.filter(username__in=usernames)

        # Filter by date range
        if start_date:
            qs = qs.filter(visit_date__gte=start_date)
        if end_date:
            qs = qs.filter(visit_date__lte=end_date)

        # Apply last_n_per_user using window function
        if last_n_per_user:
            # Add row number partitioned by username, ordered by visit_date desc
            qs = qs.annotate(
                row_num=Window(
                    expression=RowNumber(),
                    partition_by=[F("username")],
                    order_by=F("visit_date").desc(),
                )
            ).filter(row_num__lte=last_n_per_user)

        # Apply last_n_total
        if last_n_total:
            qs = qs.order_by("-visit_date")[:last_n_total]

        # Apply sampling (using random ordering)
        # Note: For large datasets, TABLESAMPLE would be better but isn't portable
        if sample_percentage < 100:
            # Get count first, then limit
            total_count = qs.count()
            sample_size = max(1, int(total_count * sample_percentage / 100))
            # Order by random and take sample_size
            qs = qs.order_by("?")[:sample_size]

        return qs

    def get_filtered_visit_ids(
        self,
        usernames: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        last_n_per_user: int | None = None,
        last_n_total: int | None = None,
        sample_percentage: int = 100,
    ) -> list[int]:
        """Get filtered visit IDs using SQL. Returns only IDs (very fast)."""
        qs = self.filter_visits(
            usernames=usernames,
            start_date=start_date,
            end_date=end_date,
            last_n_per_user=last_n_per_user,
            last_n_total=last_n_total,
            sample_percentage=sample_percentage,
        )
        return list(qs.values_list("visit_id", flat=True))

    def get_filtered_visits_slim(
        self,
        usernames: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        last_n_per_user: int | None = None,
        last_n_total: int | None = None,
        sample_percentage: int = 100,
    ) -> list[dict]:
        """
        Get filtered visits WITHOUT form_json (slim mode).

        Returns visit dicts suitable for preview display.
        """
        qs = self.filter_visits(
            usernames=usernames,
            start_date=start_date,
            end_date=end_date,
            last_n_per_user=last_n_per_user,
            last_n_total=last_n_total,
            sample_percentage=sample_percentage,
        )

        # Defer heavy columns
        qs = qs.defer("form_json", "completed_work", "flag_reason")

        visits = []
        for row in qs.iterator():
            visits.append(
                {
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
                    "review_status": row.review_status,
                    "images": row.images,
                }
            )

        logger.info(f"[SQLCache] Filtered to {len(visits)} visits (slim)")
        return visits
