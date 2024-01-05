import re

import pytest
from tablib import Dataset

from commcare_connect.opportunity.models import Opportunity, OpportunityAccess, UserVisit, VisitValidationStatus
from commcare_connect.opportunity.tests.factories import DeliverUnitFactory, PaymentUnitFactory, UserVisitFactory
from commcare_connect.opportunity.visit_import import (
    ImportException,
    _bulk_update_visit_status,
    get_status_by_visit_id,
    update_payment_accrued,
)
from commcare_connect.users.models import User


@pytest.mark.django_db
def test_bulk_update_visit_status(opportunity: Opportunity, mobile_user: User):
    visits = UserVisitFactory.create_batch(
        5, opportunity=opportunity, status=VisitValidationStatus.pending.value, user=mobile_user
    )
    dataset = Dataset(headers=["visit id", "status", "rejected reason"])
    dataset.extend([[visit.xform_id, VisitValidationStatus.approved.value, ""] for visit in visits])

    import_status = _bulk_update_visit_status(opportunity, dataset)
    assert not import_status.missing_visits
    after_status = set(UserVisit.objects.filter(opportunity=opportunity).values_list("status", flat=True))
    assert after_status == {VisitValidationStatus.approved.value}


@pytest.mark.django_db
def test_bulk_update_reason(opportunity: Opportunity, mobile_user: User):
    visit = UserVisitFactory.create(
        opportunity=opportunity, status=VisitValidationStatus.pending.value, user=mobile_user
    )
    reason = "bad form"
    dataset = Dataset(headers=["visit id", "status", "rejected reason"])
    dataset.extend([[visit.xform_id, VisitValidationStatus.rejected.value, reason]])
    import_status = _bulk_update_visit_status(opportunity, dataset)
    assert not import_status.missing_visits
    visit.refresh_from_db()
    assert visit.status == VisitValidationStatus.rejected
    assert visit.reason == reason


@pytest.mark.django_db
def test_payment_accrued(opportunity: Opportunity, mobile_user: User):
    payment_units = PaymentUnitFactory.create_batch(2, opportunity=opportunity)
    deliver_units = []
    for payment_unit in payment_units:
        deliver_units += DeliverUnitFactory.create_batch(2, payment_unit=payment_unit, app=opportunity.deliver_app)

    visits = []
    for deliver_unit in deliver_units:
        visits.append(
            UserVisitFactory(
                opportunity=opportunity,
                user=mobile_user,
                deliver_unit=deliver_unit,
                entity_id=deliver_unit.payment_unit.name,
                status=VisitValidationStatus.approved.value,
            )
        )
    update_payment_accrued(opportunity, {mobile_user.id})
    assert OpportunityAccess.objects.filter(user=mobile_user, opportunity=opportunity).exists()
    access = OpportunityAccess.objects.get(user=mobile_user, opportunity=opportunity)
    assert access.payment_accrued == sum(payment_unit.amount for payment_unit in payment_units)


@pytest.mark.parametrize(
    "headers,rows,expected",
    [
        (
            ["visit id", "status", "rejected reason"],
            [[123, "approved", ""], ["abc", "rejected", ""]],
            {"123": VisitValidationStatus.approved.value, "abc": VisitValidationStatus.rejected.value},
        ),
        (
            ["extra col", "visit id", "status", "rejected reason"],
            [["x", "1", "approved", ""], ["y", "2", "rejected", ""]],
            {"1": VisitValidationStatus.approved.value, "2": VisitValidationStatus.rejected.value},
        ),
        (["a", "status"], [], ImportException("Missing required column(s): 'visit id'")),
        (["visit id", "a"], [], ImportException("Missing required column(s): 'status'")),
    ],
)
def test_get_status_by_visit_id(headers, rows, expected):
    dataset = Dataset(headers=headers)
    dataset.extend(rows)

    if isinstance(expected, ImportException):
        with pytest.raises(ImportException, match=re.escape(expected.message)):
            get_status_by_visit_id(dataset)
    else:
        actual, _ = get_status_by_visit_id(dataset)
        assert actual == expected
