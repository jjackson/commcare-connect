"""
Tests for experiment helper functions.

Minimal focused tests for critical functionality.
"""

import pytest

from commcare_connect.organization.models import Organization
from commcare_connect.program.models import Program
from commcare_connect.solicitations.helpers import (
    create_response_record,
    create_review_record,
    create_solicitation_record,
    get_response_for_solicitation,
    get_solicitations,
)
from commcare_connect.users.models import User


@pytest.mark.django_db
class TestExperimentHelpers:
    """Test experiment helper functions."""

    def test_create_solicitation_record(self):
        """Test creating a solicitation record."""
        # Create test data
        org = Organization.objects.create(name="Test Org", slug="test-org")
        program = Program.objects.create(name="Test Program", organization=org)

        # Create solicitation
        data = {
            "title": "Test Solicitation",
            "description": "Test description",
            "solicitation_type": "eoi",
            "status": "active",
            "questions": [{"id": 1, "text": "Question 1", "type": "text", "required": True}],
            "application_deadline": "2025-12-31",
        }

        record = create_solicitation_record(program, data)

        assert record.id is not None
        assert record.experiment == "solicitations"
        assert record.type == "Solicitation"
        assert record.program == program
        assert record.data["title"] == "Test Solicitation"
        assert len(record.data["questions"]) == 1

    def test_get_solicitations(self):
        """Test querying solicitations."""
        org = Organization.objects.create(name="Test Org", slug="test-org")
        program = Program.objects.create(name="Test Program", organization=org)

        # Create active and closed solicitations
        create_solicitation_record(program, {"title": "Active EOI", "solicitation_type": "eoi", "status": "active"})
        create_solicitation_record(program, {"title": "Closed EOI", "solicitation_type": "eoi", "status": "closed"})
        create_solicitation_record(program, {"title": "Active RFP", "solicitation_type": "rfp", "status": "active"})

        # Test basic query
        all_sols = get_solicitations()
        assert all_sols.count() == 3

        # Test status filter
        active_sols = get_solicitations(status="active")
        assert active_sols.count() == 2

        # Test type filter
        eoi_sols = get_solicitations(solicitation_type="eoi")
        assert eoi_sols.count() == 2

        # Test combined filters
        active_eois = get_solicitations(status="active", solicitation_type="eoi")
        assert active_eois.count() == 1

    def test_create_and_query_response(self):
        """Test creating and querying responses."""
        org = Organization.objects.create(name="Test Org", slug="test-org")
        program = Program.objects.create(name="Test Program", organization=org)
        user = User.objects.create(username="testuser", email="test@example.com")

        # Create solicitation
        solicitation = create_solicitation_record(
            program, {"title": "Test Solicitation", "status": "active", "solicitation_type": "eoi"}
        )

        # Create response
        response_data = {"status": "draft", "responses": {"question_1": "Answer 1"}, "attachments": []}

        response = create_response_record(solicitation, org, user, response_data)

        assert response.id is not None
        assert response.experiment == "solicitations"
        assert response.type == "SolicitationResponse"
        assert response.parent == solicitation
        assert response.organization == org
        assert response.user == user

        # Test querying
        found_response = get_response_for_solicitation(solicitation, org)
        assert found_response.id == response.id

    def test_create_review(self):
        """Test creating a review."""
        org = Organization.objects.create(name="Test Org", slug="test-org")
        program = Program.objects.create(name="Test Program", organization=org)
        user = User.objects.create(username="testuser", email="test@example.com")
        reviewer = User.objects.create(username="reviewer", email="reviewer@example.com")

        # Create solicitation and response
        solicitation = create_solicitation_record(program, {"title": "Test", "status": "active"})
        response = create_response_record(solicitation, org, user, {"status": "submitted", "responses": {}})

        # Create review
        review_data = {"score": 85, "recommendation": "recommended", "notes": "Good response"}

        review = create_review_record(response, reviewer, review_data)

        assert review.id is not None
        assert review.experiment == "solicitations"
        assert review.type == "SolicitationReview"
        assert review.parent == response
        assert review.user == reviewer
        assert review.data["score"] == 85
