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
            request.json.return_value = {"found_users": [{"username": "test"}]}
            add_connect_users(["+15555555555"], opportunity.id)
        user = User.objects.get(username="test")
        assert len(OpportunityAccess.objects.filter(user=user, opportunity=opportunity)) == 1
