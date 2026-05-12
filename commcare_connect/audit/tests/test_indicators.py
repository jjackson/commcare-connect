from __future__ import annotations

import datetime
import random
from datetime import timezone

import pytest

from commcare_connect.audit.indicators import (
    _FEMALE_VALUE,
    _VACCINE_YES_VALUE,
    AgeHeaping,
    CampingRatio,
    GenderRatioDeviation,
    InaccessibleWARateEarlyWarning,
    MUACPhotoCompliance,
    WACoverageToVisitRatio,
)
from commcare_connect.microplanning.models import WorkAreaStatus
from commcare_connect.microplanning.tests.factories import WorkAreaFactory, WorkAreaGroupFactory
from commcare_connect.opportunity.tests.factories import OpportunityAccessFactory, UserVisitFactory

PERIOD_START = datetime.date(2026, 4, 13)  # Monday
PERIOD_END = datetime.date(2026, 4, 19)  # Sunday
IN_PERIOD = datetime.datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc)
OUT_OF_PERIOD = datetime.datetime(2026, 4, 5, 12, 0, tzinfo=timezone.utc)
AFTER_PERIOD = datetime.datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc)


def make_visit(access, work_area=None, visit_date=IN_PERIOD, **kwargs):
    return UserVisitFactory(
        opportunity=access.opportunity,
        user=access.user,
        opportunity_access=access,
        work_area=work_area,
        visit_date=visit_date,
        completed_work=None,
        **kwargs,
    )


def make_wag(access, **kwargs):
    """WorkAreaGroup has no opportunity_access FK — WAs are assigned to accesses directly."""
    return WorkAreaGroupFactory(opportunity=access.opportunity, **kwargs)


def make_wa(wag, access, **kwargs):
    return WorkAreaFactory(opportunity=wag.opportunity, work_area_group=wag, opportunity_access=access, **kwargs)


# ── visit builder helpers ──────────────────────────────────────────────────────


def _visit_with_gender(access, gender, **kwargs):
    return make_visit(
        access,
        form_json={"form": {"additional_case_info": {"childs_gender": gender}}},
        **kwargs,
    )


def _visit_with_age(access, age, dob=None, **kwargs):
    additional = {"childs_age_in_month": age}
    if dob is not None:
        additional["childs_dob"] = dob
    return make_visit(access, form_json={"form": {"additional_case_info": additional}}, **kwargs)


def _visit_with_muac_photo(access, has_photo=True, age_months=12, **kwargs):
    muac_group = {"muac_consent_group": {"muac_consent": "yes"}}
    if has_photo:
        muac_group["muac_photo_link"] = "https://example.com/photo.jpg"
    return make_visit(
        access,
        form_json={"form": {"additional_case_info": {"childs_age_in_month": age_months}, "muac_group": muac_group}},
        **kwargs,
    )


def _visit_with_vaccine(access, given=True, **kwargs):
    return make_visit(
        access,
        form_json={"form": {"pictures": {"received_any_vaccine": _VACCINE_YES_VALUE if given else "no"}}},
        **kwargs,
    )


def _visit_with_vaccine_card(access, has_photo=True, **kwargs):
    form = {"pictures": {"received_any_vaccine": _VACCINE_YES_VALUE}}
    if has_photo:
        form["immunization_photo_group"] = {"photo_link_vaccine": "https://example.com/card.jpg"}
    return make_visit(access, form_json={"form": form}, **kwargs)


def _visit_with_muac(access, muac_cm, **kwargs):
    return make_visit(
        access,
        form_json={"form": {"muac_group": {"muac_display_group_1": {"soliciter_muac_cm": muac_cm}}}},
        **kwargs,
    )


def _realistic_muac_measurements() -> list[float]:
    """Bell-shaped MUAC distribution centred around 13.5 cm — passes all 6 features."""
    random.seed(42)
    return [max(9.5, min(21.4, round(random.gauss(13.5, 1.5), 1))) for _ in range(100)]


