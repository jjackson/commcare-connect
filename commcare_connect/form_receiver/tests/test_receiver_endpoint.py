from unittest import mock

from rest_framework.test import APIRequestFactory

from commcare_connect.form_receiver.exceptions import ProcessingError
from commcare_connect.form_receiver.tests.xforms import get_form_json
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
    assert set(response.data) == {"domain", "metadata", "build_id", "app_id", "received_on", "form", "id"}


def test_process_xform_error(user: User, api_rf: APIRequestFactory):
    request = api_rf.post("/api/receiver/", data=get_form_json(), format="json")
    request.user = user
    with (mock.patch("commcare_connect.form_receiver.views.process_xform") as process_xform,):
        process_xform.side_effect = ProcessingError("oops, something went wrong")
        response = receiver_view(request)
    assert response.status_code == 400, response.data
    assert response.data == {"detail": "oops, something went wrong"}
