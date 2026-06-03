import datetime
from dataclasses import dataclass

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