@pytest.mark.django_db
class TestCampingRatio:
    calc = CampingRatio()

    def test_no_visits_returns_insufficient_data(self):
        access = OpportunityAccessFactory()
        _, sample = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert sample == 0

    @pytest.mark.parametrize(
        "n_visits, n_buildings, expected_camping_count",
        [
            (1, 10, 0),  # 1/10 = 0.1, below threshold
            (13, 1, 1),  # 13/1 = 13 > 12, flagged
            (12, 1, 0),  # 12/1 = 12, not > 12, boundary is exclusive
        ],
    )
    def test_camping_threshold(self, n_visits, n_buildings, expected_camping_count):
        access = OpportunityAccessFactory()
        wa = WorkAreaFactory(opportunity=access.opportunity, building_count=n_buildings)
        for _ in range(n_visits):
            make_visit(access, work_area=wa)
        value, sample = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert sample == 1
        assert value == expected_camping_count

    def test_wa_with_zero_building_count_excluded(self):
        access = OpportunityAccessFactory()
        wa = WorkAreaFactory(opportunity=access.opportunity, building_count=0)
        make_visit(access, work_area=wa)
        _, sample = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert sample == 0

    def test_visits_outside_period_not_counted(self):
        access = OpportunityAccessFactory()
        wa = WorkAreaFactory(opportunity=access.opportunity, building_count=1)
        for _ in range(13):
            make_visit(access, work_area=wa, visit_date=OUT_OF_PERIOD)
        _, sample = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert sample == 0

    def test_only_camping_wa_flagged(self):
        access = OpportunityAccessFactory()
        wa_camping = WorkAreaFactory(opportunity=access.opportunity, building_count=1)
        wa_ok = WorkAreaFactory(opportunity=access.opportunity, building_count=100)
        for _ in range(13):
            make_visit(access, work_area=wa_camping)
        make_visit(access, work_area=wa_ok)
        value, sample = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert sample == 2
        assert value == 1

    def test_run_marks_out_of_range_when_camping(self):
        access = OpportunityAccessFactory()
        wa = WorkAreaFactory(opportunity=access.opportunity, building_count=1)
        for _ in range(13):
            make_visit(access, work_area=wa)
        result = self.calc.run(access, PERIOD_START, PERIOD_END)
        assert result.has_sufficient_data is True
        assert result.in_range is False


@pytest.mark.django_db
class TestGenderRatioDeviation:
    calc = GenderRatioDeviation()

    def test_no_visits_returns_insufficient_data(self):
        access = OpportunityAccessFactory()
        _, sample = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert sample == 0

    @pytest.mark.parametrize(
        "female, male, expected_ratio, in_range",
        [
            (5, 5, 0.5, True),  # 50/50 — within 0.4–0.6
            (10, 0, 1.0, False),  # all female — above 0.6
        ],
    )
    def test_ratio_threshold(self, female, male, expected_ratio, in_range):
        access = OpportunityAccessFactory()
        for _ in range(female):
            _visit_with_gender(access, _FEMALE_VALUE)
        for _ in range(male):
            _visit_with_gender(access, "male_child")
        value, sample = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert sample == female + male
        assert value == pytest.approx(expected_ratio)
        assert self.calc._in_range(value) is in_range

    def test_visits_after_period_end_excluded(self):
        access = OpportunityAccessFactory()
        _visit_with_gender(access, _FEMALE_VALUE, visit_date=AFTER_PERIOD)
        _, sample = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert sample == 0

    def test_visits_before_period_included_in_rolling_window(self):
        """Rolling window goes back past period_start — pre-period visits count."""
        access = OpportunityAccessFactory()
        _visit_with_gender(access, _FEMALE_VALUE, visit_date=OUT_OF_PERIOD)
        _, sample = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert sample == 1

    def test_denominator_is_all_visits_not_just_with_gender(self):
        access = OpportunityAccessFactory()
        make_visit(access)  # no gender field
        _visit_with_gender(access, _FEMALE_VALUE)
        value, sample = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert sample == 2
        assert value == pytest.approx(0.5)


