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
    CompletedWorkStatus,
    LearnModule,
    Opportunity,
    OpportunityAccess,
    OpportunityClaim,
    UserVisit,
    VisitValidationStatus,
)
from commcare_connect.opportunity.tasks import approve_completed_work_and_update_payment_accrued
from commcare_connect.opportunity.tests.factories import DeliverUnitFactory, LearnModuleFactory
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
    deliver_unit = DeliverUnitFactory(app=opportunity.deliver_app)
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
    opportunity.daily_max_visits_per_user = daily_max_per_user
    opportunity.save()
    OpportunityClaim.objects.filter(
        opportunity_access__opportunity=opportunity,
        opportunity_access__user=user,
    ).update(max_payments=max_visits_per_user, end_date=end_date)
    deliver_unit = DeliverUnitFactory(app=opportunity.deliver_app)
    stub = DeliverUnitStubFactory(id=deliver_unit.slug)
    form_json = get_form_json(
        form_block=stub.json,
        domain=deliver_unit.app.cc_domain,
        app_id=deliver_unit.app.cc_app_id,
    )
    return form_json


@pytest.mark.django_db
def test_receiver_deliver_form_daily_visits_reached(
    mobile_user_with_connect_link: User, api_client: APIClient, opportunity: Opportunity
):
    form_json = _create_opp_and_form_json(opportunity, user=mobile_user_with_connect_link, daily_max_per_user=0)
    assert UserVisit.objects.filter(user=mobile_user_with_connect_link).count() == 0
    make_request(api_client, form_json, mobile_user_with_connect_link)
    assert UserVisit.objects.filter(user=mobile_user_with_connect_link).count() == 1
    visit = UserVisit.objects.get(user=mobile_user_with_connect_link)
    assert visit.status == VisitValidationStatus.over_limit


@pytest.mark.django_db
def test_receiver_deliver_form_max_visits_reached(
    mobile_user_with_connect_link: User, api_client: APIClient, opportunity: Opportunity
):
    form_json = _create_opp_and_form_json(opportunity, user=mobile_user_with_connect_link, max_visits_per_user=0)
    assert UserVisit.objects.filter(user=mobile_user_with_connect_link).count() == 0
    make_request(api_client, form_json, mobile_user_with_connect_link)
    assert UserVisit.objects.filter(user=mobile_user_with_connect_link).count() == 1
    visit = UserVisit.objects.get(user=mobile_user_with_connect_link)
    assert visit.status == VisitValidationStatus.over_limit


@pytest.mark.django_db
def test_receiver_deliver_form_end_date_reached(
    mobile_user_with_connect_link: User, api_client: APIClient, opportunity: Opportunity
):
    form_json = _create_opp_and_form_json(
        opportunity, user=mobile_user_with_connect_link, end_date=datetime.date.today() - datetime.timedelta(days=100)
    )
    assert UserVisit.objects.filter(user=mobile_user_with_connect_link).count() == 0
    make_request(api_client, form_json, mobile_user_with_connect_link)
    assert UserVisit.objects.filter(user=mobile_user_with_connect_link).count() == 1
    visit = UserVisit.objects.get(user=mobile_user_with_connect_link)
    assert visit.status == VisitValidationStatus.over_limit


def test_receiver_duplicate(mobile_user_with_connect_link: User, api_client: APIClient, opportunity: Opportunity):
    form_json = _create_opp_and_form_json(opportunity, user=mobile_user_with_connect_link)
    make_request(api_client, form_json, mobile_user_with_connect_link)
    visit = UserVisit.objects.get(user=mobile_user_with_connect_link)
    assert visit.status == VisitValidationStatus.pending
    duplicate_json = deepcopy(form_json)
    duplicate_json["id"] = str(uuid4())
    api_client.post("/api/receiver/", data=duplicate_json, format="json")
    visit = UserVisit.objects.get(xform_id=duplicate_json["id"])
    assert visit.status == VisitValidationStatus.duplicate
    assert ["duplicate", "A beneficiary with the same identifier already exists"] in visit.flag_reason.get("flags", [])


def test_flagged_form(mobile_user_with_connect_link: User, api_client: APIClient, opportunity: Opportunity):
    # The mock data for form fails with duration flag
    form_json = _create_opp_and_form_json(opportunity, user=mobile_user_with_connect_link)
    make_request(api_client, form_json, mobile_user_with_connect_link)
    visit = UserVisit.objects.get(user=mobile_user_with_connect_link)
    assert visit.status == VisitValidationStatus.pending
    assert visit.flagged
    assert len(visit.flag_reason.get("flags", []))


