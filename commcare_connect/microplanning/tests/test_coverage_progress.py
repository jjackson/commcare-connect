import datetime

import pytest
from django.utils import timezone

from commcare_connect.microplanning.coverage_progress import (
    CoverageDateFilter,
    annotate_status_timestamps,
    build_ward_rows,
    non_excluded_workareas,
    status_aggregates,
    status_event_model,
    target_aggregates,
    visits_approved_aggregates,
)
from commcare_connect.microplanning.models import WorkAreaStatus
from commcare_connect.microplanning.tests.factories import WorkAreaFactory, WorkAreaGroupFactory
from commcare_connect.opportunity.models import VisitValidationStatus
from commcare_connect.opportunity.tests.factories import UserVisitFactory

pytestmark = pytest.mark.django_db


def test_date_filter_overall_has_no_window():
    f = CoverageDateFilter.overall()
    assert f.is_overall is True
    assert f.window is None


def test_date_filter_custom_range_window():
    f = CoverageDateFilter(start=datetime.date(2026, 1, 1), end=datetime.date(2026, 1, 31))
    assert f.is_overall is False
    assert f.window == (datetime.date(2026, 1, 1), datetime.date(2026, 1, 31))


def _stamp_transition(work_area, status, when):
    Event = status_event_model()
    event = Event.objects.create(
        pgh_obj_id=work_area.pk,
        pgh_label="update",
        status=status,
        expected_visit_count=work_area.expected_visit_count,
        work_area_group_id=work_area.work_area_group_id,
        opportunity_access_id=work_area.opportunity_access_id,
        excluded_reason=work_area.excluded_reason,
    )
    Event.objects.filter(pk=event.pk).update(pgh_created_at=when)
    return event


def test_annotate_status_timestamps_uses_earliest_transition(opportunity):
    wa = WorkAreaFactory(opportunity=opportunity, status=WorkAreaStatus.VISITED)
    early = timezone.make_aware(datetime.datetime(2026, 1, 10, 9, 0))
    late = timezone.make_aware(datetime.datetime(2026, 2, 20, 9, 0))
    _stamp_transition(wa, WorkAreaStatus.VISITED, late)
    _stamp_transition(wa, WorkAreaStatus.VISITED, early)
    _stamp_transition(wa, WorkAreaStatus.EXPECTED_VISIT_REACHED, late)

    annotated = annotate_status_timestamps(non_excluded_workareas(opportunity)).get(pk=wa.pk)
    assert annotated.visited_at == early
    assert annotated.evc_reached_at == late


def test_status_aggregates_overall_strict_and_exclusive(opportunity):
    WorkAreaFactory(opportunity=opportunity, ward="w1", status=WorkAreaStatus.VISITED, building_count=10)
    WorkAreaFactory(opportunity=opportunity, ward="w1", status=WorkAreaStatus.EXPECTED_VISIT_REACHED, building_count=7)
    WorkAreaFactory(opportunity=opportunity, ward="w1", status=WorkAreaStatus.NOT_VISITED, building_count=3)
    WorkAreaFactory(opportunity=opportunity, ward="w1", status=WorkAreaStatus.EXCLUDED, building_count=99)

    result = status_aggregates(opportunity, "ward", window=None)

    assert result["w1"]["WAs_visited"] == 1
    assert result["w1"]["WAs_evc_reached"] == 1
    assert result["w1"]["Buildings_covered_in_WAs_visited"] == 10
    assert result["w1"]["Buildings_covered_in_WAs_evc_reached"] == 7


def test_status_aggregates_window_filters_by_transition_date(opportunity):
    wa = WorkAreaFactory(opportunity=opportunity, ward="w1", status=WorkAreaStatus.VISITED, building_count=10)
    _stamp_transition(wa, WorkAreaStatus.VISITED, timezone.make_aware(datetime.datetime(2026, 3, 15, 9, 0)))
    in_window = (datetime.date(2026, 3, 1), datetime.date(2026, 3, 31))
    out_window = (datetime.date(2026, 4, 1), datetime.date(2026, 4, 30))

    assert status_aggregates(opportunity, "ward", window=in_window)["w1"]["WAs_visited"] == 1
    assert status_aggregates(opportunity, "ward", window=out_window).get("w1", {}).get("WAs_visited", 0) == 0