@pytest.mark.django_db
class TestMUACPhotoCompliance:
    calc = MUACPhotoCompliance()

    def test_no_eligible_visits_returns_insufficient_data(self):
        access = OpportunityAccessFactory()
        _, sample = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert sample == 0

    def test_child_under_6_months_not_in_denominator(self):
        access = OpportunityAccessFactory()
        _visit_with_muac_photo(access, age_months=3)  # age <= 6, excluded
        _, sample = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert sample == 0

    def test_no_consent_not_in_denominator(self):
        access = OpportunityAccessFactory()
        make_visit(access, form_json={"form": {"additional_case_info": {"childs_age_in_month": 12}}})
        _, sample = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert sample == 0

    @pytest.mark.parametrize(
        "with_photo, without_photo, expected_value, in_range",
        [
            (5, 0, 1.0, True),  # 100% compliance
            (1, 4, 0.2, False),  # 20% compliance, below 72% threshold
        ],
    )
    def test_compliance_threshold(self, with_photo, without_photo, expected_value, in_range):
        access = OpportunityAccessFactory()
        for _ in range(with_photo):
            _visit_with_muac_photo(access, has_photo=True)
        for _ in range(without_photo):
            _visit_with_muac_photo(access, has_photo=False)
        value, sample = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert sample == with_photo + without_photo
        assert value == pytest.approx(expected_value)
        assert self.calc._in_range(value) is in_range

    def test_empty_photo_link_not_counted(self):
        access = OpportunityAccessFactory()
        make_visit(
            access,
            form_json={
                "form": {
                    "additional_case_info": {"childs_age_in_month": 12},
                    "muac_group": {"muac_consent_group": {"muac_consent": "yes"}, "muac_photo_link": ""},
                }
            },
        )
        value, _ = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert value == pytest.approx(0.0)


