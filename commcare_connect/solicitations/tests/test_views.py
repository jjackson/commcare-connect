import pytest
from django.urls import reverse
from django.test import Client
from datetime import date, timedelta

from commcare_connect.solicitations.models import Solicitation, SolicitationType, SolicitationStatus
from commcare_connect.program.tests.factories import ProgramFactory
from commcare_connect.users.tests.factories import UserFactory


@pytest.mark.django_db
class TestPublicSolicitationListView:
    def test_public_list_view_shows_active_public_solicitations(self):
        program = ProgramFactory()
        user = UserFactory()
        client = Client()
        
        # Create various solicitations
        active_public_eoi = Solicitation.objects.create(
            title="Active Public EOI",
            description="Test description",
            target_population="Test population",
            scope_of_work="Test scope",
            solicitation_type=SolicitationType.EOI,
            status=SolicitationStatus.ACTIVE,
            is_publicly_listed=True,
            program=program,
            created_by=user,
            application_deadline=date.today() + timedelta(days=30)
        )
        
        active_private_eoi = Solicitation.objects.create(
            title="Active Private EOI",
            description="Test description",
            target_population="Test population", 
            scope_of_work="Test scope",
            solicitation_type=SolicitationType.EOI,
            status=SolicitationStatus.ACTIVE,
            is_publicly_listed=False,
            program=program,
            created_by=user,
            application_deadline=date.today() + timedelta(days=30)
        )
        
        draft_public_eoi = Solicitation.objects.create(
            title="Draft Public EOI",
            description="Test description",
            target_population="Test population",
            scope_of_work="Test scope", 
            solicitation_type=SolicitationType.EOI,
            status=SolicitationStatus.DRAFT,
            is_publicly_listed=True,
            program=program,
            created_by=user,
            application_deadline=date.today() + timedelta(days=30)
        )
        
        url = reverse('solicitations:list')
        response = client.get(url)
        
        assert response.status_code == 200
        assert active_public_eoi.title in response.content.decode()
        assert active_private_eoi.title not in response.content.decode()
        assert draft_public_eoi.title not in response.content.decode()

    def test_eoi_filter_view(self):
        program = ProgramFactory()
        user = UserFactory()
        client = Client()
        
        # Create EOI and RFP
        eoi = Solicitation.objects.create(
            title="Test EOI",
            description="Test description",
            target_population="Test population",
            scope_of_work="Test scope",
            solicitation_type=SolicitationType.EOI,
            status=SolicitationStatus.ACTIVE,
            is_publicly_listed=True,
            program=program,
            created_by=user,
            application_deadline=date.today() + timedelta(days=30)
        )
        
        rfp = Solicitation.objects.create(
            title="Test RFP", 
            description="Test description",
            target_population="Test population",
            scope_of_work="Test scope",
            solicitation_type=SolicitationType.RFP,
            status=SolicitationStatus.ACTIVE,
            is_publicly_listed=True,
            program=program,
            created_by=user,
            application_deadline=date.today() + timedelta(days=30)
        )
        
        # Test EOI filter
        url = reverse('solicitations:eoi_list')
        response = client.get(url)
        
        assert response.status_code == 200
        assert eoi.title in response.content.decode()
        assert rfp.title not in response.content.decode()

    def test_rfp_filter_view(self):
        program = ProgramFactory()
        user = UserFactory()
        client = Client()
        
        # Create EOI and RFP
        eoi = Solicitation.objects.create(
            title="Test EOI",
            description="Test description", 
            target_population="Test population",
            scope_of_work="Test scope",
            solicitation_type=SolicitationType.EOI,
            status=SolicitationStatus.ACTIVE,
            is_publicly_listed=True,
            program=program,
            created_by=user,
            application_deadline=date.today() + timedelta(days=30)
        )
        
        rfp = Solicitation.objects.create(
            title="Test RFP",
            description="Test description",
            target_population="Test population",
            scope_of_work="Test scope", 
            solicitation_type=SolicitationType.RFP,
            status=SolicitationStatus.ACTIVE,
            is_publicly_listed=True,
            program=program,
            created_by=user,
            application_deadline=date.today() + timedelta(days=30)
        )
        
        # Test RFP filter
        url = reverse('solicitations:rfp_list')
        response = client.get(url)
        
        assert response.status_code == 200
        assert rfp.title in response.content.decode()
        assert eoi.title not in response.content.decode()

    def test_search_functionality(self):
        program = ProgramFactory()
        user = UserFactory()
        client = Client()
        
        solicitation1 = Solicitation.objects.create(
            title="Child Health Campaign",
            description="Maternal and child health services",
            target_population="Children under 5",
            scope_of_work="Health screening",
            status=SolicitationStatus.ACTIVE,
            is_publicly_listed=True,
            program=program,
            created_by=user,
            application_deadline=date.today() + timedelta(days=30)
        )
        
        solicitation2 = Solicitation.objects.create(
            title="Nutrition Program",
            description="Adult nutrition services", 
            target_population="Adults",
            scope_of_work="Nutrition counseling",
            status=SolicitationStatus.ACTIVE,
            is_publicly_listed=True,
            program=program,
            created_by=user,
            application_deadline=date.today() + timedelta(days=30)
        )
        
        # Search for "child" should find solicitation1
        url = reverse('solicitations:list')
        response = client.get(url, {'search': 'child'})
        
        assert response.status_code == 200
        assert solicitation1.title in response.content.decode()
        assert solicitation2.title not in response.content.decode()