def test_status_aggregates_window_filters_by_transition_date_for_wag(opportunity):
    group = WorkAreaGroupFactory(opportunity=opportunity)
    wa = WorkAreaFactory(
        opportunity=opportunity, work_area_group=group, status=WorkAreaStatus.VISITED, building_count=10
    )
    _stamp_transition(wa, WorkAreaStatus.VISITED, timezone.make_aware(datetime.datetime(2026, 3, 15, 9, 0)))
    in_window = (datetime.date(2026, 3, 1), datetime.date(2026, 3, 31))
    out_window = (datetime.date(2026, 4, 1), datetime.date(2026, 4, 30))

    in_result = status_aggregates(opportunity, "work_area_group_id", window=in_window)
    out_result = status_aggregates(opportunity, "work_area_group_id", window=out_window)
    assert in_result[group.id]["WAs_visited"] == 1
    assert out_result.get(group.id, {}).get("WAs_visited", 0) == 0


def test_target_aggregates_by_ward_excludes_excluded(opportunity):
    WorkAreaFactory(
        opportunity=opportunity,
        ward="w1",
        status=WorkAreaStatus.VISITED,
        target_population=100,
        building_count=10,
        expected_visit_count=5,
    )
    WorkAreaFactory(
        opportunity=opportunity,
        ward="w1",
        status=WorkAreaStatus.INACCESSIBLE,
        target_population=50,
        building_count=4,
        expected_visit_count=3,
    )
    WorkAreaFactory(
        opportunity=opportunity,
        ward="w1",
        status=WorkAreaStatus.EXCLUDED,
        target_population=999,
        building_count=99,
        expected_visit_count=99,
    )
    WorkAreaFactory(
        opportunity=opportunity,
        ward="w2",
        status=WorkAreaStatus.NOT_VISITED,
        target_population=20,
        building_count=2,
        expected_visit_count=1,
    )

    result = target_aggregates(opportunity, "ward")

    assert result["w1"] == {
        "ward": "w1",
        "target_population": 150,
        "building_count": 14,
        "num_work_areas": 2,
        "expected_visit_total": 8,
    }
    assert result["w2"]["num_work_areas"] == 1
    assert "999" not in str(result["w1"])  # excluded WA not summed


def test_target_aggregates_by_wag_excludes_excluded(opportunity):
    group = WorkAreaGroupFactory(opportunity=opportunity)
    WorkAreaFactory(
        opportunity=opportunity,
        work_area_group=group,
        status=WorkAreaStatus.VISITED,
        target_population=100,
        building_count=10,
        expected_visit_count=5,
    )
    WorkAreaFactory(
        opportunity=opportunity,
        work_area_group=group,
        status=WorkAreaStatus.EXCLUDED,
        target_population=999,
        building_count=99,
        expected_visit_count=99,
    )

    result = target_aggregates(opportunity, "work_area_group_id")

    assert result[group.id] == {
        "work_area_group_id": group.id,
        "target_population": 100,
        "building_count": 10,
        "num_work_areas": 1,
        "expected_visit_total": 5,
    }


def _approved_visit(opportunity, work_area, when):
    return UserVisitFactory(
        opportunity=opportunity,
        work_area=work_area,
        status=VisitValidationStatus.approved,
        visit_date=timezone.make_aware(datetime.datetime.combine(when, datetime.time(9, 0))),
    )


