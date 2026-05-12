from __future__ import annotations

from django.db.models import Count, Max, Q, Sum

from commcare_connect.audit.calculations import AuditCalculation, register_calculation
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


@register_calculation
class CampingRatio(AuditCalculation):
    """Detect inflated visit reporting within a Work Area's building count.
    Flags if any WA has >12 visits per building in the report week.
    Returns count of camping WAs; upper_bound=0 means any camping WA flags the FLW.
    """

    name = "camping_ratio"
    label = "Camping (Visit:Building Ratio)"
    min_sample_size = 1
    upper_bound = 0

    def compute(self, opportunity_access, period_start, period_end):
        wa_visit_counts = list(
            UserVisit.objects.filter(
                opportunity_access=opportunity_access,
                visit_date__date__range=(period_start, period_end),
                work_area__isnull=False,
                work_area__building_count__gt=0,
            )
            .values("work_area_id", "work_area__building_count")
            .annotate(visit_count=Count("id"))
        )

        total_evaluated = len(wa_visit_counts)
        camping_count = sum(1 for row in wa_visit_counts if row["visit_count"] > 12 * row["work_area__building_count"])
        return camping_count, total_evaluated


@register_calculation
class GenderRatioDeviation(AuditCalculation):
    """Detect gender imbalance suggesting selective visit recording.
    Ratio = female visits / last 97 completed visits.
    Flags if female ratio < 0.4 or > 0.6 (10% max deviation from 50/50 at 95% confidence).
    """

    name = "gender_ratio_deviation"
    label = "Gender Ratio Deviation"
    min_sample_size = 97
    lower_bound = 0.4
    upper_bound = 0.6

    def compute(self, opportunity_access, period_start, period_end):
        recent = _last_n_visits(opportunity_access, self.min_sample_size, period_end)
        result = UserVisit.objects.filter(id__in=recent).aggregate(
            total=Count("id"),
            female=Count("id", filter=Q(**{f"form_json__form__{_GENDER_FIELD}": _FEMALE_VALUE})),
        )
        total = result["total"]
        if not total:
            return None, 0
        return result["female"] / total, total


@register_calculation
class MUACPhotoCompliance(AuditCalculation):
    """Detect missing MUAC measurement photos for eligible children.
    Denominator: last 70 visits where child is >6 months old and MUAC consent was given.
    Numerator: visits where muac_photo_link is non-empty.
    Flags if compliance < 72% (p=0.80, n=70, one-sided 95% CI lower bound).
    """

    name = "muac_photo_compliance"
    label = "MUAC Photo Compliance"
    min_sample_size = 70
    lower_bound = 0.72

    def compute(self, opportunity_access, period_start, period_end):
        eligible = _last_n_visits(
            opportunity_access,
            self.min_sample_size,
            period_end,
            **{f"form_json__form__{_AGE_FIELD}__gt": 6},
            **{f"form_json__form__{_MUAC_CONSENT_FIELD}": _MUAC_CONSENT_YES},
        )
        result = UserVisit.objects.filter(id__in=eligible).aggregate(
            total=Count("id"),
            with_photo=Count("id", filter=_q_link_present(_MUAC_PHOTO_LINK_FIELD)),
        )
        total = result["total"]
        if not total:
            return None, 0
        return result["with_photo"] / total, total


@register_calculation
class AgeHeaping(AuditCalculation):
    """Detect rounding/shortcut age entry at exact whole-year values.
    Flags when visits with childs_age_in_month in (12, 24, 36, 48) exceed 19%
    of the last 97 visits without a recorded DOB.
    Threshold: p=0.134, n=97, one-sided 95% CI upper bound.
    """

    name = "age_heaping"
    label = "Age Heaping"
    min_sample_size = 97
    upper_bound = 0.19

    def compute(self, opportunity_access, period_start, period_end):
        recent = _last_n_visits(
            opportunity_access,
            self.min_sample_size,
            period_end,
            **{f"form_json__form__{_AGE_FIELD}__isnull": False},
            **{f"form_json__form__{_DOB_FIELD}__isnull": True},
        )
        result = UserVisit.objects.filter(id__in=recent).aggregate(
            total=Count("id"),
            heaped=Count("id", filter=Q(**{f"form_json__form__{_AGE_FIELD}__in": [12, 24, 36, 48]})),
        )
        total = result["total"]
        if not total:
            return None, 0
        return result["heaped"] / total, total


