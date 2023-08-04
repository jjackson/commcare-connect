import pytest
from rest_framework.test import APIClient

from commcare_connect.form_receiver.tests.xforms import get_form_json, get_learn_module
from commcare_connect.opportunity.models import CompletedModule, Opportunity
from commcare_connect.opportunity.tests.factories import LearnModuleFactory, OpportunityFactory
from commcare_connect.users.models import User


@pytest.fixture()
def opportunity():
    return OpportunityFactory()


@pytest.mark.django_db
def test_form_receiver_learn_module_db(user: User, api_client: APIClient, opportunity: Opportunity):
    module_id = "learn_module_1"
    learn_app = opportunity.learn_app
    module = LearnModuleFactory(app=learn_app, slug=module_id)

    form_json = get_form_json(
        form_block=get_learn_module(module_id=module_id),
        domain=learn_app.cc_domain,
        app_id=learn_app.cc_app_id,
    )
    assert CompletedModule.objects.count() == 0

    api_client.force_authenticate(user=user)
    response = api_client.post("/api/receiver/", data=form_json, format="json")
    assert response.status_code == 200, response.data
    assert CompletedModule.objects.count() == 1
    CompletedModule.objects.filter(
        module=module,
        xform_id=form_json["id"],
        app_build_id=form_json["build_id"],
        app_build_version=form_json["metadata"]["app_build_version"],
    ).exists()
