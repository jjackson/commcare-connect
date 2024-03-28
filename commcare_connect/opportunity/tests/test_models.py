import pytest

from commcare_connect.opportunity.models import Opportunity, OpportunityAccess, OpportunityClaimLimit
from commcare_connect.opportunity.tests.factories import (
    CompletedModuleFactory,
    OpportunityAccessFactory,
    OpportunityClaimFactory,
    OpportunityClaimLimitFactory,
    PaymentUnitFactory,
)
from commcare_connect.users.models import User
from commcare_connect.users.tests.factories import MobileUserFactory


@pytest.mark.django_db
def test_learn_progress():
    module = CompletedModuleFactory()
    access_1 = OpportunityAccessFactory(opportunity=module.opportunity, user=module.user)
    access_2 = OpportunityAccessFactory(opportunity=module.opportunity)
    assert access_1.learn_progress == 100
    assert access_2.learn_progress == 0


@pytest.mark.django_db
def test_opportunity_stats(opportunity: Opportunity, mobile_user: User):
    payment_unit_sub = PaymentUnitFactory(
        opportunity=opportunity, max_total=100, max_daily=10, amount=5, parent_payment_unit=None
    )
    payment_unit1 = PaymentUnitFactory(
        opportunity=opportunity,
        max_total=100,
        max_daily=10,
        amount=3,
        parent_payment_unit=payment_unit_sub,
    )
    payment_unit2 = PaymentUnitFactory(
        opportunity=opportunity, max_total=100, max_daily=10, amount=5, parent_payment_unit=None
    )
    assert set(list(opportunity.top_level_paymentunits.values_list("id", flat=True))) == {
        payment_unit1.id,
        payment_unit2.id,
    }

    assert opportunity.budget_per_user == sum([p.amount * p.max_total for p in [payment_unit1, payment_unit2]])
    assert opportunity.number_of_users == opportunity.total_budget / opportunity.budget_per_user
    assert (
        opportunity.allotted_visits
        == sum([pu.max_total for pu in [payment_unit1, payment_unit2]]) * opportunity.number_of_users
    )

    access = OpportunityAccess.objects.get(opportunity=opportunity, user=mobile_user)
    # max_payments to be removed
    claim = OpportunityClaimFactory(opportunity_access=access, max_payments=0)

    ocl1 = OpportunityClaimLimitFactory(opportunity_claim=claim, payment_unit=payment_unit1)
    ocl2 = OpportunityClaimLimitFactory(opportunity_claim=claim, payment_unit=payment_unit2)

    opportunity.claimed_budget == (ocl1.max_visits * payment_unit1.amount) + (ocl2.max_visits * payment_unit2.amount)


@pytest.mark.django_db
def test_claim_limits(opportunity: Opportunity):
    payment_units = PaymentUnitFactory.create_batch(2, opportunity=opportunity, parent_payment_unit=None)
    budget_per_user = sum([p.max_total * p.amount for p in payment_units])
    # budget not enough for more than 2 users
    opportunity.total_budget = budget_per_user + budget_per_user * 0.5
    mobile_users = MobileUserFactory.create_batch(3)
    for mobile_user in mobile_users:
        access = OpportunityAccessFactory(user=mobile_user, opportunity=opportunity, accepted=True)
        claim = OpportunityClaimFactory(opportunity_access=access, max_payments=0)
        OpportunityClaimLimit.create_claim_limits(opportunity, claim)

    assert opportunity.claimed_budget <= int(opportunity.total_budget)
    assert opportunity.claimed_visits <= int(opportunity.allotted_visits)
    assert opportunity.remaining_budget < payment_units[0].amount + payment_units[1].amount

    def limit_count(user):
        return OpportunityClaimLimit.objects.filter(opportunity_claim__opportunity_access__user=user).count()

    assert limit_count(mobile_users[0]) == 2
    assert limit_count(mobile_users[1]) in [1, 2]
    assert limit_count(mobile_users[2]) == 0
