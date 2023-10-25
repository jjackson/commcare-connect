from unittest import mock

import pytest

from commcare_connect.connect_id_client.models import ConnectIdUser
from commcare_connect.opportunity.models import OpportunityAccess
from commcare_connect.opportunity.tasks import add_connect_users
from commcare_connect.opportunity.tests.factories import OpportunityFactory
from commcare_connect.users.models import User


class TestConnectUserCreation:
    @pytest.mark.django_db
    def test_add_connect_user(self, httpx_mock):
        opportunity = OpportunityFactory()
        with (
            mock.patch("commcare_connect.opportunity.tasks.fetch_users") as fetch_users,
            mock.patch("commcare_connect.users.helpers.send_sms"),
        ):
            httpx_mock.add_response(
                method="POST",
                json={
                    "all_success": True,
                    "responses": [
                        {"username": "test", "status": "success"},
                        {"username": "test2", "status": "success"},
                    ],
                },
            )
            fetch_users.return_value = [
                ConnectIdUser(username="test", phone_number="+15555555555", name="a"),
                ConnectIdUser(username="test2", phone_number="+12222222222", name="b"),
            ]
            add_connect_users(["+15555555555", "+12222222222"], opportunity.id)

        user_list = User.objects.filter(username="test")
        assert len(user_list) == 1
        user = user_list[0]
        assert user.name == "a"
        assert user.phone_number == "+15555555555"
        assert len(OpportunityAccess.objects.filter(user=user_list.first(), opportunity=opportunity)) == 1

        user2 = User.objects.filter(username="test2")
        assert len(user2) == 1
        assert len(OpportunityAccess.objects.filter(user=user2.first(), opportunity=opportunity)) == 1
