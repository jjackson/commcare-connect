"""
Follow-up visit analysis for MBW Monitoring Dashboard.

Calculates visit status (Completed On-Time, Completed Late, Due On-Time,
Due Late, Missed) and aggregates per-FLW and per-mother metrics.
"""

import logging
from collections import defaultdict
from datetime import date

logger = logging.getLogger(__name__)

# Visit status constants
STATUS_COMPLETED_ON_TIME = "Completed - On Time"
STATUS_COMPLETED_LATE = "Completed - Late"
STATUS_DUE_ON_TIME = "Due - On Time"
STATUS_DUE_LATE = "Due - Late"
STATUS_MISSED = "Missed"

# Status color thresholds
THRESHOLD_GREEN = 80
THRESHOLD_YELLOW = 60

# Completion flag mapping: visit_type → property name
COMPLETION_FLAGS = {
    "ANC Visit": "antenatal_visit_completion",
    "Postnatal Visit": "postnatal_visit_completion",
    "Postnatal Delivery Visit": "postnatal_visit_completion",
    "1 Week Visit": "one_two_week_visit_completion",
    "1 Month Visit": "one_month_visit_completion",
    "3 Month Visit": "three_month_visit_completion",
    "6 Month Visit": "six_month_visit_completion",
}

# Visit type display names (normalize)
VISIT_TYPE_DISPLAY = {
    "ANC Visit": "ANC",
    "Postnatal Visit": "Postnatal",
    "Postnatal Delivery Visit": "Postnatal",
    "1 Week Visit": "Week 1",
    "1 Month Visit": "Month 1",
    "3 Month Visit": "Month 3",
    "6 Month Visit": "Month 6",
}

# Visit type keys for per-type breakdown
VISIT_TYPE_KEYS = ["anc", "postnatal", "week1", "month1", "month3", "month6"]
VISIT_TYPE_TO_KEY = {
    "ANC Visit": "anc",
    "Postnatal Visit": "postnatal",
    "Postnatal Delivery Visit": "postnatal",
    "1 Week Visit": "week1",
    "1 Month Visit": "month1",
    "3 Month Visit": "month3",
    "6 Month Visit": "month6",
}


def _parse_date(date_str: str | None) -> date | None:
    """Parse a date string (YYYY-MM-DD) into a date object."""
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str[:10])
    except (ValueError, TypeError):
        return None


