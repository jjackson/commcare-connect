import json
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DetailView, ListView, TemplateView, UpdateView
from django_tables2 import SingleTableView

from commcare_connect.labs.config import LABS_DEFAULT_OPP_ID as SOLICITATION_DEFAULT_OPPORTUNITY_ID

from .data_access import SolicitationDataAccess
from .forms import SolicitationForm, SolicitationResponseForm, SolicitationReviewForm
from .models import ResponseRecord, ReviewRecord, SolicitationRecord

# =============================================================================
# Permission Mixins (following established patterns)
# =============================================================================


class SolicitationAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Handles organization membership requirements for solicitation access.

    Following the OrganizationUserMixin pattern from opportunity/views.py.
    Users must have organization membership to access solicitation features.
    """

    def test_func(self):
        # Follow OrganizationUserMixin pattern exactly
        return self.request.org_membership != None or self.request.user.is_superuser  # noqa: E711


class SolicitationManagerMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Handles program manager permissions for solicitation management.

    Following the ProgramManagerMixin pattern from program/views.py exactly.
    Users must be organization admins with program manager role.
    """

    def test_func(self):
        # Follow ProgramManagerMixin pattern exactly
        org_membership = getattr(self.request, "org_membership", None)
        is_admin = getattr(org_membership, "is_admin", False)
        org = getattr(self.request, "org", None)
        program_manager = getattr(org, "program_manager", False)
        return (org_membership is not None and is_admin and program_manager) or self.request.user.is_superuser


class SolicitationResponseViewAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Handles access permissions for viewing solicitation responses.
    Simplified for labs - superuser gets access (since LabsUser is always superuser).
    """

    def test_func(self):
        # For labs, LabsUser is superuser so this will pass
        return self.request.user.is_superuser


# =============================================================================
# Data Access Helper Function
# =============================================================================
# Note: Following audit/tasks pattern - instantiate directly in views rather
# than using a mixin. This is simpler and more explicit.


# =============================================================================
# Custom Decorators (following established patterns from opportunity/program apps)
# =============================================================================
def solicitation_access_required(view_func):
    """
    Decorator equivalent of SolicitationAccessMixin for function-based views.
    Ensures user has organization membership (following established patterns).
    """
    from functools import wraps

    from django.core.exceptions import PermissionDenied

    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Follow SolicitationAccessMixin logic exactly
        if not (getattr(request, "org_membership", None) or request.user.is_superuser):
            raise PermissionDenied("Organization membership required")
        return view_func(request, *args, **kwargs)

    return wrapper


# =============================================================================
# Admin Overview Views - REPLACED BY UnifiedSolicitationDashboard
# =============================================================================

# AdminSolicitationOverview, ProgramSolicitationDashboard, and UserSolicitationDashboard
# have been consolidated into UnifiedSolicitationDashboard (see bottom of file)


# =============================================================================
# New LocalLabsRecord-based Views
# =============================================================================


class LabsHomeView(TemplateView):
    """
    Landing page for the solicitations lab explaining the project and providing navigation.
    """

    template_name = "solicitations/labs_home.html"


class ProgramSelectView(TemplateView):
    """
    View for program managers to select which program they want to create a solicitation for.
    """

    template_name = "solicitations/program_select.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get programs from OAuth session data
        if hasattr(self.request.user, "programs"):
            context["programs"] = self.request.user.programs
        else:
            context["programs"] = []
        return context


class ManageSolicitationsListView(ListView):
    """
    List view of solicitations created by the current user.
    """

    model = SolicitationRecord
    template_name = "solicitations/manage_list.html"
    context_object_name = "solicitations"
    paginate_by = 20

    def get_queryset(self):
        # Use data access layer to filter by user's username
        data_access = SolicitationDataAccess(opportunity_id=SOLICITATION_DEFAULT_OPPORTUNITY_ID, request=self.request)
        return data_access.get_solicitations()


class MyResponsesListView(ListView):
    """
    List view of responses created by the current user's organization.
    """

    model = ResponseRecord
    template_name = "solicitations/my_responses.html"
    context_object_name = "responses"
    paginate_by = 20

    def get_queryset(self):
        data_access = SolicitationDataAccess(opportunity_id=SOLICITATION_DEFAULT_OPPORTUNITY_ID, request=self.request)

        # Get user's organization slugs from OAuth data
        org_slugs = []
        if hasattr(self.request.user, "organizations") and self.request.user.organizations:
            org_slugs = [org.get("slug") for org in self.request.user.organizations if org.get("slug")]

        if org_slugs:
            # Get responses for all user's organizations
            all_responses = []
            for org_slug in org_slugs:
                responses = data_access.get_responses_for_organization(organization_id=org_slug)
                all_responses.extend(responses)
            return all_responses
        return []


class SolicitationResponsesListView(SingleTableView):
    """
    List view of all responses to a specific solicitation (for solicitation authors).
    Uses django-tables2 for display.
    """

    model = ResponseRecord
    template_name = "solicitations/solicitation_responses.html"
    context_object_name = "responses"
    paginate_by = 20

    def dispatch(self, request, *args, **kwargs):
        # Store data_access as instance variable for use in multiple methods
        self.data_access = SolicitationDataAccess(opportunity_id=SOLICITATION_DEFAULT_OPPORTUNITY_ID, request=request)

        # Get the solicitation
        solicitation_pk = self.kwargs.get("solicitation_pk")
        self.solicitation = self.data_access.get_solicitation_by_id(solicitation_pk)

        if not self.solicitation:
            raise Http404("Solicitation not found")

        # Check if user created this solicitation
        if self.solicitation.username != request.user.username:
            raise Http404("You can only view responses to your own solicitations")

        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return self.data_access.get_responses_for_solicitation(solicitation_record=self.solicitation)

    def get_table_class(self):
        from .tables import ResponseRecordTable

        return ResponseRecordTable

    def get_table_kwargs(self):
        """Pass data_access to table for API queries."""
        kwargs = super().get_table_kwargs()
        kwargs["data_access"] = self.data_access
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["solicitation"] = self.solicitation
        return context


class SolicitationListView(ListView):
    """
    Public list view of all publicly listed solicitations using LocalLabsRecords.
    """

    model = SolicitationRecord
    template_name = "solicitations/solicitation_list.html"
    context_object_name = "solicitations"
    paginate_by = 12

    def get_queryset(self):
        data_access = SolicitationDataAccess(opportunity_id=SOLICITATION_DEFAULT_OPPORTUNITY_ID, request=self.request)
        solicitation_type = self.kwargs.get("type")
        filters = {"status": "active", "is_publicly_listed": True}
        if solicitation_type:
            filters["solicitation_type"] = solicitation_type
        return data_access.get_solicitations(**filters)

    def get_context_data(self, **kwargs):
        data_access = SolicitationDataAccess(opportunity_id=SOLICITATION_DEFAULT_OPPORTUNITY_ID, request=self.request)
        context = super().get_context_data(**kwargs)
        context["current_type"] = self.kwargs.get("type", "all")
        context["total_active"] = len(data_access.get_solicitations(status="active", is_publicly_listed=True))
        context["eoi_count"] = len(
            data_access.get_solicitations(status="active", is_publicly_listed=True, solicitation_type="eoi")
        )
        context["rfp_count"] = len(
            data_access.get_solicitations(status="active", is_publicly_listed=True, solicitation_type="rfp")
        )
        return context


class SolicitationDetailView(DetailView):
    """
    Public detail view of a specific solicitation using LocalLabsRecords.
    """

    model = SolicitationRecord
    template_name = "solicitations/solicitation_detail.html"
    context_object_name = "solicitation"

    def get_object(self, queryset=None):
        data_access = SolicitationDataAccess(opportunity_id=SOLICITATION_DEFAULT_OPPORTUNITY_ID, request=self.request)
        pk = self.kwargs.get("pk")
        solicitations = data_access.get_solicitations(status="active")
        for sol in solicitations:
            if sol.id == pk:
                return sol
        raise Http404("Solicitation not found")

    def get_context_data(self, **kwargs):
        data_access = SolicitationDataAccess(opportunity_id=SOLICITATION_DEFAULT_OPPORTUNITY_ID, request=self.request)
        context = super().get_context_data(**kwargs)
        solicitation = self.object
        today = timezone.now().date()

        # Add deadline information
        if solicitation.application_deadline:
            from datetime import datetime

            if isinstance(solicitation.application_deadline, str):
                deadline = datetime.fromisoformat(solicitation.application_deadline).date()
            else:
                deadline = solicitation.application_deadline
            days_remaining = (deadline - today).days
            context["days_remaining"] = max(0, days_remaining)
            context["deadline_passed"] = days_remaining < 0

        # Add questions
        context["questions"] = solicitation.questions

        # Check for existing response if user is authenticated
        context["has_draft"] = False
        context["has_submitted_response"] = False

        if self.request.user.is_authenticated and self.request.user.memberships.exists():
            user_org = self.request.user.memberships.first().organization

            # Check for draft
            draft = data_access.get_response_for_solicitation(
                solicitation_record=solicitation, organization_id=user_org.slug, status="draft"
            )
            if draft:
                context["has_draft"] = True
                context["draft"] = draft

            # Check for submitted response
            submitted = data_access.get_response_for_solicitation(
                solicitation_record=solicitation, organization_id=user_org.slug, status="submitted"
            )
            if submitted:
                context["has_submitted_response"] = True
                context["submitted_response"] = submitted

        return context


class SolicitationResponseCreateOrUpdate(SolicitationAccessMixin, UpdateView):
    """
    Create or update a solicitation response using LocalLabsRecords.
    Simplified version that works directly with JSON data.
    """

    model = ResponseRecord
    form_class = SolicitationResponseForm
    template_name = "solicitations/response_form.html"

    def get_object(self, queryset=None):
        data_access = SolicitationDataAccess(opportunity_id=SOLICITATION_DEFAULT_OPPORTUNITY_ID, request=self.request)
        response_pk = self.kwargs.get("pk")
        if response_pk:
            # Edit mode - explicit PK provided
            response = data_access.get_response_by_id(response_pk)
            if not response:
                raise Http404("Response not found")

            # Verify user can edit - Labs uses OAuth organizations (slugs)
            user_org_slugs = []
            if hasattr(self.request.user, "organizations"):
                user_org_slugs = [org.get("slug") for org in self.request.user.organizations if org.get("slug")]

            if response.organization_id not in user_org_slugs:
                raise Http404("You can only edit your organization's responses")

            return response

        # Check if an organization was specified in POST/GET to load existing response
        org_slug = self.request.POST.get("organization_id") or self.request.GET.get("org")
        if org_slug:
            solicitation_pk = self.kwargs.get("solicitation_pk")
            if solicitation_pk:
                # Try to find existing response for this org+solicitation
                solicitation = data_access.get_solicitation_by_id(solicitation_pk)
                if solicitation:
                    response = data_access.get_response_for_solicitation(
                        solicitation_record=solicitation, organization_id=org_slug, username=self.request.user.username
                    )
                    if response:
                        return response

        return None

    def dispatch(self, request, *args, **kwargs):
        data_access = SolicitationDataAccess(opportunity_id=SOLICITATION_DEFAULT_OPPORTUNITY_ID, request=request)

        # Get solicitation
        if self.kwargs.get("pk"):
            response = self.get_object()
            self.solicitation = data_access.get_solicitation_by_id(response.labs_record_id)
        else:
            solicitation_pk = self.kwargs.get("solicitation_pk")
            self.solicitation = data_access.get_solicitation_by_id(solicitation_pk)

        if not self.solicitation:
            raise Http404("Solicitation not found")

        # Check if user can respond
        if not self.solicitation.can_accept_responses():
            messages.warning(request, "This solicitation is no longer accepting responses")
            return redirect("solicitations:detail", pk=self.solicitation.pk)

        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        data_access = SolicitationDataAccess(opportunity_id=SOLICITATION_DEFAULT_OPPORTUNITY_ID, request=self.request)
        kwargs = super().get_form_kwargs()
        kwargs["solicitation"] = self.solicitation
        kwargs["user"] = self.request.user
        kwargs["data_access"] = data_access
        # Pass instance if we have one (for editing existing responses)
        if self.object:
            kwargs["instance"] = self.object
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["solicitation"] = self.solicitation
        context["questions"] = self.solicitation.questions
        context["is_editing"] = self.kwargs.get("pk") is not None
        return context

    def form_valid(self, form):
        data_access = SolicitationDataAccess(opportunity_id=SOLICITATION_DEFAULT_OPPORTUNITY_ID, request=self.request)

        # Get organization slug from form (user selected it)
        org_slug = form.cleaned_data.get("organization_id")

        is_draft = self.request.POST.get("action") == "save_draft"

        # Prepare response data (exclude organization_id from responses)
        response_answers = {k: v for k, v in form.cleaned_data.items() if k != "organization_id"}
        response_data = {
            "status": "draft" if is_draft else "submitted",
            "responses": response_answers,
            "attachments": [],  # TODO: Handle attachments
            "submitted_by": {
                "id": self.request.user.id,
                "username": self.request.user.username,
                "email": self.request.user.email,
                "full_name": self.request.user.get_full_name()
                if hasattr(self.request.user, "get_full_name")
                else f"{self.request.user.first_name} {self.request.user.last_name}".strip(),
            },
        }

        # Create or update response
        if self.object:
            # Update existing via API
            response = data_access.update_response(
                record_id=self.object.id, data_dict=response_data, organization_id=org_slug
            )
        else:
            # Create new
            response = data_access.create_response(
                solicitation_record=self.solicitation,
                organization_id=org_slug,  # Pass slug (not int ID)
                username=self.request.user.username,
                data_dict=response_data,
            )

        if is_draft:
            messages.success(self.request, "Draft saved successfully")
            return redirect("solicitations:response_edit", pk=response.id)
        else:
            messages.success(self.request, "Response submitted successfully")
            return redirect("solicitations:response_detail", pk=response.id)


class SolicitationResponseDetailView(SolicitationResponseViewAccessMixin, DetailView):
    """
    View response details using LocalLabsRecords.
    """

    model = ResponseRecord
    template_name = "solicitations/response_detail.html"
    context_object_name = "response"

    def get_object(self, queryset=None):
        data_access = SolicitationDataAccess(opportunity_id=SOLICITATION_DEFAULT_OPPORTUNITY_ID, request=self.request)
        pk = self.kwargs.get("pk")
        response = data_access.get_response_by_id(pk)
        if not response:
            raise Http404("Response not found")
        return response

    def get_context_data(self, **kwargs):
        data_access = SolicitationDataAccess(opportunity_id=SOLICITATION_DEFAULT_OPPORTUNITY_ID, request=self.request)
        context = super().get_context_data(**kwargs)
        response = self.object
        solicitation = data_access.get_solicitation_by_id(response.labs_record_id)
        context["solicitation"] = solicitation

        # Get reviews
        # Note: This would need a method in data_access to fetch reviews for a response
        context["reviews"] = []  # TODO: Implement get_reviews_for_response

        # Build questions_with_answers for template
        questions_with_answers = []
        if solicitation and solicitation.questions:
            response_answers = response.responses  # Dict from JSON data
            for question in solicitation.questions:
                q_id = question.get("id")
                q_text = question.get("question_text")
                q_required = question.get("is_required", False)
                answer = response_answers.get(f"question_{q_id}", "")

                questions_with_answers.append(
                    {
                        "question": {
                            "question_text": q_text,
                            "is_required": q_required,
                        },
                        "answer": answer,
                    }
                )

        context["questions_with_answers"] = questions_with_answers
        return context


class SolicitationResponseReviewCreateOrUpdate(SolicitationManagerMixin, UpdateView):
    """
    Create or update a review for a response using LocalLabsRecords.
    """

    model = ReviewRecord
    form_class = SolicitationReviewForm
    template_name = "solicitations/review_form.html"

    def get_object(self, queryset=None):
        data_access = SolicitationDataAccess(opportunity_id=SOLICITATION_DEFAULT_OPPORTUNITY_ID, request=self.request)
        response_pk = self.kwargs.get("response_pk")
        response = data_access.get_response_by_id(response_pk)

        if not response:
            raise Http404("Response not found")

        # Check if review already exists for this user
        review = data_access.get_review_by_user(response_record=response, username=self.request.user.username)
        return review

    def dispatch(self, request, *args, **kwargs):
        data_access = SolicitationDataAccess(opportunity_id=SOLICITATION_DEFAULT_OPPORTUNITY_ID, request=request)
        response_pk = self.kwargs.get("response_pk")
        self.response = data_access.get_response_by_id(response_pk)

        if not self.response:
            raise Http404("Response not found")

        self.solicitation = data_access.get_solicitation_by_id(self.response.labs_record_id)

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["response"] = self.response
        context["solicitation"] = self.solicitation
        context["is_editing"] = self.object is not None

        # Add questions_with_answers for template
        questions_with_answers = []
        if self.solicitation and self.solicitation.questions:
            response_answers = self.response.responses
            for question in self.solicitation.questions:
                q_id = question.get("id")
                q_text = question.get("question_text")
                q_required = question.get("is_required", False)
                answer = response_answers.get(f"question_{q_id}", "")

                questions_with_answers.append(
                    {
                        "question": {
                            "question_text": q_text,
                            "is_required": q_required,
                        },
                        "answer": answer,
                    }
                )

        context["questions_with_answers"] = questions_with_answers
        return context

    def form_valid(self, form):
        data_access = SolicitationDataAccess(opportunity_id=SOLICITATION_DEFAULT_OPPORTUNITY_ID, request=self.request)
        review_data = {
            "score": form.cleaned_data.get("score"),
            "recommendation": form.cleaned_data.get("recommendation"),
            "notes": form.cleaned_data.get("notes"),
            "tags": form.cleaned_data.get("tags", ""),
        }

        if self.object:
            # Update existing review via API
            data_access.update_review(record_id=self.object.id, data_dict=review_data)
            messages.success(self.request, "Review updated successfully")
        else:
            # Create new review
            data_access.create_review(
                response_record=self.response, username=self.request.user.username, data_dict=review_data
            )
            messages.success(self.request, "Review submitted successfully")

        return redirect("solicitations:response_detail", pk=self.response.id)


class SolicitationCreateOrUpdate(SolicitationManagerMixin, UpdateView):
    """
    Create or edit solicitations using LocalLabsRecords.
    Simplified version that stores data in JSON.
    """

    model = SolicitationRecord
    form_class = SolicitationForm
    template_name = "solicitations/solicitation_form.html"

    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk")
        if pk:
            data_access = SolicitationDataAccess(
                opportunity_id=SOLICITATION_DEFAULT_OPPORTUNITY_ID, request=self.request
            )
            # Edit mode - return existing solicitation
            solicitation = data_access.get_solicitation_by_id(pk)
            if not solicitation:
                raise Http404("Solicitation not found")
            # For labs: permissions already checked by SolicitationManagerMixin
            return solicitation
        return None

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        # Remove instance since we're using LocalLabsRecords, not Solicitation model
        kwargs.pop("instance", None)

        # Pass user for program choices
        kwargs["user"] = self.request.user

        # For labs: form doesn't need program object, just use JSON data
        if self.object:
            # Populate form with JSON data for editing
            initial_data = self.object.data.copy()
            # Add program_id to initial data for the dropdown
            initial_data["program"] = str(self.object.program_id) if self.object.program_id else ""
            kwargs["initial"] = initial_data

        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # For labs: don't fetch program from DB, get production program info from OAuth data
        program_pk = self.kwargs.get("program_pk") or (self.object.program_id if self.object else None)
        if program_pk and hasattr(self.request.user, "programs"):
            # Find program in user's OAuth data
            for prog in self.request.user.programs:
                if prog.get("id") == program_pk:
                    context["program"] = prog
                    break

        # Build question context inline (no helper needed)
        if self.object and hasattr(self.object, "questions"):
            # Edit mode - load existing questions from JSON
            context["existing_questions"] = self.object.questions or []
        else:
            # Create mode - empty questions
            context["existing_questions"] = []

        # Add simple breadcrumb navigation for labs
        action_title = "Edit Solicitation" if self.object else "Create Solicitation"
        context["path"] = [
            {"title": "Solicitations Home", "url": reverse("solicitations:home")},
            {"title": "Manage Solicitations", "url": reverse("solicitations:manage_list")},
            {"title": action_title, "url": "#"},
        ]

        return context

    def form_valid(self, form):
        data_access = SolicitationDataAccess(opportunity_id=SOLICITATION_DEFAULT_OPPORTUNITY_ID, request=self.request)
        is_edit = self.object is not None

        # Get program ID and name from form (user selected from dropdown)
        program_pk = form.cleaned_data.get("program")
        program_name = None
        if hasattr(self.request.user, "programs") and program_pk:
            for prog in self.request.user.programs:
                if str(prog.get("id")) == str(program_pk):
                    program_name = prog.get("name")
                    break

        # For labs: we don't use organization_id for solicitation creation
        # (only for responses).

        # Parse questions data
        questions_data = self.request.POST.get("questions_data", "[]")
        try:
            questions = json.loads(questions_data) if questions_data else []
        except json.JSONDecodeError:
            questions = []

        # Assign IDs to questions that don't have them
        for question in questions:
            if not question.get("id"):
                question["id"] = str(uuid.uuid4())[:8]  # Use short UUID for readability

        # Prepare data for JSON storage
        solicitation_data = {
            "title": form.cleaned_data.get("title", ""),
            "description": form.cleaned_data.get("description", ""),
            "scope_of_work": form.cleaned_data.get("scope_of_work", ""),
            "solicitation_type": form.cleaned_data.get("solicitation_type", "eoi"),
            "status": form.cleaned_data.get("status", "draft"),
            "is_publicly_listed": form.cleaned_data.get("is_publicly_listed", True),
            "application_deadline": str(form.cleaned_data.get("application_deadline", "")),
            "expected_start_date": str(form.cleaned_data.get("expected_start_date", ""))
            if form.cleaned_data.get("expected_start_date")
            else "",
            "expected_end_date": str(form.cleaned_data.get("expected_end_date", ""))
            if form.cleaned_data.get("expected_end_date")
            else "",
            "estimated_scale": form.cleaned_data.get("estimated_scale", ""),
            "program_name": program_name,  # Store program name from OAuth data
            "questions": questions,
        }

        if is_edit:
            # Update existing record via API
            self.object = data_access.update_solicitation(
                record_id=self.object.id, data_dict=solicitation_data, program_id=program_pk
            )
            messages.success(
                self.request, f'Solicitation "{solicitation_data["title"]}" has been updated successfully.'
            )
        else:
            # Create new record with production IDs
            self.object = data_access.create_solicitation(
                program_id=program_pk,
                username=self.request.user.username,
                data_dict=solicitation_data,
            )
            messages.success(
                self.request, f'Solicitation "{solicitation_data["title"]}" has been created successfully.'
            )

        return redirect(self.get_success_url())

    def get_success_url(self):
        # Redirect to manage list after creating/editing solicitation
        return reverse("solicitations:manage_list")
