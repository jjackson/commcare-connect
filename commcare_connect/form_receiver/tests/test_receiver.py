from unittest import mock

from rest_framework.test import APIRequestFactory

from commcare_connect.form_receiver.tests.xforms import get_assessment, get_form, get_learn_module
from commcare_connect.form_receiver.views import FormReceiver
from commcare_connect.users.models import User

receiver_view = FormReceiver.as_view()


def test_form_receiver_requires_auth(api_rf: APIRequestFactory):
    request = api_rf.post("/api/receiver/", data={"foo": "bar"})
    response = receiver_view(request)
    assert response.status_code == 403


def test_form_receiver_only_accept_json(user: User, api_rf: APIRequestFactory):
    request = api_rf.post("/api/receiver/", data={"foo": "bar"})
    request.user = user
    response = receiver_view(request)
    assert response.status_code == 415


def test_form_receiver_validation(user: User, api_rf: APIRequestFactory):
    request = api_rf.post("/api/receiver/", data={}, format="json")
    request.user = user
    response = receiver_view(request)
    assert response.status_code == 400
    assert set(response.data) == {"domain", "app_id", "form"}


def test_form_receiver(user: User, api_rf: APIRequestFactory):
    request = api_rf.post("/api/receiver/", data=get_form(), format="json")
    request.user = user
    with mock.patch("commcare_connect.form_receiver.processor.process_learn_modules") as process_learn_modules:
        response = receiver_view(request)
    assert response.status_code == 200, response.data
    assert process_learn_modules.call_count == 0


def test_form_receiver_learn_module(user: User, api_rf: APIRequestFactory):
    learn_module = get_learn_module()
    request = api_rf.post("/api/receiver/", data=get_form(form_block=learn_module), format="json")
    request.user = user
    _test_processing(request, 1, 0)


def test_form_receiver_assessment(user: User, api_rf: APIRequestFactory):
    assessment = get_assessment()
    request = api_rf.post("/api/receiver/", data=get_form(form_block=assessment), format="json")
    request.user = user
    _test_processing(request, 0, 1)


def _test_processing(request, expected_learn_module_calls, expected_assessment_calls):
    with (
        mock.patch("commcare_connect.form_receiver.processor.process_learn_modules") as process_learn_modules,
        mock.patch("commcare_connect.form_receiver.processor.process_assessments") as process_assessments,
    ):
        response = receiver_view(request)
    assert response.status_code == 200, response.data
    assert process_learn_modules.call_count == expected_learn_module_calls
    assert process_assessments.call_count == expected_assessment_calls
