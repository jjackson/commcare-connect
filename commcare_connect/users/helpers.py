import requests
from allauth.utils import build_absolute_uri
from django.conf import settings
from django.urls import reverse

from commcare_connect.connect_id_client import send_message
from commcare_connect.connect_id_client.models import Message
from commcare_connect.organization.models import Organization
from commcare_connect.utils.sms import send_sms


def get_organization_for_request(request, view_kwargs):
    if not request.user.is_authenticated:
        return

    org_slug = view_kwargs.get("org_slug", None)
    if org_slug:
        try:
            return Organization.objects.get(slug=org_slug, memberships__user=request.user)
        except Organization.DoesNotExist:
            return None

    membership = request.user.memberships.select_related("organization").first()
    return membership.organization if membership else None


def create_hq_user(user, domain, api_key):
    mobile_worker_api_url = f"{settings.COMMCARE_HQ_URL}/a/{domain}/api/v0.5/user/"
    hq_request = requests.post(
        mobile_worker_api_url,
        json={
            "username": user.username,
            "connect_username": user.username,
        },
        headers={"Authorization": f"ApiKey {api_key.user.email}:{api_key.api_key}"},
    )
    if hq_request.status_code == 201:
        return True
    return False


def invite_user(user, opportunity_access):
    invite_id = opportunity_access.invite_id
    location = reverse("users:accept_invite", args=(invite_id,))
    url = build_absolute_uri(None, location)
    body = (
        "You have been invited to a new job in Commcare Connect. Click the following "
        f"link to share your information with the project and find out more {url}"
    )
    if not user.phone_number:
        return
    send_sms(user.phone_number, body)
    message = Message(
        usernames=[user.username],
        title="New job available on Commcare Connect",
        body=(
            "You have been invited to a new job in Commcare Connect. Click the notification"
            "to share your information with the project and find out more."
        ),
    )
    send_message(message)
