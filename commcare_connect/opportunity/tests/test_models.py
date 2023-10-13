import pytest

from commcare_connect.opportunity.tests.factories import CompletedModuleFactory, OpportunityAccessFactory


@pytest.mark.django_db
def test_learn_progress():
    module = CompletedModuleFactory()
    access_1 = OpportunityAccessFactory(opportunity=module.opportunity, user=module.user)
    access_2 = OpportunityAccessFactory(opportunity=module.opportunity)
    assert access_1.learn_progress == 100
    assert access_2.learn_progress == 0
