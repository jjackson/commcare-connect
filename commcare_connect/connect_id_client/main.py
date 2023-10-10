import httpx
from django.conf import settings
from httpx import BasicAuth, Response

from commcare_connect.connect_id_client.models import ConnectIdUser

GET = "GET"
POST = "POST"


def fetch_users(phone_number_list) -> list[ConnectIdUser]:
    response = _make_request(GET, "/users/fetch_users", params={"phone_numbers": phone_number_list})
    data = response.json()
    return [ConnectIdUser(**user_dict) for user_dict in data["found_users"]]


def _make_request(method, path, params=None, json=None) -> Response:
    if json and not method == "POST":
        raise ValueError("json can only be used with POST requests")

    auth = BasicAuth(settings.CONNECTID_CLIENT_ID, settings.CONNECTID_CLIENT_SECRET)
    response = httpx.request(
        method,
        f"{settings.CONNECTID_URL}{path}",
        params=params,
        json=json,
        auth=auth,
    )
    response.raise_for_status()
    return response
