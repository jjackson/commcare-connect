"""Tests for OpportunityImageTypesAPIView (Connect-based image type discovery)."""
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
)


@pytest.fixture
def labs_client(db):
    """Django test client with a valid labs session injected."""
    client = Client(enforce_csrf_checks=False)
    session = client.session
    session["labs_oauth"] = {
        "access_token": "test-token-abc",
        "expires_at": time.time() + 3600,
        "user_profile": {"username": "testuser", "id": 42, "email": "testuser@example.com"},
    }
    session.save()
    return client


@override_settings(**LABS_SETTINGS)
def test_image_types_returns_unique_question_ids(labs_client):
    """View returns unique question_ids discovered from sampled Connect visits."""
    sample_visits = [
        {
            "id": 1,
            "form_json": {"form": {"group": {"photo_a": "img1.jpg"}}},
            "images": [{"blob_id": "b1", "name": "img1.jpg"}],
            "username": "user1",
            "entity_name": "Entity1",
            "visit_date": "2024-01-01",
        },
        {
            "id": 2,
            "form_json": {"form": {"group": {"photo_b": "img2.jpg"}}},
            "images": [{"blob_id": "b2", "name": "img2.jpg"}],
            "username": "user2",
            "entity_name": "Entity2",
            "visit_date": "2024-01-02",
        },
    ]

    with patch("commcare_connect.audit.views.AuditDataAccess") as MockDA:
        mock_da = MockDA.return_value
        mock_da.fetch_visits_slim.return_value = [{"id": 1}, {"id": 2}]
        mock_da.fetch_visits_for_ids.return_value = sample_visits

        response = labs_client.get("/audit/api/opportunity/42/image-questions/")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2
    ids = {item["id"] for item in data}
    assert "group/photo_a" in ids
    assert "group/photo_b" in ids


@override_settings(**LABS_SETTINGS)
def test_image_types_requires_auth():
    """Unauthenticated request redirects to login."""
    client = Client()
    response = client.get("/audit/api/opportunity/42/image-questions/")
    assert response.status_code in (302, 401)


@override_settings(**LABS_SETTINGS)
def test_image_types_empty_opportunity(labs_client):
    """Returns empty list when no visits exist."""
    with patch("commcare_connect.audit.views.AuditDataAccess") as MockDA:
        mock_da = MockDA.return_value
        mock_da.fetch_visits_slim.return_value = []

        response = labs_client.get("/audit/api/opportunity/42/image-questions/")

    assert response.status_code == 200
    assert response.json() == []
