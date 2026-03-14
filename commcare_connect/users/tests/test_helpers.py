import pytest

from commcare_connect.users.helpers import build_hq_user_payload


@pytest.mark.django_db
class TestBuildHqUserPayload:
    def test_includes_all_fields(self, mobile_user):
        mobile_user.name = "Test User"
        mobile_user.email = "test@example.com"
        mobile_user.phone_number = "+1234567890"

        payload = build_hq_user_payload(mobile_user)

        assert payload == {
            "username": mobile_user.username,
            "connect_username": mobile_user.username,
            "first_name": "Test User",
            "email": "test@example.com",
            "default_phone_number": "+1234567890",
        }

    def test_excludes_email_when_null(self, mobile_user):
        mobile_user.email = None

        payload = build_hq_user_payload(mobile_user)

        assert "email" not in payload

    def test_excludes_name_when_blank(self, mobile_user):
        mobile_user.name = ""

        payload = build_hq_user_payload(mobile_user)

        assert "first_name" not in payload

    def test_excludes_phone_when_null(self, mobile_user):
        mobile_user.phone_number = None

        payload = build_hq_user_payload(mobile_user)

        assert "default_phone_number" not in payload
