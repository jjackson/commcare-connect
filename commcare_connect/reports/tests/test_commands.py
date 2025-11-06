import datetime
from datetime import timezone

from django.core.management import call_command

from commcare_connect.opportunity.models import CompletedWorkStatus
from commcare_connect.opportunity.tests.factories import (
    AssessmentFactory,
    CompletedWorkFactory,
    OpportunityAccessFactory,
    OpportunityClaimFactory,
    OpportunityFactory,
    PaymentFactory,
    PaymentUnitFactory,
)
from commcare_connect.reports.models import UserAnalyticsData
from commcare_connect.users.tests.factories import UserFactory


def test_backfill_user_analytics_data(db):
    user = UserFactory(username="test", email=None)
    opportunity = OpportunityFactory()
    payment_unit = PaymentUnitFactory(opportunity=opportunity, max_total=1)
    access = OpportunityAccessFactory(
        user=user,
        opportunity=opportunity,
        invited_date=datetime.datetime(2023, 1, 1, tzinfo=timezone.utc),
        date_learn_started=datetime.datetime(2023, 1, 2, tzinfo=timezone.utc),
        completed_learn_date=datetime.datetime(2023, 1, 3, tzinfo=timezone.utc),
        accepted=True,
    )
    AssessmentFactory(
        opportunity_access=access,
        passed=True,
        date=datetime.datetime(2023, 1, 4, tzinfo=timezone.utc),
    )
    claim = OpportunityClaimFactory(
        opportunity_access=access,
    )
    claim.date_claimed = datetime.datetime(2023, 1, 5, tzinfo=timezone.utc)
    claim.save()
    completed_work = CompletedWorkFactory(
        opportunity_access=access,
        payment_unit=payment_unit,
        date_created=datetime.datetime(2023, 1, 6, tzinfo=timezone.utc),
        status=CompletedWorkStatus.approved,
        status_modified_date=datetime.datetime(2023, 1, 9, tzinfo=timezone.utc),
    )
    PaymentFactory(
        opportunity_access=access,
        date_paid=datetime.datetime(2023, 1, 7, tzinfo=timezone.utc),
    )

    assert not UserAnalyticsData.objects.filter(user=user).exists()
    call_command("backfill_user_analytics_data")
    assert UserAnalyticsData.objects.filter(user=user).exists()

    analytics_data = UserAnalyticsData.objects.get(user=user)
    assert analytics_data.has_opp_invite == access.invited_date
    assert analytics_data.has_accepted_opp == access.invited_date
    assert analytics_data.has_started_learning == access.date_learn_started
    assert analytics_data.has_completed_learning == access.completed_learn_date
    assert analytics_data.has_completed_assessment == datetime.datetime(2023, 1, 4, tzinfo=timezone.utc)
    assert analytics_data.has_claimed_job == datetime.datetime(2023, 1, 5, tzinfo=timezone.utc)
    assert analytics_data.has_started_job == completed_work.date_created
    assert analytics_data.has_paid == datetime.datetime(2023, 1, 7, tzinfo=timezone.utc)
    assert analytics_data.has_completed_opp == completed_work.status_modified_date
