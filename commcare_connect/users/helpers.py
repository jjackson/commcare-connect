import requests

from django.conf import settings

from commcare_connect.organization.models import Organization


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
    mobile_worker_api_url = f"{settings.COMMCARE_HQ_URL}/a/{domain}/api/v0.5/user"
    hq_request = requests.post(
        mobile_worker_api_url,
        data={
            "username": user.username,
            "connect_user": user.username,
        },
        headers={"Authorization": f"ApiKey {api_key.user.email}:{api_key.api_key}"},
    )
    if hq_request.status_code == 201:
        return True
    return False
