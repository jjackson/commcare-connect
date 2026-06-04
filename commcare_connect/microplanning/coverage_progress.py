import datetime
from dataclasses import dataclass
from typing import TypedDict

from django.core.cache import cache
from django.db.models import Count, Min, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.timezone import localdate

from commcare_connect.microplanning.helpers import pct
from commcare_connect.microplanning.models import WorkArea, WorkAreaGroup, WorkAreaStatus
from commcare_connect.opportunity.models import UserVisit, VisitValidationStatus

LAST_WEEK_DAYS = 7

# A group key is a ward slug (str) or a work_area_group_id (int); aggregate dicts are keyed by it.
GroupKey = str | int


class TargetAggregate(TypedDict):
    """Static, filter-independent denominators for one group, as emitted by ``target_aggregates``."""

    target_population: int
    building_count: int
    num_work_areas: int
    expected_visit_total: int


class StatusAggregate(TypedDict):
    """WA-status counts + building sums for one group, as emitted by ``status_aggregates``."""

    WAs_visited: int
    WAs_evc_reached: int
    Buildings_covered_in_WAs_visited: int
    Buildings_covered_in_WAs_evc_reached: int


class VisitsAggregate(TypedDict):
    """Approved-visit count for one group, as emitted by ``visits_approved_aggregates``."""

    visits_approved: int


@dataclass(frozen=True)
class CoverageDateFilter:
    """Page-level date filter. ``overall`` means no date window on no-suffix metrics."""

    start: datetime.date | None = None
    end: datetime.date | None = None

    def __post_init__(self):
        # Invariant: a window is either fully specified or fully absent. A half-specified
        # filter (only one bound) is a programming error, not a silent "overall".
        if (self.start is None) != (self.end is None):
            raise ValueError("CoverageDateFilter requires both start and end, or neither.")

    @classmethod
    def overall(cls) -> "CoverageDateFilter":
        return cls(start=None, end=None)

    @property
    def is_overall(self) -> bool:
        return self.start is None and self.end is None

    @property
    def window(self) -> tuple[datetime.date, datetime.date] | None:
        if self.is_overall:
            return None
        return (self.start, self.end)


def last_week_window() -> tuple[datetime.date, datetime.date]:
    today = localdate()
    return (today - datetime.timedelta(days=LAST_WEEK_DAYS - 1), today)


def non_excluded_workareas(opportunity):
    return WorkArea.objects.filter(opportunity=opportunity).exclude(status=WorkAreaStatus.EXCLUDED)


def status_event_model():
    return WorkArea.pgh_event_model


def _earliest_transition_subquery(status):
    events = status_event_model().objects
    return Subquery(
        events.filter(pgh_obj_id=OuterRef("pk"), status=status)
        .order_by()
        .values("pgh_obj_id")
        .annotate(earliest=Min("pgh_created_at"))
        .values("earliest")[:1]
    )


def annotate_status_timestamps(qs):
    return qs.annotate(
        visited_at=_earliest_transition_subquery(WorkAreaStatus.VISITED),
        evc_reached_at=_earliest_transition_subquery(WorkAreaStatus.EXPECTED_VISIT_REACHED),
    )


def _window_datetime_bounds(window):
    """Convert an inclusive (start, end) *date* window to a half-open [start, end-exclusive) datetime range.

    Callers use ``__gte=start_dt`` AND ``__lt=end_dt``. Because visit_date / pgh_created_at are
    timestamps with sub-second precision, the upper bound is midnight of the day AFTER ``end`` (not
    ``end 23:59:59``) so every instant on the ``end`` day is included.
    """
    start, end = window
    start_dt = timezone.make_aware(datetime.datetime.combine(start, datetime.time.min))
    end_dt = timezone.make_aware(datetime.datetime.combine(end + datetime.timedelta(days=1), datetime.time.min))
    return start_dt, end_dt


def get_target_aggregates(opportunity, group_field) -> dict[GroupKey, TargetAggregate]:
    """Static, filter-independent denominators grouped by ward or work_area_group_id."""
    rows = (
        non_excluded_workareas(opportunity)
        .values(group_field)
        .annotate(
            target_population=Sum("target_population"),
            building_count=Sum("building_count"),
            num_work_areas=Count("id"),
            expected_visit_total=Sum("expected_visit_count"),
        )
    )
    return {row[group_field]: row for row in rows}


