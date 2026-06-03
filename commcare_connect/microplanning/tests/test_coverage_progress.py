import datetime

import pytest

from commcare_connect.microplanning.coverage_progress import CoverageDateFilter

pytestmark = pytest.mark.django_db


def test_date_filter_overall_has_no_window():
    f = CoverageDateFilter.overall()
    assert f.is_overall is True
    assert f.window is None


def test_date_filter_custom_range_window():
    f = CoverageDateFilter(start=datetime.date(2026, 1, 1), end=datetime.date(2026, 1, 31))
    assert f.is_overall is False
    assert f.window == (datetime.date(2026, 1, 1), datetime.date(2026, 1, 31))
