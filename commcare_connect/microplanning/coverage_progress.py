import datetime
from dataclasses import dataclass

from django.db.models import Min, OuterRef, Subquery
from django.utils.timezone import localdate

from commcare_connect.microplanning.models import WorkArea, WorkAreaStatus

LAST_WEEK_DAYS = 7


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
