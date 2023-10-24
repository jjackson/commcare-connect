import httpx
from django.conf import settings
from httpx import BasicAuth, Response

from commcare_connect.connect_id_client.models import ConnectIdUser, Message, MessagingBulkResponse, MessagingResponse

GET = "GET"
POST = "POST"


def fetch_users(phone_number_list: list[str]) -> list[ConnectIdUser]:
    response = _make_request(GET, "/users/fetch_users", params={"phone_numbers": phone_number_list})
    data = response.json()
    return [ConnectIdUser(**user_dict) for user_dict in data["found_users"]]


def send_message(message: Message):
    """Send a push notification to a user."""
    response = _make_request(POST, "/messaging/send/", json=message.asdict())
    data = response.json()
    return MessagingResponse.build(**data)


def send_message_bulk(messages: list[Message]) -> MessagingBulkResponse:
    """Send a push notification to multiple users."""
    json = {"messages": [message.asdict() for message in messages]}
    response = _make_request(POST, "/messaging/send_bulk/", json=json)
    data = response.json()
    return MessagingBulkResponse.build(**data)


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
