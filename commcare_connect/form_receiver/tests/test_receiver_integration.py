import datetime
from copy import deepcopy
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from commcare_connect.form_receiver.tests.test_receiver_endpoint import add_credentials
from commcare_connect.form_receiver.tests.xforms import (
    AssessmentStubFactory,
    DeliverUnitStubFactory,
    LearnModuleJsonFactory,
    get_form_json,
)
from commcare_connect.opportunity.models import (
    Assessment,
    CompletedModule,
    CompletedWork,
    LearnModule,
    Opportunity,
    OpportunityClaimLimit,
    UserVisit,
    VisitValidationStatus,
)
from commcare_connect.opportunity.tests.factories import (
    DeliverUnitFactory,
    LearnModuleFactory,
    OpportunityAccessFactory,
    OpportunityClaimFactory,
    PaymentUnitFactory,
)
from commcare_connect.users.models import User


@pytest.mark.django_db
def test_form_receiver_learn_module(
    mobile_user_with_connect_link: User, api_client: APIClient, opportunity: Opportunity
):
    module_id = "learn_module_1"
    form_json = _get_form_json(opportunity.learn_app, module_id)
    assert CompletedModule.objects.count() == 0
    learn_module = LearnModuleFactory(app=opportunity.learn_app, slug=module_id)
    make_request(api_client, form_json, mobile_user_with_connect_link)

    assert CompletedModule.objects.count() == 1
    assert CompletedModule.objects.filter(
        module=learn_module,
        xform_id=form_json["id"],
        app_build_id=form_json["build_id"],
        app_build_version=form_json["metadata"]["app_build_version"],
    ).exists()


@pytest.mark.django_db
def test_form_receiver_learn_module_create(
    mobile_user_with_connect_link: User, api_client: APIClient, opportunity: Opportunity
):
    """Test that a new learn module is created if it doesn't exist."""
    module = LearnModuleJsonFactory()
    form_json = _get_form_json(opportunity.learn_app, module.id, module.json)
    assert CompletedModule.objects.count() == 0

    make_request(api_client, form_json, mobile_user_with_connect_link)
    assert CompletedModule.objects.count() == 1
    assert CompletedModule.objects.filter(
        module__slug=module.id,
        xform_id=form_json["id"],
        app_build_id=form_json["build_id"],
        app_build_version=form_json["metadata"]["app_build_version"],
    ).exists()

    assert LearnModule.objects.filter(
        app=opportunity.learn_app,
        slug=module.id,
        name=module.name,
        description=module.description,
        time_estimate=module.time_estimate,
    ).exists()


@pytest.mark.django_db
def test_form_receiver_assessment(
    mobile_user_with_connect_link: User, api_client: APIClient, opportunity: Opportunity
):
    passing_score = opportunity.learn_app.passing_score
    score = passing_score + 5
    assessment = AssessmentStubFactory(score=score).json
    form_json = get_form_json(
        form_block=assessment,
        domain=opportunity.learn_app.cc_domain,
        app_id=opportunity.learn_app.cc_app_id,
    )
    assert Assessment.objects.count() == 0

    make_request(api_client, form_json, mobile_user_with_connect_link)
    assert Assessment.objects.count() == 1
    assert Assessment.objects.filter(
        score=score,
        passing_score=passing_score,
        passed=True,
        xform_id=form_json["id"],
        app_build_id=form_json["build_id"],
        app_build_version=form_json["metadata"]["app_build_version"],
    ).exists()


@pytest.mark.django_db
def test_receiver_deliver_form(mobile_user_with_connect_link: User, api_client: APIClient, opportunity: Opportunity):
    deliver_unit = DeliverUnitFactory(app=opportunity.deliver_app, payment_unit=opportunity.paymentunit_set.first())
    stub = DeliverUnitStubFactory(id=deliver_unit.slug)
    form_json = get_form_json(
        form_block=stub.json,
        domain=deliver_unit.app.cc_domain,
        app_id=deliver_unit.app.cc_app_id,
    )
    assert UserVisit.objects.filter(user=mobile_user_with_connect_link).count() == 0

    make_request(api_client, form_json, mobile_user_with_connect_link)
    assert UserVisit.objects.filter(user=mobile_user_with_connect_link).count() == 1
    visit = UserVisit.objects.get(user=mobile_user_with_connect_link)
    assert visit.deliver_unit == deliver_unit
    assert visit.entity_id == stub.entity_id
    assert visit.entity_name == stub.entity_name


