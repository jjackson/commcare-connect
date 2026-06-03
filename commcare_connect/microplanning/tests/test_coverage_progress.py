import datetime

import pytest
from django.utils import timezone

from commcare_connect.microplanning.coverage_progress import (
    CoverageDateFilter,
    annotate_status_timestamps,
    non_excluded_workareas,
    status_aggregates,
    status_event_model,
    target_aggregates,
)
from commcare_connect.microplanning.models import WorkAreaStatus
from commcare_connect.microplanning.tests.factories import WorkAreaFactory, WorkAreaGroupFactory

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
