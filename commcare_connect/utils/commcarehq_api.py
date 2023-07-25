import asyncio
import datetime
import itertools

import httpx
from allauth.socialaccount.models import SocialAccount, SocialApp, SocialToken
from asgiref.sync import async_to_sync
from django.conf import settings
from django.utils import timezone


def refresh_access_token(user, force=False):
    social_app = SocialApp.objects.filter(provider="commcarehq").first()
    social_acc = SocialAccount.objects.filter(user=user).first()
    social_token = SocialToken.objects.filter(account=social_acc).first()

    if not force and social_token.expires_at > timezone.now():
        return social_token

    response = httpx.post(
        f"{settings.COMMCARE_HQ_URL}/oauth/token/",
        data={
            "grant_type": "refresh_token",
            "client_id": social_app.client_id,
            "client_secret": social_app.secret,
            "refresh_token": social_token.token_secret,
        },
    )
    if response.status_code != 200:
        raise Exception(f"Failed to refresh token: {response.text}")

    data = response.json()
    if data.get("access_token", ""):
        social_token.token = data["access_token"]
        social_token.token_secret = data["refresh_token"]
        social_token.expires_at = timezone.now() + datetime.timedelta(seconds=900)
        social_token.save()

    return social_token


def get_domains_for_user(user):
    social_token = refresh_access_token(user)
    response = httpx.get(
        f"{settings.COMMCARE_HQ_URL}/api/v0.5/user_domains/",
        headers={"Authorization": f"Bearer {social_token}"},
    )
    data = response.json()
    domains = [domain["domain_name"] for domain in data["objects"]]
    return domains


def get_applications_for_user(user):
    social_token = refresh_access_token(user)
    domains = get_domains_for_user(user)
    return _get_applications_for_domains(social_token, domains)


@async_to_sync
async def _get_applications_for_domains(social_token, domains):
    async with httpx.AsyncClient(timeout=30, headers={"Authorization": f"Bearer {social_token}"}) as client:
        tasks = []
        for domain in domains:
            tasks.append(asyncio.ensure_future(_get_commcare_app_json(client, domain)))

        domain_apps = await asyncio.gather(*tasks)
    applications = list(itertools.chain.from_iterable(domain_apps))
    return applications


async def _get_commcare_app_json(client, domain):
    applications = []
    response = await client.get(f"{settings.COMMCARE_HQ_URL}/a/{domain}/api/v0.5/application/")
    data = response.json()

    def _get_name(block: dict):
        name_data = block.get("name", {})
        for lang in ["en"] + list(name_data):
            if lang in name_data:
                return name_data[lang]

    for application in data.get("objects", []):
        applications.append({"id": application.get("id"), "name": application.get("name"), "domain": domain})
    return applications
