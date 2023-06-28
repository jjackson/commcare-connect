import datetime

import requests
from allauth.socialaccount.models import SocialAccount, SocialApp, SocialToken
from django.conf import settings
from django.utils import timezone


def refresh_access_token(user):
    social_app = SocialApp.objects.filter(provider="commcarehq").first()
    social_acc = SocialAccount.objects.filter(user=user).first()
    social_token = SocialToken.objects.filter(account=social_acc).first()

    if social_token.expires_at > timezone.now():
        return social_token

    response = requests.post(
        f"{settings.COMMCARE_HQ_URL}/oauth/token/",
        data={
            "grant_type": "refresh_token",
            "client_id": social_app.client_id,
            "client_secret": social_app.secret,
            "refresh_token": social_token.token_secret,
        },
    )
    data = response.json()

    if data.get("access_token", ""):
        social_token.token = data["access_token"]
        social_token.token_secret = data["refresh_token"]
        social_token.expires_at = timezone.now() + datetime.timedelta(seconds=900)
        social_token.save()

    return social_token


def get_domains_for_user(user):
    social_token = refresh_access_token(user)
    response = requests.get(
        f"{settings.COMMCARE_HQ_URL}/api/v0.5/user_domains/",
        headers={"Authorization": f"Bearer {social_token}"},
    )
    data = response.json()
    domains = [domain["domain_name"] for domain in data["objects"]]
    return domains


def get_applications_for_user(user):
    social_token = refresh_access_token(user)
    domains = get_domains_for_user(user)
    applications = []

    for domain in domains:
        response = requests.get(
            f"{settings.COMMCARE_HQ_URL}/a/{domain}/api/v0.5/application/",
            headers={"Authorization": f"Bearer {social_token}"},
        )
        data = response.json()
        for application in data.get("objects", []):
            applications.append({"id": application.get("id"), "name": application.get("name"), "domain": domain})

    return applications
