from datetime import date, timedelta

import pytest
from django.db import IntegrityError

from commcare_connect.solicitations.models import (
    ResponseStatus,
    SolicitationQuestion,
    SolicitationResponse,
    SolicitationStatus,
)
from commcare_connect.solicitations.tests.factories import SolicitationFactory, SolicitationResponseFactory


class BaseSolicitationModelTest:
    """Base class for solicitation model tests with common fixtures"""

    @pytest.fixture(autouse=True)
    def setup(self, solicitation_basic, user_with_org):
        self.solicitation = solicitation_basic
        self.user = user_with_org
        self.org = self.user.memberships.first().organization


@pytest.mark.django_db
class TestSolicitation(BaseSolicitationModelTest):
    def test_publicly_visible_property(self):
        """Test that solicitations are only publicly visible when active AND publicly listed"""
        # Active and publicly listed
        active_public = SolicitationFactory(
            status=SolicitationStatus.ACTIVE,
            is_publicly_listed=True,
        )

        # Active but not publicly listed
        active_private = SolicitationFactory(
            status=SolicitationStatus.ACTIVE,
            is_publicly_listed=False,
        )

        # Draft and publicly listed
        draft_public = SolicitationFactory(
            status=SolicitationStatus.DRAFT,
            is_publicly_listed=True,
        )

        assert active_public.is_publicly_visible
        assert not active_private.is_publicly_visible
        assert not draft_public.is_publicly_visible

    def test_can_accept_responses(self):
        """Test that solicitations can only accept responses when active with future deadline"""
        # Active with future deadline
        active_future = SolicitationFactory(
            status=SolicitationStatus.ACTIVE,
            application_deadline=date.today() + timedelta(days=30),
        )

        # Active with past deadline
        active_past = SolicitationFactory(
            status=SolicitationStatus.ACTIVE,
            application_deadline=date.today() - timedelta(days=1),
        )

        # Draft with future deadline
        draft_future = SolicitationFactory(
            status=SolicitationStatus.DRAFT,
            application_deadline=date.today() + timedelta(days=30),
        )

        assert active_future.can_accept_responses
        assert not active_past.can_accept_responses
        assert not draft_future.can_accept_responses


@pytest.mark.django_db
class TestSolicitationQuestion(BaseSolicitationModelTest):
    def test_question_ordering(self):
        """Test that questions are ordered by their order field"""
        # Create questions in reverse order
        question3 = SolicitationQuestion.objects.create(
            solicitation=self.solicitation, question_text="Third question", order=3
        )
        question1 = SolicitationQuestion.objects.create(
            solicitation=self.solicitation, question_text="First question", order=1
        )
        question2 = SolicitationQuestion.objects.create(
            solicitation=self.solicitation, question_text="Second question", order=2
        )

        # Should be ordered by order field
        questions = list(self.solicitation.questions.all())
        assert questions[0] == question1
        assert questions[1] == question2
        assert questions[2] == question3


@pytest.mark.django_db
class TestSolicitationResponse(BaseSolicitationModelTest):
    def test_response_defaults_to_draft_status(self):
        """Test that newly created responses default to DRAFT status"""
        response = SolicitationResponse.objects.create(
            solicitation=self.solicitation,
            organization=self.org,
            submitted_by=self.user,
            responses={"question_1": "Our response"},
        )

        assert response.status == ResponseStatus.DRAFT

    def test_unique_response_per_org(self):
        """Test that organizations can only submit one response per solicitation"""
        # First response should succeed
        SolicitationResponse.objects.create(
            solicitation=self.solicitation,
            organization=self.org,
            submitted_by=self.user,
            responses={"question_1": "First response"},
        )

        # Second response from same org should fail
        with pytest.raises(IntegrityError):
            SolicitationResponse.objects.create(
                solicitation=self.solicitation,
                organization=self.org,
                submitted_by=self.user,
                responses={"question_1": "Second response"},
            )

    def test_submit_method(self):
        """Test that submit() method changes status from DRAFT to SUBMITTED"""
        # Create a draft response
        response = SolicitationResponseFactory(
            solicitation=self.solicitation, organization=self.org, submitted_by=self.user, status=ResponseStatus.DRAFT
        )
        assert response.is_draft
        assert not response.is_submitted

        # Submit it
        response.submit()
        response.refresh_from_db()

        assert not response.is_draft
        assert response.is_submitted
        assert response.status == ResponseStatus.SUBMITTED

    def test_submit_method_only_works_on_drafts(self):
        """Test that submit() method only works on draft responses"""
        # Create an already submitted response
        response = SolicitationResponseFactory(
            solicitation=self.solicitation,
            organization=self.org,
            submitted_by=self.user,
            status=ResponseStatus.SUBMITTED,
        )
        original_status = response.status

        # Try to submit it again - should not change
        response.submit()
        response.refresh_from_db()

        assert response.status == original_status
