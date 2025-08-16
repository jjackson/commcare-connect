from datetime import date, timedelta

import pytest

from commcare_connect.program.tests.factories import ProgramFactory
from commcare_connect.solicitations.models import (
    Solicitation,
    SolicitationQuestion,
    SolicitationResponse,
    SolicitationStatus,
    SolicitationType,
)
from commcare_connect.users.tests.factories import OrganizationFactory, UserFactory


@pytest.mark.django_db
class TestSolicitation:
    def test_solicitation_creation(self):
        program = ProgramFactory()
        user = UserFactory()

        solicitation = Solicitation.objects.create(
            title="Test EOI",
            description="Test description",
            target_population="Children under 5",
            scope_of_work="Test scope",
            solicitation_type=SolicitationType.EOI,
            status=SolicitationStatus.ACTIVE,
            program=program,
            created_by=user,
            application_deadline=date.today() + timedelta(days=30),
        )

        assert solicitation.title == "Test EOI"
        assert solicitation.solicitation_type == SolicitationType.EOI
        assert solicitation.is_active
        assert solicitation.can_accept_responses

    def test_string_representation(self):
        program = ProgramFactory()
        user = UserFactory()

        solicitation = Solicitation.objects.create(
            title="Test RFP",
            description="Test description",
            target_population="Test population",
            scope_of_work="Test scope",
            solicitation_type=SolicitationType.RFP,
            program=program,
            created_by=user,
            application_deadline=date.today() + timedelta(days=30),
        )

        expected = "Request for Proposal: Test RFP"
        assert str(solicitation) == expected

    def test_publicly_visible_property(self):
        program = ProgramFactory()
        user = UserFactory()

        # Active and publicly listed
        solicitation1 = Solicitation.objects.create(
            title="Public Active",
            description="Test",
            target_population="Test",
            scope_of_work="Test",
            status=SolicitationStatus.ACTIVE,
            is_publicly_listed=True,
            program=program,
            created_by=user,
            application_deadline=date.today() + timedelta(days=30),
        )

        # Active but not publicly listed
        solicitation2 = Solicitation.objects.create(
            title="Private Active",
            description="Test",
            target_population="Test",
            scope_of_work="Test",
            status=SolicitationStatus.ACTIVE,
            is_publicly_listed=False,
            program=program,
            created_by=user,
            application_deadline=date.today() + timedelta(days=30),
        )

        # Draft and publicly listed
        solicitation3 = Solicitation.objects.create(
            title="Public Draft",
            description="Test",
            target_population="Test",
            scope_of_work="Test",
            status=SolicitationStatus.DRAFT,
            is_publicly_listed=True,
            program=program,
            created_by=user,
            application_deadline=date.today() + timedelta(days=30),
        )

        assert solicitation1.is_publicly_visible
        assert not solicitation2.is_publicly_visible
        assert not solicitation3.is_publicly_visible

    def test_can_accept_responses(self):
        program = ProgramFactory()
        user = UserFactory()

        # Active with future deadline
        solicitation1 = Solicitation.objects.create(
            title="Future Deadline",
            description="Test",
            target_population="Test",
            scope_of_work="Test",
            status=SolicitationStatus.ACTIVE,
            program=program,
            created_by=user,
            application_deadline=date.today() + timedelta(days=30),
        )

        # Active with past deadline
        solicitation2 = Solicitation.objects.create(
            title="Past Deadline",
            description="Test",
            target_population="Test",
            scope_of_work="Test",
            status=SolicitationStatus.ACTIVE,
            program=program,
            created_by=user,
            application_deadline=date.today() - timedelta(days=1),
        )

        # Draft with future deadline
        solicitation3 = Solicitation.objects.create(
            title="Draft Future",
            description="Test",
            target_population="Test",
            scope_of_work="Test",
            status=SolicitationStatus.DRAFT,
            program=program,
            created_by=user,
            application_deadline=date.today() + timedelta(days=30),
        )

        assert solicitation1.can_accept_responses
        assert not solicitation2.can_accept_responses
        assert not solicitation3.can_accept_responses


@pytest.mark.django_db
class TestSolicitationQuestion:
    def test_question_creation(self):
        program = ProgramFactory()
        user = UserFactory()

        solicitation = Solicitation.objects.create(
            title="Test EOI",
            description="Test",
            target_population="Test",
            scope_of_work="Test",
            program=program,
            created_by=user,
            application_deadline=date.today() + timedelta(days=30),
        )

        question = SolicitationQuestion.objects.create(
            solicitation=solicitation,
            question_text="What is your experience?",
            question_type="textarea",
            is_required=True,
            order=1,
        )

        assert question.question_text == "What is your experience?"
        assert question.is_required
        assert question.order == 1

    def test_question_ordering(self):
        program = ProgramFactory()
        user = UserFactory()

        solicitation = Solicitation.objects.create(
            title="Test EOI",
            description="Test",
            target_population="Test",
            scope_of_work="Test",
            program=program,
            created_by=user,
            application_deadline=date.today() + timedelta(days=30),
        )

        # Create questions in reverse order
        question3 = SolicitationQuestion.objects.create(
            solicitation=solicitation, question_text="Third question", order=3
        )
        question1 = SolicitationQuestion.objects.create(
            solicitation=solicitation, question_text="First question", order=1
        )
        question2 = SolicitationQuestion.objects.create(
            solicitation=solicitation, question_text="Second question", order=2
        )

        # Should be ordered by order field
        questions = list(solicitation.questions.all())
        assert questions[0] == question1
        assert questions[1] == question2
        assert questions[2] == question3


@pytest.mark.django_db
class TestSolicitationResponse:
    def test_response_creation(self):
        program = ProgramFactory()
        user = UserFactory()
        org = OrganizationFactory()

        solicitation = Solicitation.objects.create(
            title="Test EOI",
            description="Test",
            target_population="Test",
            scope_of_work="Test",
            program=program,
            created_by=user,
            application_deadline=date.today() + timedelta(days=30),
        )

        response = SolicitationResponse.objects.create(
            solicitation=solicitation, organization=org, submitted_by=user, responses={"question_1": "Our response"}
        )

        assert response.solicitation == solicitation
        assert response.organization == org
        assert response.submitted_by == user
        assert response.responses == {"question_1": "Our response"}
        assert response.status == "submitted"

    def test_unique_response_per_org(self):
        program = ProgramFactory()
        user = UserFactory()
        org = OrganizationFactory()

        solicitation = Solicitation.objects.create(
            title="Test EOI",
            description="Test",
            target_population="Test",
            scope_of_work="Test",
            program=program,
            created_by=user,
            application_deadline=date.today() + timedelta(days=30),
        )

        # First response should succeed
        SolicitationResponse.objects.create(
            solicitation=solicitation, organization=org, submitted_by=user, responses={"question_1": "First response"}
        )

        # Second response from same org should fail
        with pytest.raises(Exception):  # Django will raise IntegrityError
            SolicitationResponse.objects.create(
                solicitation=solicitation,
                organization=org,
                submitted_by=user,
                responses={"question_1": "Second response"},
            )
