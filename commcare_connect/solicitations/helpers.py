"""
Helper functions for the solicitations app.

This module contains business logic functions extracted from views to improve
code quality, testability, and maintainability. Following the established
pattern from opportunity/helpers.py.
"""

from django.db.models import Count, Q
from django.utils import timezone

from .models import ResponseStatus, SolicitationQuestion, SolicitationResponse


def get_solicitation_response_statistics(queryset):
    """
    Add response statistics annotations to a solicitation queryset.

    This helper extracts the complex query annotations that were duplicated
    across AdminSolicitationOverview and ProgramSolicitationDashboard.

    Args:
        queryset: A Solicitation queryset to annotate

    Returns:
        Annotated queryset with response count fields
    """
    return queryset.annotate(
        total_responses=Count("responses", filter=~Q(responses__status="draft")),
        under_review_count=Count("responses", filter=Q(responses__status="under_review")),
        accepted_count=Count("responses", filter=Q(responses__status="accepted")),
        rejected_count=Count("responses", filter=Q(responses__status="rejected")),
        submitted_count=Count("responses", filter=Q(responses__status="submitted")),
    )


def get_user_organization_context(user):
    """
    Get organization context for a user.

    This helper extracts repeated org membership logic used across multiple views.

    Args:
        user: User instance

    Returns:
        dict with organization context or None if no membership
    """
    if not user.memberships.exists():
        return None

    membership = user.memberships.first()
    return {"organization": membership.organization, "membership": membership, "has_organization": True}


def calculate_response_permissions(user, solicitation):
    """
    Calculate response permissions for a user and solicitation.

    This helper extracts the complex permission checking logic from
    SolicitationResponseCreateView.dispatch() method.

    Args:
        user: User instance
        solicitation: Solicitation instance

    Returns:
        dict with permission results and context
    """
    result = {
        "can_respond": False,
        "error_message": None,
        "redirect_needed": False,
        "existing_draft": None,
        "existing_submitted_response": None,
    }

    # Check if solicitation accepts responses
    if not solicitation.can_accept_responses:
        result["error_message"] = "This solicitation is not currently accepting responses."
        result["redirect_needed"] = True
        return result

    # Check if user has organization membership
    org_context = get_user_organization_context(user)
    if not org_context:
        result["error_message"] = "organization_required"
        return result

    user_org = org_context["organization"]

    # Check if organization already submitted a response (not draft)
    existing_submitted_response = SolicitationResponse.objects.filter(
        solicitation=solicitation,
        organization=user_org,
        status__in=[
            ResponseStatus.SUBMITTED,
            ResponseStatus.UNDER_REVIEW,
            ResponseStatus.ACCEPTED,
            ResponseStatus.REJECTED,
        ],
    ).first()

    if existing_submitted_response:
        result["existing_submitted_response"] = existing_submitted_response
        result["error_message"] = (
            f"Your organization has already submitted a response on "
            f"{existing_submitted_response.submission_date.strftime('%B %d, %Y')}."
        )
        result["redirect_needed"] = True
        return result

    # Check if there's an existing draft
    existing_draft = SolicitationResponse.objects.filter(
        solicitation=solicitation,
        organization=user_org,
        status=ResponseStatus.DRAFT,
    ).first()

    result["can_respond"] = True
    result["existing_draft"] = existing_draft
    return result


def get_deadline_status_context(solicitation):
    """
    Get deadline status and formatting context for a solicitation.

    Args:
        solicitation: Solicitation instance

    Returns:
        dict with deadline context
    """
    now = timezone.now().date()
    deadline = solicitation.application_deadline

    context = {
        "deadline": deadline,
        "deadline_formatted": deadline.strftime("%B %d, %Y") if deadline else None,
        "is_past_deadline": deadline < now if deadline else False,
        "days_until_deadline": (deadline - now).days if deadline and deadline >= now else None,
    }

    # Add status indicators
    if context["is_past_deadline"]:
        context["deadline_status"] = "expired"
        context["deadline_class"] = "text-red-600"
    elif context["days_until_deadline"] is not None:
        if context["days_until_deadline"] <= 3:
            context["deadline_status"] = "urgent"
            context["deadline_class"] = "text-orange-600"
        elif context["days_until_deadline"] <= 7:
            context["deadline_status"] = "soon"
            context["deadline_class"] = "text-yellow-600"
        else:
            context["deadline_status"] = "open"
            context["deadline_class"] = "text-green-600"
    else:
        context["deadline_status"] = "unknown"
        context["deadline_class"] = "text-gray-600"

    return context