def test_visits_approved_overall_excludes_excluded_and_unapproved(opportunity):
    wa = WorkAreaFactory(opportunity=opportunity, ward="w1", status=WorkAreaStatus.VISITED)
    excluded = WorkAreaFactory(opportunity=opportunity, ward="w1", status=WorkAreaStatus.EXCLUDED)
    _approved_visit(opportunity, wa, datetime.date(2026, 3, 10))
    _approved_visit(opportunity, wa, datetime.date(2026, 3, 12))
    _approved_visit(opportunity, excluded, datetime.date(2026, 3, 12))  # dropped: EXCLUDED WA
    UserVisitFactory(
        opportunity=opportunity,
        work_area=wa,
        status=VisitValidationStatus.pending,
        visit_date=timezone.make_aware(datetime.datetime(2026, 3, 12, 9, 0)),
    )  # dropped: not approved

    result = visits_approved_aggregates(opportunity, "ward", window=None)
    assert result["w1"]["visits_approved"] == 2


def test_visits_approved_window_filters_visit_date(opportunity):
    wa = WorkAreaFactory(opportunity=opportunity, ward="w1", status=WorkAreaStatus.VISITED)
    _approved_visit(opportunity, wa, datetime.date(2026, 3, 10))
    _approved_visit(opportunity, wa, datetime.date(2026, 4, 10))
    window = (datetime.date(2026, 3, 1), datetime.date(2026, 3, 31))
    assert visits_approved_aggregates(opportunity, "ward", window=window)["w1"]["visits_approved"] == 1


def test_build_ward_rows_merges_and_derives():
    target_aggregates = {
        "w1": {
            "ward": "w1",
            "target_population": 200,
            "building_count": 50,
            "num_work_areas": 10,
            "expected_visit_total": 40,
        }
    }
    filtered_status = {
        "w1": {
            "ward": "w1",
            "WAs_visited": 4,
            "WAs_evc_reached": 2,
            "Buildings_covered_in_WAs_visited": 20,
            "Buildings_covered_in_WAs_evc_reached": 8,
        }
    }
    filtered_visits = {"w1": {"ward": "w1", "visits_approved": 20}}
    last_week_status = {
        "w1": {
            "ward": "w1",
            "WAs_visited": 1,
            "WAs_evc_reached": 0,
            "Buildings_covered_in_WAs_visited": 5,
            "Buildings_covered_in_WAs_evc_reached": 0,
        }
    }
    last_week_visits = {"w1": {"ward": "w1", "visits_approved": 5}}

    rows = build_ward_rows(target_aggregates, filtered_status, filtered_visits, last_week_status, last_week_visits)
    row = next(r for r in rows if r["ward"] == "w1")

    assert row["num_work_areas"] == 10
    assert row["visits_approved"] == 20
    assert row["WAs_visited"] == 4
    assert row["pct_visits_approved"] == 50.0  # 20 / 40
    assert row["pct_WAs_visited"] == 40.0  # 4 / 10
    assert row["pct_WAs_evc_reached"] == 20.0  # 2 / 10
    assert row["pct_Buildings_covered_in_WAs_visited"] == 40.0  # 20 / 50
    assert row["pct_WA_visited_to_pct_visits"] == 80.0  # 40 / 50 * 100
    assert row["pct_WA_evc_reached_to_pct_visit"] == 40.0  # 20 / 50 * 100
    assert row["WAs_visited_last_week"] == 1
    assert row["pct_WAs_visited_last_week"] == 10.0  # 1 / 10
    # last-week ratio = pct_WAs_visited_last_week / pct_visits_approved_last_week * 100
    #                 = 10.0 / (5/40*100 = 12.5) * 100 = 80.0
    assert row["pct_WA_visited_to_pct_visits_last_week"] == 80.0


def test_build_ward_rows_zero_denominator_yields_none():
    target_aggregates = {
        "w1": {
            "ward": "w1",
            "target_population": 0,
            "building_count": 0,
            "num_work_areas": 0,
            "expected_visit_total": 0,
        }
    }
    rows = build_ward_rows(target_aggregates, {}, {}, {}, {})
    row = rows[0]
    assert row["visits_approved"] == 0
    assert row["pct_visits_approved"] is None
    assert row["pct_WAs_visited"] is None
    assert row["pct_WA_visited_to_pct_visits"] is None
