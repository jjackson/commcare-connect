import json
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DetailView, ListView, TemplateView, UpdateView
from django_tables2 import SingleTableView

from .experiment_helpers import (
    create_response_record,
    create_review_record,
    create_solicitation_record,
    get_response_by_id,
    get_response_for_solicitation,
    get_responses_for_solicitation,
    get_review_by_user,
    get_solicitation_by_id,
    get_solicitations,
)
from .experiment_models import ResponseRecord, ReviewRecord, SolicitationRecord
from .forms import SolicitationForm, SolicitationResponseForm, SolicitationReviewForm

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
# New ExperimentRecord-based Views
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
        # Use data access layer to filter by user's production ID
        from commcare_connect.labs.api_helpers import ExperimentRecordAPI

        api = ExperimentRecordAPI()
        qs = api.get_records(experiment="solicitations", type="Solicitation", user_id=self.request.user.id)
        return SolicitationRecord.objects.filter(pk__in=qs.values_list("pk", flat=True)).order_by("-date_created")


class MyResponsesListView(ListView):
    """
    List view of responses created by the current user's organization.
    """

    model = ResponseRecord
    template_name = "solicitations/my_responses.html"
    context_object_name = "responses"
    paginate_by = 20

    def get_queryset(self):
        # Get user's organization slugs from OAuth data (we store slugs, not IDs)
        org_slugs = []
        if hasattr(self.request.user, "organizations") and self.request.user.organizations:
            org_slugs = [org.get("slug") for org in self.request.user.organizations if org.get("slug")]

        if org_slugs:
            # Use data access layer - need to combine results for all orgs
            from commcare_connect.labs.api_helpers import ExperimentRecordAPI

            api = ExperimentRecordAPI()

            # Get records for all user's organizations
            qs = api.get_records(experiment="solicitations", type="SolicitationResponse").filter(
                organization_id__in=org_slugs
            )

            return ResponseRecord.objects.filter(pk__in=qs.values_list("pk", flat=True)).order_by("-date_created")
        return ResponseRecord.objects.none()


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
        # Get the solicitation
        solicitation_pk = self.kwargs.get("solicitation_pk")
        self.solicitation = get_solicitation_by_id(solicitation_pk)

        if not self.solicitation:
            raise Http404("Solicitation not found")

        # Check if user created this solicitation
        if self.solicitation.user_id != request.user.id:
            raise Http404("You can only view responses to your own solicitations")

        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return get_responses_for_solicitation(self.solicitation)

    def get_table_class(self):
        from .experiment_tables import ResponseRecordTable

        return ResponseRecordTable

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["solicitation"] = self.solicitation
        return context


class SolicitationListView(ListView):
    """
    Public list view of all publicly listed solicitations using ExperimentRecords.
    """

    model = SolicitationRecord
    template_name = "solicitations/solicitation_list.html"
    context_object_name = "solicitations"
    paginate_by = 12

    def get_queryset(self):
        solicitation_type = self.kwargs.get("type")
        qs = get_solicitations(status="active", is_publicly_listed=True)

        if solicitation_type:
            qs = qs.filter(data__solicitation_type=solicitation_type)

        # No select_related needed since we use IDs only (no ForeignKeys)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_type"] = self.kwargs.get("type", "all")
        context["total_active"] = get_solicitations(status="active", is_publicly_listed=True).count()
        context["eoi_count"] = get_solicitations(
            status="active", is_publicly_listed=True, solicitation_type="eoi"
        ).count()
        context["rfp_count"] = get_solicitations(
            status="active", is_publicly_listed=True, solicitation_type="rfp"
        ).count()
        return context


class SolicitationDetailView(DetailView):
    """
    Public detail view of a specific solicitation using ExperimentRecords.
    """

    model = SolicitationRecord
    template_name = "solicitations/solicitation_detail.html"
    context_object_name = "solicitation"

    def get_queryset(self):
        # No select_related needed since we use IDs only (no ForeignKeys)
        return get_solicitations(status="active")

    def get_context_data(self, **kwargs):
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
            draft = get_response_for_solicitation(solicitation, user_org, status="draft")
            if draft:
                context["has_draft"] = True
                context["draft"] = draft

            # Check for submitted response
            submitted = get_response_for_solicitation(solicitation, user_org, status="submitted")
            if submitted:
                context["has_submitted_response"] = True
                context["submitted_response"] = submitted

        return context


