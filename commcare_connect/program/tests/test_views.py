from http import HTTPStatus

import pytest
from django.contrib import messages
from django.test import Client
from django.urls import reverse

from commcare_connect.opportunity.tests.factories import DeliveryTypeFactory
from commcare_connect.organization.models import Organization
from commcare_connect.program.models import Program
from commcare_connect.program.tests.factories import ProgramFactory
from commcare_connect.users.models import User


@pytest.mark.django_db
class TestProgramListView:
    @pytest.fixture(autouse=True)
    def setup(self, program_manager_org: Organization, program_manager_org_user_admin: User):
        self.organization = program_manager_org
        self.user = program_manager_org_user_admin
        self.list_url = reverse("program:list", kwargs={"org_slug": self.organization.slug})
        self.programs = ProgramFactory.create_batch(15, organization=self.organization)

    def test_view_url_exists_at_desired_location(self, client):
        client.force_login(self.user)
        response = client.get(self.list_url)
        assert response.status_code == 200

    def test_pagination_is_ten(self, client):
        client.force_login(self.user)
        response = client.get(self.list_url)
        assert response.status_code == HTTPStatus.OK
        programs = response.context["page_obj"].object_list
        assert len(programs) == 10

    def test_pagination_next_page(self, client):
        client.force_login(self.user)
        response = client.get(f"{self.list_url}?page=2")
        assert response.status_code == HTTPStatus.OK
        programs = response.context["page_obj"].object_list
        assert len(programs) == 5

    def test_default_ordering(self, client):
        client.force_login(self.user)
        response = client.get(self.list_url)
        assert response.status_code == HTTPStatus.OK
        page_obj = response.context["page_obj"]
        programs = page_obj.object_list
        expected_programs = sorted(self.programs, key=lambda p: p.name)
        self.check_order(programs, expected_programs[:10])

    def test_ordering_by_start_date(self, client):
        client.force_login(self.user)
        response = client.get(f"{self.list_url}?sort=start_date")
        assert response.status_code == HTTPStatus.OK
        page_obj = response.context["page_obj"]
        programs = page_obj.object_list
        expected_programs = sorted(self.programs, key=lambda p: p.start_date)
        self.check_order(programs, expected_programs[:10])

    def test_ordering_by_end_date(self, client):
        client.force_login(self.user)
        response = client.get(f"{self.list_url}?sort=end_date")
        assert response.status_code == HTTPStatus.OK
        page_obj = response.context["page_obj"]
        programs = page_obj.object_list
        expected_programs = sorted(self.programs, key=lambda p: p.end_date)
        self.check_order(programs, expected_programs[:10])

    def test_ordering_by_invalid_field(self, client):
        client.force_login(self.user)
        response = client.get(f"{self.list_url}?sort=invalid")
        assert response.status_code == HTTPStatus.OK
        page_obj = response.context["page_obj"]
        programs = page_obj.object_list
        expected_programs = sorted(self.programs, key=lambda p: p.name)
        self.check_order(programs, expected_programs[:10])

    @staticmethod
    def check_order(programs, expected_programs):
        for program, expected_program in zip(programs, expected_programs):  # Adjust for pagination
            assert program.name == expected_program.name


@pytest.mark.django_db
class TestProgramCreateOrUpdateView:
    @pytest.fixture(autouse=True)
    def setup(self, program_manager_org: Organization, program_manager_org_user_admin: User, client: Client):
        self.organization = program_manager_org
        self.user = program_manager_org_user_admin
        self.delivery_type = DeliveryTypeFactory.create()
        self.client = client
        client.force_login(self.user)
        self.program = ProgramFactory.create(organization=self.organization)
        self.init_url = reverse("program:init", kwargs={"org_slug": self.organization.slug})
        self.edit_url = reverse("program:edit", kwargs={"org_slug": self.organization.slug, "pk": self.program.pk})
        self.list_url = reverse("program:list", kwargs={"org_slug": self.organization.slug})

    def test_create_view(self):
        response = self.client.get(self.init_url)
        assert response.status_code == 200
        assert "program/program_add.html" in response.templates[0].name

    def test_create_program(self):
        data = {
            "name": "New Program",
            "description": "A description for the new program",
            "delivery_type": self.delivery_type.id,
            "budget": 10000,
            "currency": "USD",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        }
        response = self.client.post(self.init_url, data)
        assert response.status_code == HTTPStatus.FOUND
        assert Program.objects.filter(name="New Program").exists()
        assert "Program 'New Program' created successfully." in [
            msg.message for msg in messages.get_messages(response.wsgi_request)
        ]
        assert response.url == self.list_url

    def test_update_view(self):
        response = self.client.get(self.edit_url)
        assert response.status_code == HTTPStatus.OK
        assert "program/program_edit.html" in response.templates[0].name

    def test_update_program(self):
        data = {
            "name": "Updated Program Name",
            "description": "Updated description",
            "delivery_type": self.delivery_type.id,
            "organization": self.organization.id,
            "budget": 15000,
            "currency": "EUR",
            "start_date": "2024-02-01",
            "end_date": "2024-11-30",
        }
        response = self.client.post(self.edit_url, data)
        assert response.status_code == HTTPStatus.FOUND
        self.program.refresh_from_db()
        assert self.program.name == "Updated Program Name"
        assert "Program 'Updated Program Name' updated successfully." in [
            msg.message for msg in messages.get_messages(response.wsgi_request)
        ]
        assert response.url == self.list_url
