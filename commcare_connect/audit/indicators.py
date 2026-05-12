from __future__ import annotations

from django.db.models import Count, Max, Q

from commcare_connect.microplanning.models import WorkArea, WorkAreaGroup, WorkAreaStatus
from commcare_connect.opportunity.models import UserVisit

_TERMINAL_STATUSES = [
    WorkAreaStatus.VISITED,
    WorkAreaStatus.INACCESSIBLE,
    WorkAreaStatus.EXCLUDED,
    WorkAreaStatus.EXPECTED_VISIT_REACHED,
]

# A WAG is fully closed only when every WA has reached one of these statuses.
# VISITED is excluded — it means visits started but expected count not yet reached.
_CLOSED_STATUSES = [
    WorkAreaStatus.EXPECTED_VISIT_REACHED,
    WorkAreaStatus.EXCLUDED,
    WorkAreaStatus.INACCESSIBLE,
]

# form_json field path constants — paths are relative to form_json["form"], using __ for nesting
_GENDER_FIELD = "additional_case_info__childs_gender"  # values: "female_child" / "male_child"
_FEMALE_VALUE = "female_child"
_AGE_FIELD = "additional_case_info__childs_age_in_month"  # integer months
_DOB_FIELD = "additional_case_info__childs_dob"  # exclude when present (age is auto-calculated)

_MUAC_MEASUREMENT_FIELD = "muac_group__muac_display_group_1__soliciter_muac_cm"  # float cm
_MUAC_PHOTO_LINK_FIELD = "muac_group__muac_photo_link"  # URL (non-empty = photo taken)
_MUAC_CONSENT_FIELD = "muac_group__muac_consent_group__muac_consent"
_MUAC_CONSENT_YES = "yes"

_VACCINE_FIELD = "pictures__received_any_vaccine"  # values: "yes" / "no"
_VACCINE_YES_VALUE = "yes"
_VACCINE_CARD_LINK_FIELD = "immunization_photo_group__photo_link_vaccine"  # URL (non-empty = photo taken)

_MUAC_BIN_EDGES = [9.5, 10.5, 11.5, 12.5, 13.5, 14.5, 15.5, 16.5, 17.5, 18.5, 19.5, 20.5, 21.5]


def _last_n_visits(opportunity_access, n, period_end, **filters):
    """Return a queryset of the last n visit IDs (as of period_end) for use in id__in filters."""
    return (
        UserVisit.objects.filter(
            opportunity_access=opportunity_access,
            visit_date__date__lte=period_end,
            **filters,
        )
        .order_by("-visit_date")
        .values("id")[:n]
    )


def _q_link_present(form_field) -> Q:
    """Return a Q that matches when a form URL link field is non-null and non-empty."""
    path = f"form_json__form__{form_field}"
    return Q(**{f"{path}__isnull": False}) & ~Q(**{path: ""})


def _find_active_wag(opportunity_access) -> WorkAreaGroup | None:
    """Return the FLW's current active WAG: has non-terminal WAs, most terminal WAs (furthest along)."""
    wag_stats = (
        WorkArea.objects.filter(
            opportunity_access=opportunity_access,
            work_area_group__isnull=False,
        )
        .values("work_area_group_id")
        .annotate(
            terminal_count=Count("id", filter=Q(status__in=_TERMINAL_STATUSES)),
            non_terminal_count=Count("id", filter=~Q(status__in=_TERMINAL_STATUSES)),
        )
    )

    active_wag_id = None
    max_terminal = -1
    for stats in wag_stats:
        if stats["non_terminal_count"] > 0 and stats["terminal_count"] > max_terminal:
            active_wag_id = stats["work_area_group_id"]
            max_terminal = stats["terminal_count"]

    if active_wag_id is None:
        return None
    return WorkAreaGroup.objects.get(id=active_wag_id)


def _find_last_completed_wag(opportunity_access, period_start, period_end) -> WorkAreaGroup | None:
    """Return the most recently closed WAG that had visits in the current reporting period.

    A WAG is closed when every WA has reached a _CLOSED_STATUSES state.
    The period filter ensures we only surface a WAG that was actively worked
    this week — a WAG closed in a prior week returns None so the indicator
    shows N/A instead of a stale rate.
    """
    wag_stats = (
        WorkArea.objects.filter(
            opportunity_access=opportunity_access,
            work_area_group__isnull=False,
        )
        .values("work_area_group_id")
        .annotate(
            total=Count("id"),
            closed_count=Count("id", filter=Q(status__in=_CLOSED_STATUSES)),
        )
    )

    completed_ids = [s["work_area_group_id"] for s in wag_stats if s["total"] > 0 and s["total"] == s["closed_count"]]

    if not completed_ids:
        return None

    last = (
        UserVisit.objects.filter(
            opportunity_access=opportunity_access,
            work_area__work_area_group_id__in=completed_ids,
            visit_date__date__range=(period_start, period_end),
        )
        .values("work_area__work_area_group_id")
        .annotate(last_visit=Max("visit_date"))
        .order_by("-last_visit")
        .first()
    )

    if not last:
        return None

    return WorkAreaGroup.objects.get(id=last["work_area__work_area_group_id"])
