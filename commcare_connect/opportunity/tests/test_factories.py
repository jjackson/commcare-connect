import pytest

from commcare_connect.opportunity.tests.factories import DeliverFormFactory, OpportunityFactory


@pytest.mark.django_db
def test_opportunity_factory():
    opportunity = OpportunityFactory()
    assert opportunity.organization == opportunity.learn_app.organization
    assert opportunity.organization == opportunity.deliver_app.organization
    assert opportunity.deliver_form.count() == 1
    assert opportunity.deliver_form.first().app == opportunity.deliver_app


@pytest.mark.django_db
def test_deliver_form_factory():
    deliver_form = DeliverFormFactory()
    opportunity = deliver_form.opportunity
    assert deliver_form.app == opportunity.deliver_app
    assert deliver_form.app.organization == opportunity.organization
    assert deliver_form.app.organization == opportunity.learn_app.organization
