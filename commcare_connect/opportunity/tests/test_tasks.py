from unittest import mock

import pytest

from commcare_connect.opportunity.models import OpportunityAccess
from commcare_connect.opportunity.tasks import add_connect_users
from commcare_connect.opportunity.tests.factories import OpportunityFactory
from commcare_connect.users.models import User


class TestConnectUserCreation:
    @pytest.mark.django_db
    def test_add_connect_user(self):
        opportunity = OpportunityFactory()
        with mock.patch("commcare_connect.opportunity.tasks.requests.get") as request:
            request.return_value.json.return_value = {
                "found_users": [
                    {"username": "test", "phone_number": "+15555555555", "name": "a"},
                    {"username": "test2", "phone_number": "+12222222222", "name": "b"},
                ]
            }
            add_connect_users(["+15555555555", "+12222222222"], opportunity.id)

        user_list = User.objects.filter(username="test")
        assert len(user) == 1
        user = user_list[0]
        assert user.name == "a"
        assert user.phone_number == "+15555555555"
        assert len(OpportunityAccess.objects.filter(user=user.first(), opportunity=opportunity)) == 1

        user2 = User.objects.filter(username="test2")
        assert len(user2) == 1
        assert len(OpportunityAccess.objects.filter(user=user2.first(), opportunity=opportunity)) == 1
