import datetime
import math

import pytest
from factory.faker import Faker

from commcare_connect.conftest import MobileUserFactory
from commcare_connect.opportunity.models import CompletedWorkStatus, Opportunity, VisitValidationStatus
from commcare_connect.opportunity.tests.factories import (
    CompletedWorkFactory,
    DeliverUnitFactory,
    OpportunityAccessFactory,
    PaymentUnitFactory,
    UserVisitFactory,
)
from commcare_connect.reports.views import _get_table_data_for_quarter


@pytest.mark.django_db
def test_delivery_stats(opportunity: Opportunity):
    payment_units = PaymentUnitFactory.create_batch(2, opportunity=opportunity)
    mobile_users = MobileUserFactory.create_batch(5)
    for payment_unit in payment_units:
        DeliverUnitFactory.create_batch(2, payment_unit=payment_unit, app=opportunity.deliver_app, optional=False)
    access_objects = []
    for mobile_user in mobile_users:
        access = OpportunityAccessFactory(user=mobile_user, opportunity=opportunity, accepted=True)
        access_objects.append(access)
        for payment_unit in payment_units:
            completed_work = CompletedWorkFactory(
                opportunity_access=access,
                payment_unit=payment_unit,
                status=CompletedWorkStatus.approved.value,
            )
            for deliver_unit in payment_unit.deliver_units.all():
                UserVisitFactory(
                    opportunity=opportunity,
                    user=mobile_user,
                    deliver_unit=deliver_unit,
                    status=VisitValidationStatus.approved.value,
                    opportunity_access=access,
                    completed_work=completed_work,
                    visit_date=Faker("date_time_this_month", tzinfo=datetime.UTC),
                )

    quarter = math.ceil(datetime.datetime.utcnow().month / 12 * 4)

    # delivery_type filter not applied
    all_data = _get_table_data_for_quarter((datetime.datetime.utcnow().year, quarter), None)
    assert all_data[0]["users"] == 5
    assert all_data[0]["services"] == 10
    assert all_data[0]["beneficiaries"] == 10

    # test delivery_type filter
    filtered_data = _get_table_data_for_quarter(
        (datetime.datetime.utcnow().year, quarter), opportunity.delivery_type.slug
    )
    assert filtered_data == all_data

    # unknown delivery-type should have no data
    unknown_delivery_type_data = _get_table_data_for_quarter((datetime.datetime.utcnow().year, quarter), "unknown")
    assert unknown_delivery_type_data[0]["users"] == 0
    assert unknown_delivery_type_data[0]["services"] == 0
    assert unknown_delivery_type_data[0]["beneficiaries"] == 0
