import datetime

import pytest
from django.utils import timezone

from commcare_connect.microplanning.coverage_progress import (
    CoverageDateFilter,
    annotate_status_timestamps,
    non_excluded_workareas,
    status_event_model,
)
from commcare_connect.microplanning.models import WorkAreaStatus
from commcare_connect.microplanning.tests.factories import WorkAreaFactory

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