@pytest.mark.django_db
class TestAgeHeaping:
    calc = AgeHeaping()

    def test_no_visits_returns_insufficient_data(self):
        access = OpportunityAccessFactory()
        _, sample = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert sample == 0

    @pytest.mark.parametrize(
        "ages, expected_rate, in_range",
        [
            ([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0.0, True),  # no round years
            ([12, 24, 36, 48, 1, 2, 3, 4, 5, 6], 0.4, False),  # 4/10 heaped, above 19%
        ],
    )
    def test_heaping_rate(self, ages, expected_rate, in_range):
        access = OpportunityAccessFactory()
        for age in ages:
            _visit_with_age(access, age)
        value, sample = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert sample == len(ages)
        assert value == pytest.approx(expected_rate)
        assert self.calc._in_range(value) is in_range

    def test_visits_with_dob_excluded(self):
        access = OpportunityAccessFactory()
        _visit_with_age(access, 12, dob="2025-04-15")  # has DOB → excluded
        _visit_with_age(access, 13)  # no DOB → included
        _, sample = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert sample == 1

    def test_visits_after_period_end_excluded(self):
        access = OpportunityAccessFactory()
        _visit_with_age(access, 12, visit_date=AFTER_PERIOD)
        _, sample = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert sample == 0

    def test_age_13_not_heaped(self):
        access = OpportunityAccessFactory()
        for _ in range(5):
            _visit_with_age(access, 13)
        value, _ = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert value == pytest.approx(0.0)


@pytest.mark.django_db
class TestWACoverageToVisitRatio:
    calc = WACoverageToVisitRatio()

    def test_no_was_returns_insufficient_data(self):
        access = OpportunityAccessFactory()
        _, sample = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert sample == 0

    def test_balanced_coverage_and_visits_in_range(self):
        access = OpportunityAccessFactory()
        wag = make_wag(access)
        make_wa(wag, access, status=WorkAreaStatus.VISITED, expected_visit_count=10)
        make_wa(wag, access, status=WorkAreaStatus.NOT_VISITED, expected_visit_count=10)
        for _ in range(10):
            make_visit(access)
        value, sample = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert sample == 2
        assert value == pytest.approx(1.0)
        assert self.calc._in_range(value)

    def test_high_coverage_low_visits_out_of_range(self):
        access = OpportunityAccessFactory()
        wag = make_wag(access)
        make_wa(wag, access, status=WorkAreaStatus.VISITED, expected_visit_count=100)
        make_wa(wag, access, status=WorkAreaStatus.NOT_VISITED, expected_visit_count=100)
        make_visit(access)
        value, _ = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert value > 1.4

    def test_low_coverage_high_visits_out_of_range(self):
        access = OpportunityAccessFactory()
        wag = make_wag(access)
        make_wa(wag, access, status=WorkAreaStatus.NOT_VISITED, expected_visit_count=1)
        for _ in range(10):
            make_visit(access)
        value, _ = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert value < 0.6

    def test_excluded_and_inaccessible_was_not_counted_in_eligible(self):
        """EXCLUDED/INACCESSIBLE WAs must not count in eligible denominator or expected visits."""
        access = OpportunityAccessFactory()
        wag = make_wag(access)
        make_wa(wag, access, status=WorkAreaStatus.VISITED, expected_visit_count=10)
        make_wa(wag, access, status=WorkAreaStatus.EXCLUDED, expected_visit_count=10)
        make_wa(wag, access, status=WorkAreaStatus.INACCESSIBLE, expected_visit_count=10)
        for _ in range(10):
            make_visit(access)
        value, sample = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert sample == 1  # only the VISITED WA is eligible
        assert value == pytest.approx(1.0)

    def test_no_actual_visits_returns_insufficient_data(self):
        access = OpportunityAccessFactory()
        wag = make_wag(access)
        make_wa(wag, access, status=WorkAreaStatus.NOT_VISITED, expected_visit_count=10)
        _, sample = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert sample == 0

    def test_no_expected_visits_returns_insufficient_data(self):
        access = OpportunityAccessFactory()
        wag = make_wag(access)
        make_wa(wag, access, status=WorkAreaStatus.NOT_VISITED, expected_visit_count=0)
        make_visit(access)
        _, sample = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert sample == 0


@pytest.mark.django_db
class TestInaccessibleWARateEarlyWarning:
    calc = InaccessibleWARateEarlyWarning()

    def test_no_wag_returns_insufficient_data(self):
        access = OpportunityAccessFactory()
        _, sample = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert sample == 0

    def test_fewer_than_5_terminal_was_returns_insufficient_data(self):
        access = OpportunityAccessFactory()
        wag = make_wag(access)
        make_wa(wag, access, status=WorkAreaStatus.INACCESSIBLE)
        make_wa(wag, access, status=WorkAreaStatus.INACCESSIBLE)
        make_wa(wag, access, status=WorkAreaStatus.NOT_VISITED)  # non-terminal keeps WAG active
        _, sample = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert sample == 2
        assert self.calc.run(access, PERIOD_START, PERIOD_END).has_sufficient_data is False

    @pytest.mark.parametrize(
        "inaccessible, visited, not_visited, expected_value, in_range",
        [
            (1, 5, 1, 1 / 7, True),  # ~14%, below 25% threshold
            (4, 1, 1, 4 / 6, False),  # ~67%, above 25% threshold
        ],
    )
    def test_inaccessible_rate_threshold(self, inaccessible, visited, not_visited, expected_value, in_range):
        access = OpportunityAccessFactory()
        wag = make_wag(access)
        for _ in range(inaccessible):
            make_wa(wag, access, status=WorkAreaStatus.INACCESSIBLE)
        for _ in range(visited):
            make_wa(wag, access, status=WorkAreaStatus.VISITED)
        for _ in range(not_visited):
            make_wa(wag, access, status=WorkAreaStatus.NOT_VISITED)
        value, sample = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert sample == inaccessible + visited  # terminal count
        assert value == pytest.approx(expected_value)
        assert self.calc._in_range(value) is in_range

    def test_fully_closed_wag_not_treated_as_active(self):
        access = OpportunityAccessFactory()
        wag = make_wag(access)
        for _ in range(6):
            make_wa(wag, access, status=WorkAreaStatus.VISITED)
        _, sample = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert sample == 0

    def test_most_advanced_wag_selected_as_active(self):
        access = OpportunityAccessFactory()
        wag_early = make_wag(access)
        make_wa(wag_early, access, status=WorkAreaStatus.NOT_VISITED)

        wag_active = make_wag(access)
        for _ in range(5):
            make_wa(wag_active, access, status=WorkAreaStatus.VISITED)
        make_wa(wag_active, access, status=WorkAreaStatus.INACCESSIBLE)
        make_wa(wag_active, access, status=WorkAreaStatus.NOT_VISITED)

        value, sample = self.calc.compute(access, PERIOD_START, PERIOD_END)
        assert sample == 6
        assert value == pytest.approx(1 / 7)
