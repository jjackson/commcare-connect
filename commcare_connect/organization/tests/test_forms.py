import pytest
from django.test import Client
from django.urls import reverse

from commcare_connect.organization.models import Organization
from commcare_connect.users.tests.factories import UserFactory


class TestAddMembersView:
    @pytest.fixture(autouse=True)
    def setup(self, organization: Organization, client: Client):
        self.url = reverse("organization:add_members", kwargs={"org_slug": organization.slug})
        self.user = organization.memberships.filter(role="admin").first().user
        self.client = client
        client.force_login(self.user)

    @pytest.mark.django_db
    def test_add_member_by_email(self, organization):
        new_user = UserFactory(email="test@example.com")
        data = {"email_or_username": new_user.email, "role": "member"}
        response = self.client.post(self.url, data)
        assert response.status_code == 302
        assert response.url == reverse("organization:home", kwargs={"org_slug": organization.slug})
        membership = organization.memberships.get(user=new_user)
        assert membership.role == data["role"]

    @pytest.mark.django_db
    def test_add_member_by_username(self, organization):
        new_user = UserFactory(username="test")
        data = {"email_or_username": new_user.username, "role": "member"}
        response = self.client.post(self.url, data)
        assert response.status_code == 302
        membership = organization.memberships.get(user=new_user)
        assert membership.role == data["role"]
        assert not membership.accepted

    @pytest.mark.django_db
    def test_add_member_nonexistent_user(self, organization):
        data = {"email_or_username": "nonexistent@example.com", "role": "member"}
        response = self.client.post(self.url, data)
        assert response.status_code == 302
        assert not organization.memberships.filter(user__email="nonexistent@example.com").exists()

    @pytest.mark.django_db
    def test_add_existing_member(self, organization):
        existing_user = UserFactory(email="test@example.com")
        organization.members.add(existing_user, through_defaults={"role": "member"})

        data = {"email_or_username": existing_user.email, "role": "admin"}
        response = self.client.post(self.url, data)
        assert response.status_code == 302
        assert organization.memberships.filter(user=existing_user).count() == 1
        assert organization.memberships.get(user=existing_user).role == "member"
