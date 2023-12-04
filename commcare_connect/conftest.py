import pytest
from rest_framework.test import APIClient, APIRequestFactory

from commcare_connect.opportunity.tests.factories import (
    OpportunityAccessFactory,
    OpportunityClaimFactory,
    OpportunityFactory,
)
from commcare_connect.organization.models import Organization
from commcare_connect.users.models import User
from commcare_connect.users.tests.factories import (
    ConnectIdUserLinkFactory,
    MobileUserFactory,
    OrgWithUsersFactory,
    UserFactory,
)


@pytest.fixture(autouse=True)
def media_storage(settings, tmpdir):
    settings.MEDIA_ROOT = tmpdir.strpath


@pytest.fixture()
def api_rf() -> APIRequestFactory:
    """APIRequestFactory instance"""

    return APIRequestFactory()


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def organization(db) -> Organization:
    return OrgWithUsersFactory()


@pytest.fixture
def user(db) -> User:
    return UserFactory()


@pytest.fixture()
def opportunity():
    return OpportunityFactory()


@pytest.fixture
def mobile_user(db, opportunity) -> User:
    user = MobileUserFactory()
    OpportunityAccessFactory(user=user, opportunity=opportunity)
    return user


@pytest.fixture
def mobile_user_with_connect_link(db, opportunity) -> User:
    user = MobileUserFactory()
    access = OpportunityAccessFactory(user=user, opportunity=opportunity)
    OpportunityClaimFactory(
        max_payments=opportunity.max_visits_per_user,
        end_date=opportunity.end_date,
        opportunity_access=access,
    )
    ConnectIdUserLinkFactory(user=user, commcare_username=f"test@{opportunity.learn_app.cc_domain}.commcarehq.org")
    if opportunity.learn_app.cc_domain != opportunity.deliver_app.cc_domain:
        ConnectIdUserLinkFactory(
            user=user, commcare_username=f"test@{opportunity.deliver_app.cc_domain}.commcarehq.org"
        )
    return user


@pytest.fixture
def org_user_member(organization) -> User:
    return organization.memberships.filter(role="member").first().user


@pytest.fixture
def org_user_admin(organization) -> User:
    return organization.memberships.filter(role="admin").first().user
