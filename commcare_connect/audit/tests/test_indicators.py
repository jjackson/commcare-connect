from __future__ import annotations

import datetime
import random
from datetime import timezone

from commcare_connect.audit.indicators import _VACCINE_YES_VALUE
from commcare_connect.microplanning.tests.factories import WorkAreaFactory, WorkAreaGroupFactory
from commcare_connect.opportunity.tests.factories import UserVisitFactory

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
