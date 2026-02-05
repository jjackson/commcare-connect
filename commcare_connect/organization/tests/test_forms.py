import pytest
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

from commcare_connect.organization.forms import OrganizationChangeForm
from commcare_connect.organization.models import LLOEntity, Organization
from commcare_connect.users.models import User
from commcare_connect.users.tests.factories import UserFactory
from commcare_connect.utils.permission_const import WORKSPACE_ENTITY_MANAGEMENT_ACCESS


class TestAddMembersView:
    @pytest.fixture(autouse=True)
    def setup(self, organization: Organization, client: Client):
        self.url = reverse("organization:add_members", kwargs={"org_slug": organization.slug})
        self.user = organization.memberships.filter(role="admin").first().user
        self.client = client
        client.force_login(self.user)

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        "email, role, expected_status_code, create_user, expected_role, should_exist",
        [
            ("testformember@example.com", "member", 302, True, "member", True),
            ("testforadmin@example.com", "admin", 302, True, "admin", True),
            ("nonexistent@example.com", "member", 302, False, None, False),
            ("existing@example.com", "admin", 302, True, "member", True),
        ],
    )
    def test_add_member(
        self,
        email,
        role,
        expected_status_code,
        create_user,
        expected_role,
        should_exist,
        organization,
    ):
        if create_user:
            user = UserFactory(email=email)

            if email == "existing@example.com":
                organization.members.add(user, through_defaults={"role": expected_role})

        data = {"email": email, "role": role}
        response = self.client.post(self.url, data)

        membership_filter = {"user__email": email}

        assert response.status_code == expected_status_code
        membership_exists = organization.memberships.filter(**membership_filter).exists()
        assert membership_exists == should_exist

        if should_exist and expected_role:
            membership = organization.memberships.get(**membership_filter)
            assert membership.role == expected_role


@pytest.mark.django_db
class TestOrganizationChangeForm:
    def test_update_name(self, organization: Organization):
        user = UserFactory()
        form = OrganizationChangeForm(data={"name": "New Name"}, user=user, instance=organization)
        assert form.is_valid()
        form.save()
        organization.refresh_from_db()
        assert organization.name == "New Name"

    def test_update_program_manager_without_permission(self, organization: Organization):
        user = UserFactory()
        organization.program_manager = False
        organization.save()
        form = OrganizationChangeForm(
            data={"name": "New Name", "program_manager": True},
            user=user,
            instance=organization,
        )
        assert form.is_valid()
        form.save()
        organization.refresh_from_db()
        assert not organization.program_manager
        assert organization.name == "New Name"

    def test_update_llo_entity_with_permission(self, organization: Organization):
        user = UserFactory()
        app_label, codename = WORKSPACE_ENTITY_MANAGEMENT_ACCESS.split(".")
        perm = Permission.objects.get(codename=codename, content_type__app_label=app_label)
        user.user_permissions.add(perm)
        user = User.objects.get(pk=user.pk)
        llo_entity = LLOEntity.objects.create(name="Test LLO")
        organization.llo_entity = None
        organization.save()

        form = OrganizationChangeForm(
            data={"name": organization.name, "llo_entity": llo_entity.pk},
            user=user,
            instance=organization,
        )
        assert form.is_valid(), form.errors
        form.save()
        organization.refresh_from_db()
        assert organization.llo_entity == llo_entity

    def test_create_llo_entity_with_permission(self, organization: Organization):
        user = UserFactory()
        app_label, codename = WORKSPACE_ENTITY_MANAGEMENT_ACCESS.split(".")
        perm = Permission.objects.get(codename=codename, content_type__app_label=app_label)
        user.user_permissions.add(perm)
        user = User.objects.get(pk=user.pk)

        organization.llo_entity = None
        organization.save()

        assert LLOEntity.objects.count() == 0
        form = OrganizationChangeForm(
            data={"name": organization.name, "llo_entity": "New LLO Entity"},
            user=user,
            instance=organization,
        )
        assert form.is_valid(), form.errors
        form.save()
        organization.refresh_from_db()
        assert organization.llo_entity is not None
        assert organization.llo_entity.name == "New LLO Entity"
        assert LLOEntity.objects.count() == 1

    def test_update_llo_entity_without_permission(self, organization: Organization):
        user = UserFactory()
        llo_entity = LLOEntity.objects.create(name="Test LLO")
        organization.llo_entity = None
        organization.save()

        form = OrganizationChangeForm(
            data={"name": "New Name", "llo_entity": llo_entity.pk},
            user=user,
            instance=organization,
        )
        assert form.is_valid()
        form.save()
        organization.refresh_from_db()
        assert organization.llo_entity is None
        assert organization.name == "New Name"