@pytest.mark.django_db
class TestPublicSolicitationDetailView:
    def test_detail_view_shows_active_solicitation(self):
        program = ProgramFactory()
        user = UserFactory()
        client = Client()
        
        solicitation = Solicitation.objects.create(
            title="Test Solicitation",
            description="Detailed description of the program",
            target_population="Test population",
            scope_of_work="Detailed scope of work",
            status=SolicitationStatus.ACTIVE,
            program=program,
            created_by=user,
            application_deadline=date.today() + timedelta(days=30)
        )
        
        url = reverse('solicitations:detail', kwargs={'pk': solicitation.pk})
        response = client.get(url)
        
        assert response.status_code == 200
        assert solicitation.title in response.content.decode()
        assert solicitation.description in response.content.decode()
        assert solicitation.scope_of_work in response.content.decode()

    def test_detail_view_shows_private_solicitation_via_direct_url(self):
        """Private solicitations should be accessible via direct URL"""
        program = ProgramFactory()
        user = UserFactory()
        client = Client()
        
        private_solicitation = Solicitation.objects.create(
            title="Private Solicitation",
            description="This is not publicly listed",
            target_population="Test population", 
            scope_of_work="Test scope",
            status=SolicitationStatus.ACTIVE,
            is_publicly_listed=False,
            program=program,
            created_by=user,
            application_deadline=date.today() + timedelta(days=30)
        )
        
        url = reverse('solicitations:detail', kwargs={'pk': private_solicitation.pk})
        response = client.get(url)
        
        assert response.status_code == 200
        assert private_solicitation.title in response.content.decode()

    def test_detail_view_404_for_draft_solicitation(self):
        """Draft solicitations should not be accessible even via direct URL"""
        program = ProgramFactory()
        user = UserFactory()
        client = Client()
        
        draft_solicitation = Solicitation.objects.create(
            title="Draft Solicitation",
            description="This is a draft",
            target_population="Test population",
            scope_of_work="Test scope",
            status=SolicitationStatus.DRAFT,
            program=program,
            created_by=user,
            application_deadline=date.today() + timedelta(days=30)
        )
        
        url = reverse('solicitations:detail', kwargs={'pk': draft_solicitation.pk})
        response = client.get(url)
        
        assert response.status_code == 404