def process_question_form_data(cleaned_data, is_draft_save=False):
    """
    Process question form data from SolicitationResponseForm.

    This helper extracts the JSON processing and validation logic from
    the form's save() method.

    Args:
        cleaned_data: Form's cleaned_data dict
        is_draft_save: Whether this is a draft save or final submission

    Returns:
        dict with processed responses data
    """
    responses_data = {}

    for field_name, value in cleaned_data.items():
        if field_name.startswith("question_"):
            question_id = field_name.split("_")[1]
            try:
                question = SolicitationQuestion.objects.get(id=question_id)
                # For drafts, save all values (including empty ones to preserve user's clearing of fields)
                # For submissions, only save non-empty values
                if is_draft_save:
                    responses_data[question.question_text] = value
                elif value:  # For submission, only save non-empty values
                    responses_data[question.question_text] = value
            except SolicitationQuestion.DoesNotExist:
                continue

    return responses_data


def get_existing_response_for_organization(solicitation, organization, include_drafts=True):
    """
    Get existing response for an organization to a solicitation.

    Args:
        solicitation: Solicitation instance
        organization: Organization instance
        include_drafts: Whether to include draft responses

    Returns:
        SolicitationResponse instance or None
    """
    queryset = SolicitationResponse.objects.filter(
        solicitation=solicitation,
        organization=organization,
    )

    if not include_drafts:
        queryset = queryset.exclude(status=ResponseStatus.DRAFT)

    return queryset.first()


def validate_solicitation_response_eligibility(user, solicitation):
    """
    Validate if a user is eligible to respond to a solicitation.

    Consolidates eligibility checks used across multiple views.

    Args:
        user: User instance
        solicitation: Solicitation instance

    Returns:
        dict with eligibility results
    """
    result = {"is_eligible": False, "reasons": []}

    # Check authentication
    if not user.is_authenticated:
        result["reasons"].append("User must be authenticated")
        return result

    # Check organization membership
    org_context = get_user_organization_context(user)
    if not org_context:
        result["reasons"].append("User must be a member of an organization")
        return result

    # Check solicitation status
    if not solicitation.can_accept_responses:
        result["reasons"].append("Solicitation is not currently accepting responses")
        return result

    # Check for existing submission
    existing_response = get_existing_response_for_organization(
        solicitation, org_context["organization"], include_drafts=False
    )
    if existing_response:
        result["reasons"].append("Organization has already submitted a response")
        return result

    result["is_eligible"] = True
    return result


def get_solicitation_dashboard_statistics(solicitations_queryset):
    """
    Calculate dashboard statistics for a set of solicitations.

    Used by both AdminSolicitationOverview and ProgramSolicitationDashboard
    to generate summary statistics.

    Args:
        solicitations_queryset: Queryset of solicitations

    Returns:
        dict with statistics
    """
    stats = {
        "total_solicitations": solicitations_queryset.count(),
        "active_eois": solicitations_queryset.filter(solicitation_type="eoi", status="active").count(),
        "active_rfps": solicitations_queryset.filter(solicitation_type="rfp", status="active").count(),
        "total_responses": 0,
    }

    # Calculate total responses across all solicitations
    annotated_solicitations = get_solicitation_response_statistics(solicitations_queryset)
    stats["total_responses"] = sum(s.total_responses or 0 for s in annotated_solicitations)

    return stats