@register_calculation
class WACoverageToVisitRatio(AuditCalculation):
    """Detect imbalance between work area coverage progress and visit progress.

    Ratio = (VISITED WAs / eligible WAs) / (actual visits / expected visits).
    Eligible WAs exclude those marked EXCLUDED or INACCESSIBLE.
    Uses cumulative totals from campaign start, not just the report week.
    """

    name = "wa_coverage_to_visit_ratio"
    label = "WA Coverage to Visit Ratio"
    min_sample_size = 1
    lower_bound = 0.6
    upper_bound = 1.4

    def compute(self, opportunity_access, period_start, period_end):
        _eligible = ~Q(status__in=[WorkAreaStatus.EXCLUDED, WorkAreaStatus.INACCESSIBLE])
        wa_stats = WorkArea.objects.filter(opportunity_access=opportunity_access).aggregate(
            total_eligible=Count("id", filter=_eligible),
            visited_count=Count("id", filter=Q(status=WorkAreaStatus.VISITED)),
            expected_visits=Sum("expected_visit_count", filter=_eligible),
        )

        total_eligible = wa_stats["total_eligible"] or 0
        expected_visits = wa_stats["expected_visits"] or 0
        actual_visits = UserVisit.objects.filter(
            opportunity_access=opportunity_access,
            visit_date__date__lte=period_end,
        ).count()

        if not (total_eligible and expected_visits and actual_visits):
            return None, 0

        coverage_ratio = wa_stats["visited_count"] / total_eligible
        visit_ratio = actual_visits / expected_visits
        return coverage_ratio / visit_ratio, total_eligible


@register_calculation
class InaccessibleWARateEarlyWarning(AuditCalculation):
    """Detect emerging overuse of Inaccessible state mid-WAG.
    Evaluated against the FLW's current active WAG.
    Requires ≥5 WAs with terminal status before evaluating.
    """

    name = "inaccessible_wa_rate_early_warning"
    label = "Inaccessible WA Rate – Early Warning"
    min_sample_size = 5
    upper_bound = 0.25

    def compute(self, opportunity_access, period_start, period_end):
        active_wag = _find_active_wag(opportunity_access)
        if active_wag is None:
            return None, 0

        was = WorkArea.objects.filter(work_area_group=active_wag, opportunity_access=opportunity_access)
        total = was.count()
        if total == 0:
            return None, 0

        terminal_count = was.filter(status__in=_TERMINAL_STATUSES).count()
        inaccessible_count = was.filter(status=WorkAreaStatus.INACCESSIBLE).count()

        return inaccessible_count / total, terminal_count


@register_calculation
class InaccessibleWARateLastCompletedWAG(AuditCalculation):
    """Detect systematic overuse of Inaccessible state in the most recently completed WAG.
    Evaluated against the last completed WAG (all WAs terminal), identified by
    the latest visit date across its WAs.
    """

    name = "inaccessible_wa_rate_last_completed_wag"
    label = "Inaccessible WA Rate – Last Completed WAG"
    min_sample_size = 5
    upper_bound = 0.15

    def compute(self, opportunity_access, period_start, period_end):
        last_wag = _find_last_completed_wag(opportunity_access, period_start, period_end)
        if last_wag is None:
            return None, 0

        was = WorkArea.objects.filter(
            work_area_group=last_wag,
            opportunity_access=opportunity_access,
        ).exclude(status=WorkAreaStatus.EXCLUDED)
        total = was.count()
        if total == 0:
            return None, 0

        inaccessible_count = was.filter(status=WorkAreaStatus.INACCESSIBLE).count()
        return inaccessible_count / total, total