def _create_opp_and_form_json(
    opportunity,
    user,
    max_visits_per_user=100,
    daily_max_per_user=10,
    end_date=datetime.date.today(),
):
    payment_unit = PaymentUnitFactory(
        opportunity=opportunity, max_daily=daily_max_per_user, max_total=max_visits_per_user
    )
    access = OpportunityAccessFactory(user=user, opportunity=opportunity, accepted=True)
    claim = OpportunityClaimFactory(end_date=end_date, opportunity_access=access)
    OpportunityClaimLimit.create_claim_limits(opportunity, claim)

    deliver_unit = DeliverUnitFactory(app=opportunity.deliver_app, payment_unit=payment_unit)
    stub = DeliverUnitStubFactory(id=deliver_unit.slug)
    form_json = get_form_json(
        form_block=stub.json,
        domain=deliver_unit.app.cc_domain,
        app_id=deliver_unit.app.cc_app_id,
    )
    return form_json


@pytest.mark.django_db
def test_receiver_deliver_form_daily_visits_reached(
    user_with_connectid_link: User, api_client: APIClient, opportunity: Opportunity
):
    form_json = _create_opp_and_form_json(opportunity, user=user_with_connectid_link, daily_max_per_user=0)
    assert UserVisit.objects.filter(user=user_with_connectid_link).count() == 0
    make_request(api_client, form_json, user_with_connectid_link)
    assert UserVisit.objects.filter(user=user_with_connectid_link).count() == 1
    visit = UserVisit.objects.get(user=user_with_connectid_link)
    assert visit.status == VisitValidationStatus.over_limit


@pytest.mark.django_db
def test_receiver_deliver_form_max_visits_reached(
    user_with_connectid_link: User, api_client: APIClient, opportunity: Opportunity
):
    form_json = _create_opp_and_form_json(opportunity, user=user_with_connectid_link, max_visits_per_user=1)
    assert UserVisit.objects.filter(user=user_with_connectid_link).count() == 0
    make_request(api_client, form_json, user_with_connectid_link)
    assert UserVisit.objects.filter(user=user_with_connectid_link).count() == 1
    duplicate_json = deepcopy(form_json)
    duplicate_json["form"]["deliver"]["entity_id"] = str(uuid4())
    api_client.post("/api/receiver/", data=duplicate_json, format="json")
    assert UserVisit.objects.filter(user=user_with_connectid_link).count() == 2
    visit = UserVisit.objects.filter(user=user_with_connectid_link).last()
    assert visit.status == VisitValidationStatus.over_limit


@pytest.mark.django_db
def test_receiver_deliver_form_end_date_reached(
    user_with_connectid_link: User, api_client: APIClient, opportunity: Opportunity
):
    form_json = _create_opp_and_form_json(
        opportunity, user=user_with_connectid_link, end_date=datetime.date.today() - datetime.timedelta(days=100)
    )
    assert UserVisit.objects.filter(user=user_with_connectid_link).count() == 0
    assert CompletedWork.objects.count() == 0
    make_request(api_client, form_json, user_with_connectid_link)
    assert UserVisit.objects.filter(user=user_with_connectid_link).count() == 1
    assert CompletedWork.objects.count() == 1
    visit = UserVisit.objects.get(user=user_with_connectid_link)
    assert visit.status == VisitValidationStatus.over_limit


@pytest.mark.django_db
def test_receiver_deliver_form_before_start_date(
    user_with_connectid_link: User, api_client: APIClient, opportunity: Opportunity
):
    opportunity.start_date = datetime.date.today() + datetime.timedelta(days=10)
    opportunity.save()
    form_json = _create_opp_and_form_json(
        opportunity, user=user_with_connectid_link, end_date=datetime.date.today() + datetime.timedelta(days=100)
    )
    assert UserVisit.objects.filter(user=user_with_connectid_link).count() == 0
    make_request(api_client, form_json, user_with_connectid_link)
    assert UserVisit.objects.filter(user=user_with_connectid_link).count() == 1
    visit = UserVisit.objects.get(user=user_with_connectid_link)
    assert visit.status == VisitValidationStatus.trial
    assert CompletedWork.objects.count() == 0


def test_receiver_duplicate(user_with_connectid_link: User, api_client: APIClient, opportunity: Opportunity):
    form_json = _create_opp_and_form_json(opportunity, user=user_with_connectid_link)
    make_request(api_client, form_json, user_with_connectid_link)
    visit = UserVisit.objects.get(user=user_with_connectid_link)
    assert visit.status == VisitValidationStatus.pending
    duplicate_json = deepcopy(form_json)
    duplicate_json["id"] = str(uuid4())
    api_client.post("/api/receiver/", data=duplicate_json, format="json")
    visit = UserVisit.objects.get(xform_id=duplicate_json["id"])
    assert visit.status == VisitValidationStatus.duplicate


def _get_form_json(learn_app, module_id, form_block=None):
    form_json = get_form_json(
        form_block=form_block or LearnModuleJsonFactory(id=module_id).json,
        domain=learn_app.cc_domain,
        app_id=learn_app.cc_app_id,
    )
    return form_json


def make_request(api_client, form_json, user, expected_status_code=200):
    add_credentials(api_client, user)
    response = api_client.post("/api/receiver/", data=form_json, format="json")
    assert response.status_code == expected_status_code, response.data