class SolicitationResponseCreateOrUpdate(SolicitationAccessMixin, UpdateView):
    """
    Create or update a solicitation response using ExperimentRecords.
    Simplified version that works directly with JSON data.
    """

    model = ResponseRecord
    form_class = SolicitationResponseForm
    template_name = "solicitations/response_form.html"

    def get_object(self, queryset=None):
        response_pk = self.kwargs.get("pk")
        if response_pk:
            # Edit mode - explicit PK provided
            response = get_response_by_id(response_pk)
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
                from .experiment_helpers import get_response_for_solicitation

                solicitation = get_solicitation_by_id(solicitation_pk)
                if solicitation:
                    response = get_response_for_solicitation(solicitation, org_slug, self.request.user.id)
                    if response:
                        return response

        return None

    def dispatch(self, request, *args, **kwargs):
        # Get solicitation
        if self.kwargs.get("pk"):
            response = self.get_object()
            self.solicitation = get_solicitation_by_id(response.parent_id)
        else:
            solicitation_pk = self.kwargs.get("solicitation_pk")
            self.solicitation = get_solicitation_by_id(solicitation_pk)

        if not self.solicitation:
            raise Http404("Solicitation not found")

        # Check if user can respond
        if not self.solicitation.can_accept_responses():
            messages.warning(request, "This solicitation is no longer accepting responses")
            return redirect("solicitations:detail", pk=self.solicitation.pk)

        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["solicitation"] = self.solicitation
        kwargs["user"] = self.request.user
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
            # Update existing
            self.object.data = response_data
            self.object.organization_id = org_slug  # Store slug (not int ID)
            self.object.save()
            response = self.object
        else:
            # Create new
            response = create_response_record(
                solicitation_record=self.solicitation,
                organization_id=org_slug,  # Pass slug (not int ID)
                user_id=self.request.user.id,
                data_dict=response_data,
            )

        if is_draft:
            messages.success(self.request, "Draft saved successfully")
            return redirect("solicitations:response_edit", pk=response.pk)
        else:
            messages.success(self.request, "Response submitted successfully")
            return redirect("solicitations:response_detail", pk=response.pk)


class SolicitationResponseDetailView(SolicitationResponseViewAccessMixin, DetailView):
    """
    View response details using ExperimentRecords.
    """

    model = ResponseRecord
    template_name = "solicitations/response_detail.html"
    context_object_name = "response"

    def get_queryset(self):
        # Use data access layer to get responses
        from commcare_connect.labs.api_helpers import ExperimentRecordAPI

        api = ExperimentRecordAPI()
        qs = api.get_records(experiment="solicitations", type="SolicitationResponse")
        return ResponseRecord.objects.filter(pk__in=qs.values_list("pk", flat=True))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        response = self.object
        solicitation = get_solicitation_by_id(response.parent_id)
        context["solicitation"] = solicitation
        context["reviews"] = response.children.filter(type="SolicitationReview")

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
    Create or update a review for a response using ExperimentRecords.
    """

    model = ReviewRecord
    form_class = SolicitationReviewForm
    template_name = "solicitations/review_form.html"

    def get_object(self, queryset=None):
        response_pk = self.kwargs.get("response_pk")
        response = get_response_by_id(response_pk)

        if not response:
            raise Http404("Response not found")

        # Check if review already exists for this user
        review = get_review_by_user(response, self.request.user)
        return review

    def dispatch(self, request, *args, **kwargs):
        response_pk = self.kwargs.get("response_pk")
        self.response = get_response_by_id(response_pk)

        if not self.response:
            raise Http404("Response not found")

        self.solicitation = get_solicitation_by_id(self.response.parent_id)

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
        review_data = {
            "score": form.cleaned_data.get("score"),
            "recommendation": form.cleaned_data.get("recommendation"),
            "notes": form.cleaned_data.get("notes"),
            "tags": form.cleaned_data.get("tags", ""),
        }

        if self.object:
            # Update existing review
            self.object.data = review_data
            self.object.save()
            messages.success(self.request, "Review updated successfully")
        else:
            # Create new review
            create_review_record(
                response_record=self.response, reviewer_id=self.request.user.id, data_dict=review_data
            )
            messages.success(self.request, "Review submitted successfully")

        return redirect("solicitations:response_detail", pk=self.response.pk)


class SolicitationCreateOrUpdate(SolicitationManagerMixin, UpdateView):
    """
    Create or edit solicitations using ExperimentRecords.
    Simplified version that stores data in JSON.
    """

    model = SolicitationRecord
    form_class = SolicitationForm
    template_name = "solicitations/solicitation_form.html"

    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk")
        if pk:
            # Edit mode - return existing solicitation
            program_pk = self.kwargs.get("program_pk")
            filters = {"pk": pk, "experiment": "solicitations", "type": "Solicitation"}
            if program_pk:
                filters["program_id"] = program_pk

            obj = get_object_or_404(SolicitationRecord, **filters)
            # For labs: permissions already checked by SolicitationManagerMixin
            return obj
        return None

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        # Remove instance since we're using ExperimentRecords, not Solicitation model
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
        # (only for responses). Set to None.
        org_id = None

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
            # Update existing record
            self.object.data = solicitation_data
            self.object.save()
            messages.success(
                self.request, f'Solicitation "{solicitation_data["title"]}" has been updated successfully.'
            )
        else:
            # Create new record with production IDs
            self.object = create_solicitation_record(
                program_id=program_pk,
                organization_id=org_id,
                user_id=self.request.user.id,
                data_dict=solicitation_data,
            )
            messages.success(
                self.request, f'Solicitation "{solicitation_data["title"]}" has been created successfully.'
            )

        return redirect(self.get_success_url())

    def get_success_url(self):
        # Redirect to manage list after creating/editing solicitation
        return reverse("solicitations:manage_list")