def get_status_aggregates(opportunity, group_field, window) -> dict[GroupKey, StatusAggregate]:
    """WA-status counts + building sums per group, strict on current status.

    window=None -> Overall (all current-status WAs). A window applies the
    visited-at / evc-reached-at transition-date filter.
    """
    qs = non_excluded_workareas(opportunity)
    if window is None:
        visited_filter = Q(status=WorkAreaStatus.VISITED)
        evc_filter = Q(status=WorkAreaStatus.EXPECTED_VISIT_REACHED)
    else:
        qs = annotate_status_timestamps(qs)
        start_dt, end_dt = _window_datetime_bounds(window)
        visited_filter = Q(status=WorkAreaStatus.VISITED, visited_at__gte=start_dt, visited_at__lt=end_dt)
        evc_filter = Q(
            status=WorkAreaStatus.EXPECTED_VISIT_REACHED, evc_reached_at__gte=start_dt, evc_reached_at__lt=end_dt
        )

    rows = qs.values(group_field).annotate(
        WAs_visited=Count("id", filter=visited_filter),
        WAs_evc_reached=Count("id", filter=evc_filter),
        Buildings_covered_in_WAs_visited=Coalesce(Sum("building_count", filter=visited_filter), 0),
        Buildings_covered_in_WAs_evc_reached=Coalesce(Sum("building_count", filter=evc_filter), 0),
    )
    return {row[group_field]: row for row in rows}


def get_visits_approved_aggregates(opportunity, group_field, window) -> dict[GroupKey, VisitsAggregate]:
    """Approved-visit counts per group via work_area, dropping EXCLUDED WAs.

    group_field is "ward" or "work_area_group_id"; the join path through work_area
    is "work_area__<group_field>".
    """
    qs = UserVisit.objects.filter(
        opportunity=opportunity,
        status=VisitValidationStatus.approved,
        work_area__isnull=False,
    ).exclude(work_area__status=WorkAreaStatus.EXCLUDED)
    if window is not None:
        start_dt, end_dt = _window_datetime_bounds(window)
        qs = qs.filter(visit_date__gte=start_dt, visit_date__lt=end_dt)

    group_expr = f"work_area__{group_field}"
    rows = qs.values(group_expr).annotate(visits_approved=Count("id"))
    return {row[group_expr]: {group_field: row[group_expr], "visits_approved": row["visits_approved"]} for row in rows}


# Straight percentages: (output column, value key in ``row``, denominator key in ``target``).
_WARD_PCT_OF_TARGET = (
    ("pct_visits_approved", "visits_approved", "expected_visit_total"),
    ("pct_WAs_visited", "WAs_visited", "num_work_areas"),
    ("pct_WAs_visited_last_week", "WAs_visited_last_week", "num_work_areas"),
    ("pct_WAs_evc_reached", "WAs_evc_reached", "num_work_areas"),
    ("pct_WAs_evc_reached_last_week", "WAs_evc_reached_last_week", "num_work_areas"),
    ("pct_Buildings_covered_in_WAs_evc_reached", "Buildings_covered_in_WAs_evc_reached", "building_count"),
    (
        "pct_buildings_covered_in_WAs_evc_reached_last_week",
        "Buildings_covered_in_WAs_evc_reached_last_week",
        "building_count",
    ),
    ("pct_Buildings_covered_in_WAs_visited", "Buildings_covered_in_WAs_visited", "building_count"),
    (
        "pct_buildings_covered_in_WAs_visited_last_week",
        "Buildings_covered_in_WAs_visited_last_week",
        "building_count",
    ),
)

# Ratios of two percentages: (output column, numerator pct column, which visits-pct is the denominator).
# "filtered" -> row["pct_visits_approved"]; "last_week" -> the pinned 7-day visits pct.
_WARD_PCT_RATIOS = (
    ("pct_WA_visited_to_pct_visits", "pct_WAs_visited", "filtered"),
    ("pct_WA_visited_to_pct_visits_last_week", "pct_WAs_visited_last_week", "last_week"),
    ("pct_WA_evc_reached_to_pct_visit", "pct_WAs_evc_reached", "filtered"),
    ("pct_WA_evc_reached_to_pct_visits_last_week", "pct_WAs_evc_reached_last_week", "last_week"),
    ("pct_buildings_covered_in_WA_evc_reached_to_pct_visit", "pct_Buildings_covered_in_WAs_evc_reached", "filtered"),
    (
        "pct_buildings_covered_in_WA_evc_reached_to_pct_visits_last_week",
        "pct_buildings_covered_in_WAs_evc_reached_last_week",
        "last_week",
    ),
    ("pct_buildings_covered_in_WA_visited_to_pct_visit", "pct_Buildings_covered_in_WAs_visited", "filtered"),
    (
        "pct_buildings_covered_in_WA_visited_to_pct_visits_last_week",
        "pct_buildings_covered_in_WAs_visited_last_week",
        "last_week",
    ),
)

# How long a computed coverage slot stays cached.
COVERAGE_CACHE_TTL_SECONDS = 15 * 60


