import datetime
from dataclasses import dataclass
from typing import TypedDict

from django.db.models import Count, Min, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.timezone import localdate

from commcare_connect.microplanning.models import WorkArea, WorkAreaStatus
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
    return (today - datetime.timedelta(days=LAST_WEEK_DAYS), today)


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


def target_aggregates(opportunity, group_field) -> dict[GroupKey, TargetAggregate]:
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


def status_aggregates(opportunity, group_field, window) -> dict[GroupKey, StatusAggregate]:
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


def visits_approved_aggregates(opportunity, group_field, window) -> dict[GroupKey, VisitsAggregate]:
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