def process_solicitation_questions(questions_data_json, solicitation):
    """
    Process question form data for solicitation creation/editing.

    Extracts the complex question processing logic from SolicitationCreateView
    and SolicitationUpdateView.

    Args:
        questions_data_json: JSON string containing questions data from form
        solicitation: Solicitation instance to associate questions with

    Returns:
        tuple: (success: bool, error_message: str or None)
    """
    import json

    if not questions_data_json:
        return True, None

    try:
        questions = json.loads(questions_data_json)

        # Validate questions data structure
        validation_result = validate_question_structure(questions)
        if not validation_result[0]:
            return validation_result

        # Create question objects
        for question_data in questions:
            SolicitationQuestion.objects.create(
                solicitation=solicitation,
                question_text=question_data.get("question_text", ""),
                question_type=question_data.get("question_type", "textarea"),
                is_required=question_data.get("is_required", True),
                options=question_data.get("options", None),
                order=question_data.get("order", 1),
            )

        return True, None

    except json.JSONDecodeError:
        return False, "Invalid questions data format"
    except Exception as e:
        return False, f"Error processing questions: {str(e)}"


def validate_question_structure(questions_data):
    """
    Validate question data structure and requirements.

    Args:
        questions_data: List of question dictionaries

    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    if not isinstance(questions_data, list):
        return False, "Questions data must be a list"

    required_fields = ["question_text", "question_type"]
    valid_question_types = ["textarea", "text", "select", "multiselect", "number", "date"]

    for i, question in enumerate(questions_data):
        if not isinstance(question, dict):
            return False, f"Question {i+1} must be a dictionary"

        # Check required fields
        for field in required_fields:
            if field not in question or not question[field]:
                return False, f"Question {i+1} is missing required field: {field}"

        # Validate question type
        if question["question_type"] not in valid_question_types:
            return False, f"Question {i+1} has invalid question type: {question['question_type']}"

        # Validate options for select/multiselect questions
        if question["question_type"] in ["select", "multiselect"]:
            options = question.get("options")
            if not options:
                return False, f"Question {i+1} of type {question['question_type']} requires options"

    return True, None


def build_question_context(solicitation, is_edit=False):
    """
    Build question context for template rendering.

    Args:
        solicitation: Solicitation instance (None for create mode)
        is_edit: Whether this is edit mode

    Returns:
        dict with question context
    """
    import json

    if is_edit and solicitation:
        # Load existing questions for editing
        existing_questions = list(
            solicitation.questions.all()
            .order_by("order")
            .values("id", "question_text", "question_type", "is_required", "options", "order")
        )
        return {
            "existing_questions": json.dumps(existing_questions),
            "is_create": False,
        }
    else:
        # No questions for new solicitations
        return {
            "existing_questions": json.dumps([]),
            "is_create": True,
        }


def update_solicitation_questions(questions_data_json, solicitation):
    """
    Update questions for an existing solicitation.

    This handles the more complex case of updating existing questions,
    which may involve deleting old questions and creating new ones.

    Args:
        questions_data_json: JSON string containing questions data from form
        solicitation: Solicitation instance to update questions for

    Returns:
        tuple: (success: bool, error_message: str or None)
    """
    import json

    if not questions_data_json:
        return True, None

    try:
        questions = json.loads(questions_data_json)

        # Validate questions data structure
        validation_result = validate_question_structure(questions)
        if not validation_result[0]:
            return validation_result

        # Delete existing questions and create new ones
        # This is simpler than trying to update in place
        solicitation.questions.all().delete()

        # Create new question objects
        for question_data in questions:
            SolicitationQuestion.objects.create(
                solicitation=solicitation,
                question_text=question_data.get("question_text", ""),
                question_type=question_data.get("question_type", "textarea"),
                is_required=question_data.get("is_required", True),
                options=question_data.get("options", None),
                order=question_data.get("order", 1),
            )

        return True, None

    except json.JSONDecodeError:
        return False, "Invalid questions data format"
    except Exception as e:
        return False, f"Error updating questions: {str(e)}"
