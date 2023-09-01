from collections.abc import Sequence
from typing import Any

from django.contrib.auth import get_user_model
from factory import Faker, RelatedFactory, SubFactory, post_generation
from factory.django import DjangoModelFactory

from commcare_connect.organization.models import Organization, UserOrganizationMembership
from commcare_connect.users.models import ConnectIDUserLink


class UserFactory(DjangoModelFactory):
    email = Faker("email")
    name = Faker("name")

    @post_generation
    def password(self, create: bool, extracted: Sequence[Any], **kwargs):
        password = (
            extracted
            if extracted
            else Faker(
                "password",
                length=42,
                special_chars=True,
                digits=True,
                upper_case=True,
                lower_case=True,
            ).evaluate(None, None, extra={"locale": None})
        )
        self.set_password(password)

    class Meta:
        model = get_user_model()
        django_get_or_create = ["email"]


class ConnectIdUserLinkFactory(DjangoModelFactory):
    user = SubFactory(UserFactory)
    commcare_username = Faker("word")

    class Meta:
        model = ConnectIDUserLink
        django_get_or_create = ["commcare_username"]


class MobileUserFactory(DjangoModelFactory):
    username = Faker("word")
    name = Faker("name")

    class Meta:
        model = get_user_model()
        django_get_or_create = ["username"]


class MobileUserWithConnectIDLink(MobileUserFactory):
    connectiduserlink = RelatedFactory(ConnectIdUserLinkFactory, "user", commcare_username="test")


class OrganizationFactory(DjangoModelFactory):
    name = Faker("company")

    class Meta:
        model = Organization


class MembershipFactory(DjangoModelFactory):
    class Meta:
        model = UserOrganizationMembership

    user = SubFactory(UserFactory)
    organization = SubFactory(OrganizationFactory)
    role = "admin"


class OrgWithUsersFactory(OrganizationFactory):
    admin = RelatedFactory(MembershipFactory, "organization", role="admin")
    member = RelatedFactory(MembershipFactory, "organization", role="member")