def _parse_bool(value) -> bool:
    """Parse a boolean-like value from case properties."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("yes", "true", "1", "completed")
    return bool(value)


def is_visit_completed(visit_case: dict) -> bool:
    """
    Check if a visit case is completed based on its type-specific completion flag.

    Args:
        visit_case: Case dict from CommCare HQ

    Returns:
        True if the visit is marked as completed
    """
    props = visit_case.get("properties", {})
    visit_type = props.get("visit_type", "")

    flag_name = COMPLETION_FLAGS.get(visit_type)
    if not flag_name:
        return False

    return _parse_bool(props.get(flag_name))


def calculate_visit_status(visit_case: dict, current_date: date) -> str:
    """
    Determine the status of a visit case.

    Categories:
    - Completed - On Time: Completed within the on-time window
    - Completed - Late: Completed after on-time window but before expiry
    - Due - On Time: Not completed, currently within on-time window
    - Due - Late: Not completed, past on-time window but before expiry
    - Missed: Not completed and past expiry date

    Args:
        visit_case: Case dict from CommCare HQ with properties
        current_date: Reference date for status calculation

    Returns:
        Status string (one of the 5 categories)
    """
    props = visit_case.get("properties", {})
    visit_type = props.get("visit_type", "")
    scheduled_date = _parse_date(props.get("visit_date_scheduled"))
    expiry_date = _parse_date(props.get("visit_expiry_date"))
    completed = is_visit_completed(visit_case)

    # If we can't parse dates, default to Unknown handling
    if not scheduled_date:
        if completed:
            return STATUS_COMPLETED_LATE
        return STATUS_DUE_ON_TIME

    # On-time window: within 7 days of scheduled date
    from datetime import timedelta

    on_time_end = scheduled_date + timedelta(days=7)

    if completed:
        # Try to get completion date from case modified date
        modified_date = _parse_date(visit_case.get("date_modified") or visit_case.get("server_date_modified"))

        if modified_date and modified_date <= on_time_end:
            return STATUS_COMPLETED_ON_TIME
        return STATUS_COMPLETED_LATE

    # Not completed
    if expiry_date and current_date > expiry_date:
        return STATUS_MISSED

    if current_date <= on_time_end:
        return STATUS_DUE_ON_TIME

    return STATUS_DUE_LATE


def aggregate_flw_followup(
    visit_cases_by_flw: dict[str, list[dict]],
    current_date: date,
    flw_names: dict[str, str] | None = None,
) -> list[dict]:
    """
    Aggregate follow-up metrics per FLW.

    Args:
        visit_cases_by_flw: Dict mapping username to list of visit case dicts
        current_date: Reference date for status calculations
        flw_names: Optional dict mapping username to display name

    Returns:
        List of per-FLW summary dicts, sorted by completion rate ascending
    """
    flw_names = flw_names or {}
    summaries = []

    for username, cases in visit_cases_by_flw.items():
        summary = _build_flw_summary(username, cases, current_date, flw_names)
        summaries.append(summary)

    # Sort by completion rate ascending (worst performers first)
    summaries.sort(key=lambda s: s["completion_rate"])

    return summaries


def _build_flw_summary(
    username: str,
    cases: list[dict],
    current_date: date,
    flw_names: dict[str, str],
) -> dict:
    """Build a follow-up summary for one FLW."""
    display_name = flw_names.get(username, username)

    # Initialize counters
    completed_on_time = 0
    completed_late = 0
    due_on_time = 0
    due_late = 0
    missed = 0

    # Per-visit-type counters
    type_counts = {}
    for key in VISIT_TYPE_KEYS:
        type_counts[key] = {
            "completed_on_time": 0,
            "completed_late": 0,
            "due_on_time": 0,
            "due_late": 0,
            "missed": 0,
        }

    for case in cases:
        status = calculate_visit_status(case, current_date)
        visit_type = case.get("properties", {}).get("visit_type", "")
        type_key = VISIT_TYPE_TO_KEY.get(visit_type)

        if status == STATUS_COMPLETED_ON_TIME:
            completed_on_time += 1
            if type_key:
                type_counts[type_key]["completed_on_time"] += 1
        elif status == STATUS_COMPLETED_LATE:
            completed_late += 1
            if type_key:
                type_counts[type_key]["completed_late"] += 1
        elif status == STATUS_DUE_ON_TIME:
            due_on_time += 1
            if type_key:
                type_counts[type_key]["due_on_time"] += 1
        elif status == STATUS_DUE_LATE:
            due_late += 1
            if type_key:
                type_counts[type_key]["due_late"] += 1
        elif status == STATUS_MISSED:
            missed += 1
            if type_key:
                type_counts[type_key]["missed"] += 1

    completed_total = completed_on_time + completed_late
    due_total = completed_total + due_on_time + due_late + missed
    completion_rate = round((completed_total / due_total) * 100) if due_total > 0 else 0

    # Status color
    if completion_rate >= THRESHOLD_GREEN:
        status_color = "green"
    elif completion_rate >= THRESHOLD_YELLOW:
        status_color = "yellow"
    else:
        status_color = "red"

    summary = {
        "username": username,
        "display_name": display_name,
        "completed_on_time": completed_on_time,
        "completed_late": completed_late,
        "due_on_time": due_on_time,
        "due_late": due_late,
        "missed": missed,
        "completed_total": completed_total,
        "due_total": due_total,
        "completion_rate": completion_rate,
        "status_color": status_color,
    }

    # Add per-visit-type breakdown
    for key in VISIT_TYPE_KEYS:
        for status_key, count in type_counts[key].items():
            summary[f"{key}_{status_key}"] = count

    return summary


def aggregate_visit_status_distribution(
    visit_cases_by_flw: dict[str, list[dict]],
    current_date: date,
) -> dict:
    """
    Aggregate visit status distribution across all FLWs for the overview chart.

    Returns:
        Dict with status counts and percentages for 100% stacked bar chart
    """
    totals = {
        "completed_on_time": 0,
        "completed_late": 0,
        "due_on_time": 0,
        "due_late": 0,
        "missed": 0,
    }

    for cases in visit_cases_by_flw.values():
        for case in cases:
            status = calculate_visit_status(case, current_date)
            if status == STATUS_COMPLETED_ON_TIME:
                totals["completed_on_time"] += 1
            elif status == STATUS_COMPLETED_LATE:
                totals["completed_late"] += 1
            elif status == STATUS_DUE_ON_TIME:
                totals["due_on_time"] += 1
            elif status == STATUS_DUE_LATE:
                totals["due_late"] += 1
            elif status == STATUS_MISSED:
                totals["missed"] += 1

    total = sum(totals.values())
    percentages = {}
    for key, count in totals.items():
        percentages[f"{key}_pct"] = round((count / total) * 100, 1) if total > 0 else 0

    return {**totals, **percentages, "total": total}


def aggregate_mother_metrics(
    visit_cases: list[dict],
    current_date: date,
    mother_cases_map: dict[str, dict] | None = None,
) -> list[dict]:
    """
    Aggregate follow-up metrics per mother case for drill-down view.

    Args:
        visit_cases: List of visit case dicts for one FLW
        current_date: Reference date
        mother_cases_map: Optional dict mapping mother_case_id to mother case dict

    Returns:
        List of per-mother summary dicts
    """
    mother_cases_map = mother_cases_map or {}

    by_mother = defaultdict(list)
    for case in visit_cases:
        mother_id = case.get("properties", {}).get("mother_case_id", "unknown")
        by_mother[mother_id].append(case)

    mothers = []
    for mother_id, cases in by_mother.items():
        completed = sum(1 for c in cases if is_visit_completed(c))
        total = len(cases)
        rate = round((completed / total) * 100) if total > 0 else 0

        all_visits = _build_visit_details(cases, current_date)
        has_due_visits = any(
            v["status"] in (STATUS_DUE_ON_TIME, STATUS_DUE_LATE)
            for v in all_visits
        )

        # Mother metadata from mother case
        mother_case = mother_cases_map.get(mother_id, {})
        mother_props = mother_case.get("properties", {})

        mothers.append({
            "mother_case_id": mother_id,
            "mother_name": mother_case.get("case_name") or mother_props.get("mother_name", ""),
            "registration_date": (mother_case.get("date_opened") or "")[:10] or "",
            "age": mother_props.get("age") or mother_props.get("mother_age", ""),
            "phone_number": mother_props.get("phone_number") or mother_props.get("contact_phone", ""),
            "anc_completion_date": (
                mother_props.get("antenatal_visit_completion_date")
                or mother_props.get("anc_completion_date")
                or ""
            ),
            "pnc_completion_date": (
                mother_props.get("postnatal_visit_completion_date")
                or mother_props.get("pnc_completion_date")
                or ""
            ),
            "completed": completed,
            "total": total,
            "follow_up_rate": rate,
            "has_due_visits": has_due_visits,
            "visits": all_visits,
        })

    # Sort by follow-up rate ascending (worst first)
    mothers.sort(key=lambda m: m["follow_up_rate"])
    return mothers


def _build_visit_details(cases: list[dict], current_date: date) -> list[dict]:
    """Build detail rows for visits within a mother group (includes all statuses)."""
    details = []
    for case in cases:
        props = case.get("properties", {})
        status = calculate_visit_status(case, current_date)

        details.append({
            "case_id": case.get("case_id"),
            "visit_type": VISIT_TYPE_DISPLAY.get(props.get("visit_type", ""), props.get("visit_type", "")),
            "visit_date_scheduled": props.get("visit_date_scheduled"),
            "visit_expiry_date": props.get("visit_expiry_date"),
            "status": status,
        })

    # Sort by scheduled date, then visit type
    details.sort(key=lambda d: (d.get("visit_date_scheduled") or "", d.get("visit_type", "")))
    return details