def _get_or_compute(key, compute):
    """Return the cached value at ``key``, computing and caching it on a miss.

    No single-flight lock: this is an admin-only, per-opportunity report, so a cache stampede on a
    cold/expired slot is both rare and cheap, and ``compute`` is idempotent (read-only aggregates),
    so a redundant concurrent compute is harmless.
    """
    cached = cache.get(key)
    if cached is None:
        cached = compute()
        cache.set(key, cached, timeout=COVERAGE_CACHE_TTL_SECONDS)
    return cached


def _static_slot(opportunity):
    def compute():
        return {
            "ward": get_target_aggregates(opportunity, "ward"),
            "wag": get_target_aggregates(opportunity, "work_area_group_id"),
            "wag_display": _wag_display_lookup(opportunity),
        }

    return _get_or_compute(f"coverage:static:opp={opportunity.id}", compute)


def _last_week_slot(opportunity):
    def compute():
        window = last_week_window()
        return {
            "ward_status": get_status_aggregates(opportunity, "ward", window=window),
            "ward_visits": get_visits_approved_aggregates(opportunity, "ward", window=window),
            "wag_status": get_status_aggregates(opportunity, "work_area_group_id", window=window),
            "wag_visits": get_visits_approved_aggregates(opportunity, "work_area_group_id", window=window),
        }

    return _get_or_compute(f"coverage:last_week:opp={opportunity.id}", compute)


def _compute_filtered(opportunity, window):
    return {
        "ward_status": get_status_aggregates(opportunity, "ward", window=window),
        "ward_visits": get_visits_approved_aggregates(opportunity, "ward", window=window),
        "wag_status": get_status_aggregates(opportunity, "work_area_group_id", window=window),
        "wag_visits": get_visits_approved_aggregates(opportunity, "work_area_group_id", window=window),
    }


def _filtered_overall_slot(opportunity):
    return _get_or_compute(
        f"coverage:filtered:opp={opportunity.id}",
        lambda: _compute_filtered(opportunity, window=None),
    )


class CoverageProgressReport:
    """Thin public entry point: holds (opportunity, date_filter), memoizes the 3 cache slots,
    and exposes header()/ward_rows()/wag_rows() returning plain row dicts."""

    def __init__(self, opportunity, date_filter):
        self.opportunity = opportunity
        self.date_filter = date_filter
        self._slots_cache = None

    def _slots(self):
        if self._slots_cache is None:
            static = _static_slot(self.opportunity)
            last_week = _last_week_slot(self.opportunity)
            if self.date_filter.is_overall:
                filtered = _filtered_overall_slot(self.opportunity)
            else:
                filtered = _compute_filtered(self.opportunity, window=self.date_filter.window)
            self._slots_cache = (static, last_week, filtered)
        return self._slots_cache

    def header(self):
        # The saturation goal is an all-time, cumulative figure, so it always uses the overall
        # (unfiltered) status — independent of the page's date filter, which only scopes the rows.
        static, _last_week, _filtered = self._slots()
        overall_status = _filtered_overall_slot(self.opportunity)["ward_status"]
        return {"ward_saturation_goal": ward_saturation_goal(static["ward"], overall_status)}

    def ward_rows(self):
        static, last_week, filtered = self._slots()
        return build_ward_rows(
            static["ward"],
            filtered["ward_status"],
            filtered["ward_visits"],
            last_week["ward_status"],
            last_week["ward_visits"],
        )

    def wag_rows(self):
        static, last_week, filtered = self._slots()
        return build_wag_rows(
            static["wag_display"],
            static["wag"],
            filtered["wag_status"],
            filtered["wag_visits"],
            last_week["wag_status"],
            last_week["wag_visits"],
        )


def ward_saturation_goal(target_aggregates, status_aggregates):
    """Opportunity-wide pct_WAs_evc_reached for the page header: SUM(WAs_evc_reached) / SUM(num_work_areas) * 100.

    target_aggregates / status_aggregates: dicts keyed by ward -> that ward's target / status-count dict.
    Returns None when there are no (non-EXCLUDED) work areas.
    """
    total_work_areas = sum(t["num_work_areas"] for t in target_aggregates.values())
    total_evc_reached = sum(s.get("WAs_evc_reached", 0) for s in status_aggregates.values())
    return pct(total_evc_reached, total_work_areas)


