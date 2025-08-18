import pytest
from django.test import Client

from commcare_connect.solicitations.models import QuestionType, SolicitationQuestion
from commcare_connect.solicitations.tests.factories import SolicitationFactory
from commcare_connect.users.tests.factories import OrganizationFactory, UserFactory


@pytest.fixture
def user_with_org(db):
    """User with organization membership - commonly needed for solicitation responses"""
    user = UserFactory()
    org = OrganizationFactory()
    user.memberships.create(organization=org)
    return user


@pytest.fixture
def solicitation_with_questions(db):
    """Standard solicitation with common question types for testing forms"""
    solicitation = SolicitationFactory()

    # Add standard questions that are commonly used in tests
    questions = [
        {
            "question_text": "Describe your organization's relevant experience",
            "question_type": QuestionType.TEXTAREA,
            "is_required": True,
            "order": 1,
        },
        {
            "question_text": "How many staff can you deploy?",
            "question_type": QuestionType.NUMBER,
            "is_required": True,
            "order": 2,
        },
        {
            "question_text": "What is your organization name?",
            "question_type": QuestionType.TEXT,
            "is_required": False,
            "order": 3,
        },
        {
            "question_text": "Upload your organization registration",
            "question_type": QuestionType.FILE,
            "is_required": False,
            "order": 4,
        },
    ]

    for question_data in questions:
        SolicitationQuestion.objects.create(solicitation=solicitation, **question_data)

    return solicitation


@pytest.fixture
def solicitation_basic(db):
    """Basic solicitation without questions for simple tests"""
    return SolicitationFactory()


@pytest.fixture
def authenticated_client(user_with_org):
    """Client with authenticated user that has organization membership"""
    client = Client()
    client.force_login(user_with_org)
    return client


@pytest.fixture
def anonymous_client():
    """Anonymous client for testing public views"""
    return Client()