def test_auto_approve_unflagged_visits(
    mobile_user_with_connect_link: User, api_client: APIClient, opportunity: Opportunity
):
    form_json = _create_opp_and_form_json(opportunity, user=mobile_user_with_connect_link)
    form_json["metadata"]["timeEnd"] = "2023-06-07T12:36:10.178000Z"
    opportunity.auto_approve_visits = True
    opportunity.save()
    make_request(api_client, form_json, mobile_user_with_connect_link)
    visit = UserVisit.objects.get(user=mobile_user_with_connect_link)
    assert not visit.flagged
    assert visit.status == VisitValidationStatus.approved


def test_auto_approve_flagged_visits(
    mobile_user_with_connect_link: User, api_client: APIClient, opportunity: Opportunity
):
    form_json = _create_opp_and_form_json(opportunity, user=mobile_user_with_connect_link)
    opportunity.auto_approve_visits = True
    opportunity.save()
    make_request(api_client, form_json, mobile_user_with_connect_link)
    visit = UserVisit.objects.get(user=mobile_user_with_connect_link)
    assert visit.flagged
    assert visit.status == VisitValidationStatus.rejected


def test_auto_approve_payments_flagged_visit(
    mobile_user_with_connect_link: User, api_client: APIClient, opportunity: Opportunity
):
    # Flagged Visit
    form_json = _create_opp_and_form_json(opportunity, user=mobile_user_with_connect_link)
    opportunity.auto_approve_payments = True
    opportunity.save()
    make_request(api_client, form_json, mobile_user_with_connect_link)
    visit = UserVisit.objects.get(user=mobile_user_with_connect_link)
    assert visit.flagged
    assert visit.status == VisitValidationStatus.pending

    # No Payment Approval
    approve_completed_work_and_update_payment_accrued([visit.completed_work_id])
    access = OpportunityAccess.objects.get(user=mobile_user_with_connect_link, opportunity=opportunity)
    completed_work = CompletedWork.objects.get(opportunity_access=access)
    assert completed_work.status == CompletedWorkStatus.pending
    assert access.payment_accrued == 0


def test_auto_approve_payments_unflagged_visit(
    mobile_user_with_connect_link: User, api_client: APIClient, opportunity: Opportunity
):
    form_json = _create_opp_and_form_json(opportunity, user=mobile_user_with_connect_link)
    form_json["metadata"]["timeEnd"] = "2023-06-07T12:36:10.178000Z"
    opportunity.auto_approve_payments = True
    opportunity.save()
    make_request(api_client, form_json, mobile_user_with_connect_link)
    visit = UserVisit.objects.get(user=mobile_user_with_connect_link)
    assert not visit.flagged
    assert visit.status == VisitValidationStatus.pending

    # Payment Approval
    approve_completed_work_and_update_payment_accrued([visit.completed_work_id])
    access = OpportunityAccess.objects.get(user=mobile_user_with_connect_link, opportunity=opportunity)
    completed_work = CompletedWork.objects.get(opportunity_access=access)
    assert completed_work.status == CompletedWorkStatus.approved
    assert access.payment_accrued == completed_work.payment_accrued


def test_auto_approve_visits_and_payments(
    mobile_user_with_connect_link: User, api_client: APIClient, opportunity: Opportunity
):
    form_json = _create_opp_and_form_json(opportunity, user=mobile_user_with_connect_link)
    form_json["metadata"]["timeEnd"] = "2023-06-07T12:36:10.178000Z"
    opportunity.auto_approve_visits = True
    opportunity.auto_approve_payments = True
    opportunity.save()
    make_request(api_client, form_json, mobile_user_with_connect_link)
    visit = UserVisit.objects.get(user=mobile_user_with_connect_link)
    assert not visit.flagged
    assert visit.status == VisitValidationStatus.approved

    approve_completed_work_and_update_payment_accrued([visit.completed_work_id])
    access = OpportunityAccess.objects.get(user=mobile_user_with_connect_link, opportunity=opportunity)
    completed_work = CompletedWork.objects.get(opportunity_access=access)
    assert completed_work.status == CompletedWorkStatus.approved
    assert access.payment_accrued == completed_work.payment_accrued


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
