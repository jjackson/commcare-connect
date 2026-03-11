"""Tests for OpportunityImageQuestionsAPIView."""
import time
from unittest.mock import patch

import pytest
from django.test import Client, override_settings

LABS_MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "commcare_connect.labs.middleware.LabsAuthenticationMiddleware",
    "commcare_connect.labs.middleware.LabsURLWhitelistMiddleware",
    "commcare_connect.labs.context.LabsContextMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "commcare_connect.utils.middleware.CustomErrorHandlingMiddleware",
    "commcare_connect.utils.middleware.CurrentVersionMiddleware",
    "waffle.middleware.WaffleMiddleware",
    "commcare_connect.utils.middleware.CustomPGHistoryMiddleware",
]

LABS_SETTINGS = dict(
    IS_LABS_ENVIRONMENT=True,
    MIDDLEWARE=LABS_MIDDLEWARE,
    LOGIN_URL="/labs/login/",
    COMMCARE_HQ_URL="https://www.commcarehq.org",
    COMMCARE_API_KEY="test-api-key",
    COMMCARE_USERNAME="test@example.com",
)


@pytest.fixture
def labs_client(db):
    """Django test client with a valid labs session injected."""
    client = Client(enforce_csrf_checks=False)
    # Inject labs_oauth so LabsAuthenticationMiddleware creates a LabsUser
    session = client.session
    session["labs_oauth"] = {
        "access_token": "test-token-abc",
        "expires_at": time.time() + 3600,  # 1 hour from now
        "user_profile": {"username": "testuser", "id": 42, "email": "testuser@example.com"},
    }
    session.save()
    return client


SAMPLE_APP = {
    "modules": [
        {
            "name": "Health Service Delivery",
            "forms": [
                {
                    "name": "Health Service Delivery",
                    "xmlns": "http://openrosa.org/formdesigner/9EC52F6C",
                    "questions": [
                        {
                            "value": "/data/ors_group/ors_photo",
                            "type": "Image",
                            "label": "ORS Photo",
                        },
                        {
                            "value": "/data/ors_group/photo_link_ors",
                            "type": "DataBindOnly",
                            "label": "",
                            "calculate": "concat('https://hq.org/.../', /data/ors_group/ors_photo)",
                        },
                        {
                            "value": "/data/vita_group",
                            "type": "Group",
                            "label": "",
                            "relevant": "1 = 2",
                        },
                        {
                            "value": "/data/vita_group/vita_photo",
                            "type": "Image",
                            "label": "Vita A Photo",
                        },
                        {
                            "value": "/data/text_field",
                            "type": "Text",
                            "label": "Some text",
                        },
                    ],
                }
            ],
        }
    ]
}


@override_settings(**LABS_SETTINGS)
def test_image_questions_returns_all_images(labs_client):
    """View returns all Image-type questions from the app."""
    opp_meta = {
        "cc_domain": "test-domain",
        "cc_app_id": "app-abc",
        "opportunity_name": "Test Opp",
        "opportunity_id": 42,
    }
    with patch(
        "commcare_connect.audit.views.fetch_opportunity_metadata",
        return_value=opp_meta,
    ), patch("commcare_connect.audit.views.httpx.get") as mock_hq_get:
        mock_hq_get.return_value.status_code = 200
        mock_hq_get.return_value.raise_for_status = lambda: None
        mock_hq_get.return_value.json = lambda: SAMPLE_APP

        response = labs_client.get("/audit/api/opportunity/42/image-questions/")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # Both image questions are returned (no always-false filtering)
    assert len(data) == 2
    ids = {item["id"] for item in data}
    assert "ors_photo" in ids
    assert "vita_photo" in ids
    ors = next(item for item in data if item["id"] == "ors_photo")
    assert ors["label"] == "ORS Photo"
    assert ors["path"] == "ors_group/ors_photo"
    assert ors["hq_url_path"] == "ors_group/photo_link_ors"
    assert ors["form_name"] == "Health Service Delivery"


@override_settings(**LABS_SETTINGS)
def test_image_questions_requires_auth():
    """Unauthenticated request redirects to login."""
    client = Client()  # no labs_oauth session
    response = client.get("/audit/api/opportunity/42/image-questions/")
    assert response.status_code in (302, 401)


@override_settings(**LABS_SETTINGS)
def test_image_questions_handles_hq_error(labs_client):
    """When HQ API fails, returns 502."""
    import httpx

    opp_meta = {"cc_domain": "test-domain", "cc_app_id": "app-abc"}
    with patch(
        "commcare_connect.audit.views.fetch_opportunity_metadata",
        return_value=opp_meta,
    ), patch("commcare_connect.audit.views.httpx.get") as mock_hq_get:
        mock_hq_get.return_value.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500 Server Error", request=None, response=None
        )

        response = labs_client.get("/audit/api/opportunity/42/image-questions/")

    assert response.status_code == 502