def build_ward_rows(target_aggregates, filtered_status, filtered_visits, last_week_status, last_week_visits):
    """Merge the per-ward aggregate dicts into top-table rows (one row per ward, ~30 columns).

    Each argument is a dict keyed by ward slug -> that ward's aggregate dict:
      - target_aggregates: static targets (target_population, building_count, num_work_areas, expected_visit_total)
      - filtered_status / last_week_status: WA-status counts + building sums (active filter / pinned 7 days)
      - filtered_visits / last_week_visits: approved-visit counts (active filter / pinned 7 days)
    Derived columns are driven by _WARD_PCT_OF_TARGET / _WARD_PCT_RATIOS so the numerator/denominator
    pairing for each column lives in one scannable table. pct/ratio columns are None on a 0 denominator.
    """
    rows = []
    for ward, target in target_aggregates.items():
        status = filtered_status.get(ward, {})
        visits = filtered_visits.get(ward, {})
        lw_status = last_week_status.get(ward, {})
        lw_visits = last_week_visits.get(ward, {})

        # raw counts/sums (default 0 when this ward is absent from an aggregate)
        row = {
            "ward": ward,
            "target_population": target["target_population"],
            "building_count": target["building_count"],
            "num_work_areas": target["num_work_areas"],
            "visits_approved": visits.get("visits_approved", 0),
            "WAs_visited": status.get("WAs_visited", 0),
            "WAs_visited_last_week": lw_status.get("WAs_visited", 0),
            "WAs_evc_reached": status.get("WAs_evc_reached", 0),
            "WAs_evc_reached_last_week": lw_status.get("WAs_evc_reached", 0),
            "Buildings_covered_in_WAs_evc_reached": status.get("Buildings_covered_in_WAs_evc_reached", 0),
            "Buildings_covered_in_WAs_evc_reached_last_week": lw_status.get("Buildings_covered_in_WAs_evc_reached", 0),
            "Buildings_covered_in_WAs_visited": status.get("Buildings_covered_in_WAs_visited", 0),
            "Buildings_covered_in_WAs_visited_last_week": lw_status.get("Buildings_covered_in_WAs_visited", 0),
        }

        # percentages — denominators come from the static targets; numerators read back from the row
        for out_key, value_key, target_key in _WARD_PCT_OF_TARGET:
            row[out_key] = pct(row[value_key], target[target_key])

        # ratios divide one percentage by the matching % visits approved (active filter or pinned 7-day)
        ratio_denominator = {
            "filtered": row["pct_visits_approved"],
            "last_week": pct(lw_visits.get("visits_approved", 0), target["expected_visit_total"]),
        }
        for out_key, pct_key, denom in _WARD_PCT_RATIOS:
            row[out_key] = pct(row[pct_key], ratio_denominator[denom])

        rows.append(row)
    return rows


def _wag_display_lookup(opportunity):
    return {
        g["id"]: {"work_area_group": g["name"], "ward": g["ward"]}
        for g in WorkAreaGroup.objects.filter(opportunity=opportunity).values("id", "name", "ward")
    }


def build_wag_rows(display, target_aggregates, filtered_status, filtered_visits, last_week_status, last_week_visits):
    """Merge the per-work-area-group aggregate dicts into bottom-table rows (one per WAG, reduced columns).

    The five aggregate args are dicts keyed by ``work_area_group_id`` -> that group's aggregate dict (same
    shapes as build_ward_rows). ``display`` maps work_area_group_id -> {"work_area_group", "ward"} for labels
    (see _wag_display_lookup); it is passed in rather than queried here so the lookup can be computed once and
    cached with the other filter-independent data. Returns row dicts (WAGs with no group are skipped); pct
    columns are None on a 0 denominator.
    """
    rows = []
    for wag_id, target in target_aggregates.items():
        if wag_id is None:  # WAs with no group are not shown in the bottom table
            continue
        status = filtered_status.get(wag_id, {})
        visits = filtered_visits.get(wag_id, {})
        lw_status = last_week_status.get(wag_id, {})
        lw_visits = last_week_visits.get(wag_id, {})
        meta = display.get(wag_id, {"work_area_group": None, "ward": None})

        row = {
            "work_area_group_id": wag_id,
            "work_area_group": meta["work_area_group"],
            "ward": meta["ward"],
            "target_population": target["target_population"],
        }
        row["pct_visits_approved"] = pct(visits.get("visits_approved", 0), target["expected_visit_total"])
        row["pct_visits_approved_last_week"] = pct(lw_visits.get("visits_approved", 0), target["expected_visit_total"])
        row["pct_WAs_evc_reached"] = pct(status.get("WAs_evc_reached", 0), target["num_work_areas"])
        row["pct_WAs_evc_reached_last_week"] = pct(lw_status.get("WAs_evc_reached", 0), target["num_work_areas"])
        # pct_WAs_visited is not a bottom-table column; compute inline as the ratio numerator
        row["pct_WA_visited_to_pct_visits"] = pct(
            pct(status.get("WAs_visited", 0), target["num_work_areas"]), row["pct_visits_approved"]
        )
        row["pct_WA_visited_to_pct_visits_last_week"] = pct(
            pct(lw_status.get("WAs_visited", 0), target["num_work_areas"]), row["pct_visits_approved_last_week"]
        )
        rows.append(row)
    return rows
