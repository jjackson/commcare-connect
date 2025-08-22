import json
import os

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.mail import send_mail
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView, UpdateView
from django_tables2 import SingleTableView

from commcare_connect.reports.views import SuperUserRequiredMixin

from .forms import SolicitationForm, SolicitationResponseForm, SolicitationReviewForm
from .helpers import (
    build_question_context,
    calculate_response_permissions,
    get_solicitation_dashboard_statistics,
    process_solicitation_questions,
    update_solicitation_questions,
)
from .models import ResponseAttachment, Solicitation, SolicitationQuestion, SolicitationResponse, SolicitationReview
from .tables import (
    SolicitationResponseTable,
    SolicitationTable,
    UserSolicitationResponseTable,
    UserSolicitationReviewTable,
)

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


class ResponseContextMixin:
    """
    Provides common response context data for solicitation responses.

    Extracts shared context logic from SolicitationResponseDetailMixin
    to be reusable across multiple response-related views.
    """

    def get_response_context(self, response):
        """Get context data for a solicitation response"""
        questions = SolicitationQuestion.objects.filter(solicitation=response.solicitation).order_by("order")

        # Build questions with answers
        questions_with_answers = []
        for question in questions:
            answer = response.responses.get(question.question_text, "")
            questions_with_answers.append(
                {
                    "question": question,
                    "answer": answer,
                    "has_answer": bool(answer),
                }
            )

        return {
            "questions_with_answers": questions_with_answers,
            "attachments": response.file_attachments.all(),
            "solicitation": response.solicitation,
        }


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
# Admin Overview Views
# =============================================================================


class AdminSolicitationOverview(SuperUserRequiredMixin, SingleTableView):
    """
    Admin-only overview of all solicitations across all organizations and programs
    Shows active solicitations with response statistics
    """

    template_name = "solicitations/admin_solicitation_overview.html"
    table_class = SolicitationTable
    context_object_name = "solicitations"
    paginate_by = 25

    def get_queryset(self):
        return (
            Solicitation.objects.filter(status=Solicitation.Status.ACTIVE)
            .select_related("program", "program__organization")
            .prefetch_related("responses")
            .annotate(
                total_responses=Count("responses", filter=~Q(responses__status=SolicitationResponse.Status.DRAFT)),
                submitted_count=Count("responses", filter=Q(responses__status=SolicitationResponse.Status.SUBMITTED)),
            )
            .order_by("-date_created")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Import here to avoid circular imports
        from commcare_connect.program.models import Program

        # Add summary statistics
        all_solicitations = Solicitation.objects.filter(status="active")
        context["summary_stats"] = {
            "total_active_solicitations": all_solicitations.count(),
            "total_eois": all_solicitations.filter(solicitation_type="eoi").count(),
            "total_rfps": all_solicitations.filter(solicitation_type="rfp").count(),
            "total_responses": SolicitationResponse.objects.exclude(status="draft").count(),
            "total_organizations_with_programs": Program.objects.values("organization").distinct().count(),
        }

        return context


# =============================================================================
# Program Management - to decide if this should exist or move to an integrated screen for programs
# =============================================================================
class ProgramSolicitationDashboard(SolicitationManagerMixin, SingleTableView):
    """
    Dashboard view for program managers to see all their solicitations and responses
    """

    template_name = "program/solicitation_dashboard.html"
    table_class = SolicitationTable
    context_object_name = "solicitations"
    paginate_by = 20

    def get_queryset(self):
        from commcare_connect.program.models import Program

        program_pk = self.kwargs.get("pk")
        program = get_object_or_404(Program, pk=program_pk, organization=self.request.org)

        return (
            Solicitation.objects.filter(program=program)
            .select_related("program", "program__organization")
            .prefetch_related("responses")
            .annotate(
                total_responses=Count("responses", filter=~Q(responses__status=SolicitationResponse.Status.DRAFT)),
                submitted_count=Count("responses", filter=Q(responses__status=SolicitationResponse.Status.SUBMITTED)),
            )
            .order_by("-date_created")
        )

    def get_table_kwargs(self):
        kwargs = super().get_table_kwargs()
        kwargs["org_slug"] = self.request.org.slug
        kwargs["show_program_org"] = False  # Hide program/org column for program dashboard
        return kwargs

    def get_context_data(self, **kwargs):
        from commcare_connect.program.models import Program

        context = super().get_context_data(**kwargs)
        program_pk = self.kwargs.get("pk")
        program = get_object_or_404(Program, pk=program_pk, organization=self.request.org)
        context["program"] = program

        # Add summary statistics for the statistics cards
        solicitations = self.get_queryset()
        context["stats"] = get_solicitation_dashboard_statistics(solicitations)

        return context


class PublicSolicitationListView(ListView):
    """
    Public list view of all publicly listed solicitations
    Beautiful donor-facing page
    """

    model = Solicitation
    template_name = "solicitations/public_list.html"
    context_object_name = "solicitations"
    paginate_by = 12

    def get_queryset(self):
        # Only show publicly listed and active solicitations
        queryset = (
            Solicitation.objects.filter(is_publicly_listed=True, status="active")
            .select_related("program", "program__organization")
            .annotate(total_responses=Count("responses"))
        )

        # Filter by type if specified
        solicitation_type = self.kwargs.get("type")
        if solicitation_type in ["eoi", "rfp"]:
            queryset = queryset.filter(solicitation_type=solicitation_type)

        return queryset.order_by("-date_created")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Add filter information
        context["current_type"] = self.kwargs.get("type", "all")

        # Add summary statistics for the page
        context["total_active"] = Solicitation.objects.filter(is_publicly_listed=True, status="active").count()

        context["eoi_count"] = Solicitation.objects.filter(
            is_publicly_listed=True, status="active", solicitation_type="eoi"
        ).count()

        context["rfp_count"] = Solicitation.objects.filter(
            is_publicly_listed=True, status="active", solicitation_type="rfp"
        ).count()

        return context


class PublicSolicitationDetailView(DetailView):
    """
    Public detail view of a specific solicitation
    Accessible even if not publicly listed (via direct URL)
    """

    model = Solicitation
    template_name = "solicitations/public_detail.html"
    context_object_name = "solicitation"

    def get_queryset(self):
        # Allow access to any solicitation via direct URL
        # but must be active status
        return (
            Solicitation.objects.filter(status="active")
            .select_related("program", "program__organization")
            .prefetch_related("questions")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Add deadline information
        solicitation = self.object
        today = timezone.now().date()

        if solicitation.application_deadline:
            days_remaining = (solicitation.application_deadline - today).days
            context["days_remaining"] = max(0, days_remaining)
            context["deadline_passed"] = days_remaining < 0

        # Add questions for display
        context["questions"] = solicitation.questions.all().order_by("order")

        # Add related solicitations (same program, different type)
        context["related_solicitations"] = Solicitation.objects.filter(
            program=solicitation.program, is_publicly_listed=True, status="active"
        ).exclude(pk=solicitation.pk)[:3]

        # Check for existing draft if user is authenticated and has organization
        context["has_draft"] = False
        context["has_submitted_response"] = False

        if self.request.user.is_authenticated and self.request.user.memberships.exists():
            user_org = self.request.user.memberships.first().organization

            # Check for existing draft
            draft = SolicitationResponse.objects.filter(
                solicitation=solicitation, organization=user_org, status=SolicitationResponse.Status.DRAFT
            ).first()

            if draft:
                context["has_draft"] = True
                context["draft"] = draft

            # Check for submitted response
            submitted_response = SolicitationResponse.objects.filter(
                solicitation=solicitation,
                organization=user_org,
                status=SolicitationResponse.Status.SUBMITTED,
            ).first()

            if submitted_response:
                context["has_submitted_response"] = True
                context["submitted_response"] = submitted_response

        return context


# Type-specific views that inherit from the main list view
# =============================================================================
# Response Overview Views
# =============================================================================
class SolicitationResponseTableView(SolicitationManagerMixin, SingleTableView):
    """
    Table view for solicitation responses using Django Tables2
    Similar approach to opportunities table
    Requires program manager permissions to view responses
    """

    model = SolicitationResponse
    table_class = SolicitationResponseTable
    template_name = "solicitations/response_table.html"
    context_object_name = "responses"
    paginate_by = 20

    def get_queryset(self):
        # Get solicitation from URL params
        solicitation_pk = self.kwargs.get("solicitation_pk")

        # Filter responses by solicitation
        return (
            SolicitationResponse.objects.filter(solicitation_id=solicitation_pk)
            .exclude(status="draft")  # Don't show drafts to program managers
            .select_related("organization", "submitted_by", "solicitation")
            .prefetch_related("reviews", "file_attachments")
            .order_by("-submission_date")
        )

    def get_table_kwargs(self):
        kwargs = super().get_table_kwargs()
        # Handle both URL patterns for org_slug
        org_slug = self.kwargs.get("org_slug") or getattr(self.request, "org", {}).slug
        program_pk = self.kwargs.get("program_pk") or self.kwargs.get("pk")

        kwargs["org_slug"] = org_slug
        kwargs["program_pk"] = program_pk
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Add solicitation and program context
        # Handle both URL patterns
        program_pk = self.kwargs.get("program_pk") or self.kwargs.get("pk")
        solicitation_pk = self.kwargs.get("solicitation_pk")

        # Get solicitation for header info
        solicitation = get_object_or_404(Solicitation, pk=solicitation_pk)

        # Calculate response statistics efficiently
        responses = self.get_queryset()
        status_counts = {
            "submitted": 0,
        }

        for response in responses:
            if response.status in status_counts:
                status_counts[response.status] += 1

        context["solicitation"] = solicitation
        context["program_pk"] = program_pk
        context["status_counts"] = status_counts

        return context


class SolicitationResponseSuccessView(SolicitationAccessMixin, DetailView):
    """
    Success page after submitting a response
    """

    model = SolicitationResponse
    template_name = "solicitations/response_success.html"
    context_object_name = "response"

    def get_queryset(self):
        # Only allow users to view their own organization's responses
        # SolicitationAccessMixin already ensures user has organization membership
        user_org = self.request.user.memberships.first().organization
        return SolicitationResponse.objects.filter(organization=user_org)


class SolicitationResponseDetailView(SolicitationAccessMixin, ResponseContextMixin, DetailView):
    """
    Detailed view of a response for the user who submitted it
    """

    model = SolicitationResponse
    template_name = "solicitations/response_detail.html"
    context_object_name = "response"

    def get_queryset(self):
        # Only allow users to view their own organization's responses
        if self.request.user.memberships.exists():
            user_org = self.request.user.memberships.first().organization
            return (
                SolicitationResponse.objects.filter(
                    organization=user_org,
                    status=SolicitationResponse.Status.SUBMITTED,
                )
                .select_related("solicitation", "organization", "submitted_by")
                .prefetch_related("file_attachments")
            )
        return SolicitationResponse.objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        response = self.object

        # Use mixin to get shared context
        shared_context = self.get_response_context(response)
        context.update(shared_context)

        # Add user-specific context
        context["can_edit"] = response.status == SolicitationResponse.Status.DRAFT

        return context


class SolicitationResponseCreateOrUpdate(SolicitationAccessMixin, UpdateView):
    """
    Consolidated view for creating and editing solicitation responses.

    Follows the ProgramCreateOrUpdate pattern exactly:
    - Create mode: get_object() returns None, uses solicitation_pk from URL
    - Edit mode: get_object() returns existing response, uses pk from URL
    """

    model = SolicitationResponse
    form_class = SolicitationResponseForm
    template_name = "solicitations/response_form.html"

    def get_object(self, queryset=None):
        """Return None for create mode, existing response for edit mode"""
        # Check if we have a response pk (edit mode) or solicitation pk (create mode)
        response_pk = self.kwargs.get("pk")

        if response_pk:
            # Edit mode - return existing response with permission checks
            response = get_object_or_404(
                SolicitationResponse.objects.select_related("solicitation", "organization"), pk=response_pk
            )

            # Verify user can edit this response
            # SolicitationAccessMixin already ensures user has organization membership
            user_org = self.request.user.memberships.first().organization
            if response.organization != user_org:
                raise Http404("You can only edit your organization's responses.")

            # Check if response is in an editable state
            if response.status != SolicitationResponse.Status.DRAFT:
                raise Http404("Only draft responses can be edited.")

            return response

        # Create mode - return None (like ProgramCreateOrUpdate)
        return None

    def dispatch(self, request, *args, **kwargs):
        """Handle solicitation-specific permission checks"""
        # SolicitationAccessMixin handles basic authentication and organization membership

        # Get solicitation from URL (either directly or via response)
        if self.kwargs.get("pk"):
            # Edit mode - get solicitation from response
            response = self.get_object()
            self.solicitation = response.solicitation
        else:
            # Create mode - get solicitation directly
            solicitation_pk = self.kwargs.get("solicitation_pk")
            self.solicitation = get_object_or_404(Solicitation, pk=solicitation_pk)

        # Check solicitation-specific permissions for create mode
        if not self.kwargs.get("pk"):  # Create mode
            if hasattr(request, "user") and request.user.is_authenticated:
                # Use helper function for solicitation-specific checks
                permissions = calculate_response_permissions(request.user, self.solicitation)

                if not permissions["can_respond"] and permissions["redirect_needed"]:
                    if permissions["existing_submitted_response"]:
                        messages.warning(request, permissions["error_message"])
                    else:
                        messages.error(request, permissions["error_message"])
                    return redirect("solicitations:detail", pk=self.solicitation.pk)

                # Store existing draft for use in other methods
                self.existing_draft = permissions["existing_draft"]

        # For edit mode, check if solicitation still accepts responses
        elif not self.solicitation.can_accept_responses:
            messages.warning(
                request, "This solicitation is no longer accepting responses, but you can still view your submission."
            )
            return redirect("solicitations:user_response_detail", pk=self.get_object().pk)

        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        """Setup form with proper context"""
        kwargs = super().get_form_kwargs()
        kwargs["solicitation"] = self.solicitation
        kwargs["user"] = self.request.user

        # Check if this is a draft save
        if self.request.method == "POST":
            kwargs["is_draft_save"] = self.request.POST.get("action") == "save_draft"
        else:
            kwargs["is_draft_save"] = False

        # For create mode with existing draft, use the draft as instance
        if not self.kwargs.get("pk") and hasattr(self, "existing_draft") and self.existing_draft:
            kwargs["instance"] = self.existing_draft

        return kwargs

    def get_context_data(self, **kwargs):
        """Provide context for both create and edit modes"""
        context = super().get_context_data(**kwargs)
        context["solicitation"] = self.solicitation
        context["questions"] = SolicitationQuestion.objects.filter(solicitation=self.solicitation).order_by("order")

        # Determine mode and set context accordingly
        is_edit_mode = self.kwargs.get("pk") is not None
        context["is_editing"] = is_edit_mode

        if is_edit_mode:
            # Edit mode context
            context["response"] = self.object
            context["existing_attachments"] = self.object.file_attachments.all()
        else:
            # Create mode context
            context["is_editing_draft"] = hasattr(self, "existing_draft") and self.existing_draft
            if context["is_editing_draft"]:
                context["draft"] = self.existing_draft
                context["existing_attachments"] = self.existing_draft.file_attachments.all()
            else:
                context["existing_attachments"] = []

        return context

    def form_valid(self, form):
        """Handle form submission for both create and edit modes"""
        response = form.save()
        is_edit_mode = self.kwargs.get("pk") is not None

        # Check if this is a draft save or final submission
        if self.request.POST.get("action") == "save_draft":
            # Keep as draft
            response.status = SolicitationResponse.Status.DRAFT
            response.save(update_fields=["status", "responses"])

            if is_edit_mode:
                messages.success(self.request, "Your response has been saved as a draft.")
                return redirect("solicitations:user_response_edit", pk=response.pk)
            else:
                messages.success(self.request, f"Your draft response to '{self.solicitation.title}' has been saved!")
                return redirect("solicitations:respond", pk=self.solicitation.pk)
        else:
            # Submit the response
            response.status = SolicitationResponse.Status.SUBMITTED
            if not is_edit_mode:
                response.submission_date = timezone.now()
            response.save(update_fields=["status", "responses", "submission_date"])

            if is_edit_mode:
                messages.success(self.request, "Your response has been updated successfully.")
                return redirect("solicitations:user_response_detail", pk=response.pk)
            else:
                # Send email notification to program managers for new submissions
                self._send_notification_email(response)
                messages.success(
                    self.request, f"Your response to '{self.solicitation.title}' has been submitted successfully!"
                )
                return redirect("solicitations:response_success", pk=response.pk)

    def _send_notification_email(self, response):
        """Send email notification to program managers (for new submissions only)"""
        try:
            program_managers = self.solicitation.program.organization.members.filter(
                organizationusermembership__role__in=["admin", "program_manager"]
            )

            if program_managers.exists():
                recipient_emails = [user.email for user in program_managers if user.email]

                if recipient_emails:
                    subject = f"New Response Submitted: {self.solicitation.title}"
                    message = f"""
A new response has been submitted for the solicitation "{self.solicitation.title}".

Organization: {response.organization.name}
Submitted by: {response.submitted_by.get_full_name()} ({response.submitted_by.email})
Submission date: {response.submission_date.strftime('%B %d, %Y at %I:%M %p')}

Please log in to review the response.
                    """

                    send_mail(
                        subject=subject,
                        message=message,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=recipient_emails,
                        fail_silently=True,
                    )
        except Exception:
            # Don't let email failures break the response submission
            pass


class SolicitationResponseDraftListView(SolicitationAccessMixin, ListView):
    """
    View to list user's draft responses
    """

    model = SolicitationResponse
    template_name = "solicitations/draft_list.html"
    context_object_name = "drafts"

    def get_queryset(self):
        # SolicitationAccessMixin already ensures user has organization membership
        user_org = self.request.user.memberships.first().organization
        return SolicitationResponse.objects.filter(
            organization=user_org, status=SolicitationResponse.Status.DRAFT
        ).order_by("-date_modified")


class UserSolicitationDashboard(SolicitationAccessMixin, SingleTableView):
    """
    User dashboard view showing solicitations for programs they're a member of,
    their responses, and their reviews.
    """

    model = Solicitation
    table_class = SolicitationTable
    template_name = "solicitations/dashboard.html"
    context_object_name = "solicitations"
    paginate_by = 20

    def get_queryset(self):
        # Get all organizations the user is a member of
        user_orgs = [membership.organization for membership in self.request.user.memberships.all()]

        # Get solicitations for programs owned by any of the user's organizations
        # This includes both Program Manager orgs (who create solicitations) and
        # Network Manager orgs (who can respond to solicitations for their own programs)
        return (
            Solicitation.objects.filter(program__organization__in=user_orgs, status=Solicitation.Status.ACTIVE)
            .select_related("program", "program__organization")
            .prefetch_related("responses")
            .annotate(
                total_responses=Count("responses", filter=~Q(responses__status=SolicitationResponse.Status.DRAFT)),
                submitted_count=Count("responses", filter=Q(responses__status=SolicitationResponse.Status.SUBMITTED)),
            )
            .order_by("-date_created")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get all organizations the user is a member of
        user_orgs = [membership.organization for membership in self.request.user.memberships.all()]

        # Get programs owned by any of the user's organizations (direct relationship)
        from commcare_connect.program.models import Program

        user_programs = Program.objects.filter(organization__in=user_orgs)

        # Add summary statistics for the statistics cards
        solicitations = self.get_queryset()
        context["stats"] = {
            "total_active_solicitations": solicitations.count(),
            "total_eois": solicitations.filter(solicitation_type="eoi").count(),
            "total_rfps": solicitations.filter(solicitation_type="rfp").count(),
            "total_responses": SolicitationResponse.objects.filter(organization__in=user_orgs)
            .exclude(status="draft")
            .count(),
            "programs_count": user_programs.count(),
        }

        # User responses table (submitted/draft) - across all user's organizations
        user_responses = (
            SolicitationResponse.objects.filter(organization__in=user_orgs)
            .select_related("solicitation", "solicitation__program", "submitted_by")
            .order_by("-date_modified")
        )

        context["user_responses_table"] = UserSolicitationResponseTable(user_responses)

        # User reviews table (if any)
        user_reviews = (
            SolicitationReview.objects.filter(reviewer=self.request.user)
            .select_related("response__solicitation", "response__organization")
            .order_by("-review_date")
        )

        context["user_reviews_table"] = UserSolicitationReviewTable(user_reviews)

        return context


class SolicitationCreateOrUpdate(SolicitationManagerMixin, UpdateView):
    """
    Consolidated view for creating and editing solicitations.

    Follows the ProgramCreateOrUpdate pattern exactly:
    - Create mode: get_object() returns None, uses program_pk from URL
    - Edit mode: get_object() returns existing solicitation, uses pk from URL
    """

    model = Solicitation
    form_class = SolicitationForm
    template_name = "solicitations/solicitation_form.html"

    def get_object(self, queryset=None):
        """Return None for create mode, existing solicitation for edit mode"""
        pk = self.kwargs.get("pk")
        if pk:
            # Edit mode - return existing solicitation with permission checks
            obj = get_object_or_404(
                Solicitation.objects.select_related("program", "program__organization"),
                pk=pk,
                program__organization=self.request.org,
            )
            return obj
        # Create mode - return None (like ProgramCreateOrUpdate)
        return None

    def get_form_kwargs(self):
        """Setup form with proper program context"""
        kwargs = super().get_form_kwargs()
        from commcare_connect.program.models import Program

        if self.object:
            # Edit mode - get program from existing object
            kwargs["program"] = self.object.program
        else:
            # Create mode - get program from URL
            program_pk = self.kwargs.get("program_pk")
            if program_pk:
                program = get_object_or_404(Program, pk=program_pk, organization=self.request.org)
                kwargs["program"] = program

        return kwargs

    def get_context_data(self, **kwargs):
        """Provide context for both create and edit modes"""
        context = super().get_context_data(**kwargs)
        from commcare_connect.program.models import Program

        if self.object:
            # Edit mode context
            context["program"] = self.object.program
            question_context = build_question_context(self.object, is_edit=True)
        else:
            # Create mode context
            program_pk = self.kwargs.get("program_pk")
            if program_pk:
                context["program"] = get_object_or_404(Program, pk=program_pk, organization=self.request.org)
            question_context = build_question_context(None, is_edit=False)

        context.update(question_context)
        return context

    def form_valid(self, form):
        """Handle form submission for both create and edit modes"""
        is_edit = self.object is not None

        # Set audit fields
        if is_edit:
            form.instance.modified_by = self.request.user.email
        else:
            form.instance.created_by = self.request.user.email
            form.instance.modified_by = self.request.user.email

        # Save the solicitation first
        response = super().form_valid(form)

        # Process questions using appropriate helper
        questions_data = self.request.POST.get("questions_data")
        if is_edit:
            success, error_message = update_solicitation_questions(questions_data, self.object)
        else:
            success, error_message = process_solicitation_questions(questions_data, self.object)

        if not success:
            if is_edit:
                messages.warning(self.request, f"Questions could not be saved: {error_message}. Please try again.")
            else:
                messages.warning(
                    self.request,
                    f"Questions could not be saved: {error_message}. Please edit the solicitation to add questions.",
                )

        # Success message
        status = ("created", "updated")[is_edit]
        messages.success(self.request, f'Solicitation "{form.instance.title}" has been {status} successfully.')

        return response

    def get_success_url(self):
        """Redirect to program dashboard"""
        return reverse(
            "org_solicitations:program_dashboard",
            kwargs={"org_slug": self.request.org.slug, "pk": self.object.program.pk},
        )


class SolicitationResponseReviewCreateOrUpdate(SolicitationManagerMixin, ResponseContextMixin, UpdateView):
    """
    Consolidated view for creating and editing solicitation response reviews.

    Follows the ProgramCreateOrUpdate pattern exactly:
    - Create mode: get_object() returns None, creates new review
    - Edit mode: get_object() returns existing review
    """

    model = SolicitationReview
    form_class = SolicitationReviewForm
    template_name = "solicitations/response_review.html"

    def get_object(self, queryset=None):
        """Return existing review for edit mode, None for create mode"""
        from commcare_connect.program.models import Program

        program_pk = self.kwargs.get("pk")
        response_pk = self.kwargs.get("response_pk")

        # Verify program ownership through the response's solicitation
        program = get_object_or_404(Program, pk=program_pk, organization=self.request.org)
        self.response = get_object_or_404(
            SolicitationResponse.objects.select_related(
                "solicitation__program", "organization", "submitted_by"
            ).prefetch_related("file_attachments", "reviews"),
            pk=response_pk,
            solicitation__program=program,
        )

        # Try to get existing review by current user
        existing_review = SolicitationReview.objects.filter(response=self.response, reviewer=self.request.user).first()

        if existing_review:
            return existing_review  # Edit mode
        return None  # Create mode

    def get_form_kwargs(self):
        """Setup form with proper context"""
        kwargs = super().get_form_kwargs()

        # For create mode, we don't have an instance yet
        if not self.object:
            kwargs.pop("instance", None)

        return kwargs

    def get_context_data(self, **kwargs):
        """Provide context for both create and edit modes"""
        context = super().get_context_data(**kwargs)

        # Get response (set in get_object)
        response = getattr(self, "response", None)
        if not response:
            # Fallback if response wasn't set
            program_pk = self.kwargs.get("pk")
            response_pk = self.kwargs.get("response_pk")
            from commcare_connect.program.models import Program

            program = get_object_or_404(Program, pk=program_pk, organization=self.request.org)
            response = get_object_or_404(
                SolicitationResponse.objects.select_related(
                    "solicitation__program", "organization", "submitted_by"
                ).prefetch_related("file_attachments", "reviews"),
                pk=response_pk,
                solicitation__program=program,
            )

        program = response.solicitation.program

        # Use ResponseContextMixin to get response context (questions, answers, attachments)
        shared_context = self.get_response_context(response)

        # Determine if this is edit mode
        is_edit_mode = self.object is not None

        context.update(
            {
                "program": program,
                "response": response,
                "existing_review": self.object,  # Will be None for create mode
                "is_editing_review": is_edit_mode,
            }
        )

        # Add the shared context from the mixin
        context.update(shared_context)

        return context

    def form_valid(self, form):
        """Handle form submission for both create and edit modes"""
        is_edit_mode = self.object is not None

        if is_edit_mode:
            # Edit mode - update existing review
            review = self.object
        else:
            # Create mode - create new review
            review = SolicitationReview(response=self.response, reviewer=self.request.user)

        # Update review with form data
        review.score = form.cleaned_data.get("score")
        review.notes = form.cleaned_data.get("notes", "")
        review.tags = form.cleaned_data.get("tags", "")
        review.recommendation = form.cleaned_data.get("recommendation")
        review.save()

        # Set self.object for success URL generation
        self.object = review

        # Review submitted successfully - no status changes needed
        messages.success(self.request, f"Review submitted for {self.response.organization.name}.")

        return super().form_valid(form)

    def get_success_url(self):
        """Redirect back to response list for the program"""
        return reverse(
            "org_solicitations:program_response_list",
            kwargs={
                "org_slug": self.request.org.slug,
                "pk": self.response.solicitation.program.pk,
                "solicitation_pk": self.response.solicitation.pk,
            },
        )


@solicitation_access_required
@require_POST
def save_draft_ajax(request, pk):
    """
    AJAX endpoint for saving draft responses
    """
    try:
        solicitation = get_object_or_404(Solicitation, pk=pk)
        # solicitation_access_required decorator already ensures user has organization membership
        user_org = request.user.memberships.first().organization

        # Get or create draft
        draft, created = SolicitationResponse.objects.get_or_create(
            solicitation=solicitation,
            organization=user_org,
            status=SolicitationResponse.Status.DRAFT,
            defaults={"submitted_by": request.user, "responses": {}},
        )

        # Update draft with form data (no validation needed for drafts)
        form_data = json.loads(request.body)
        draft.responses = form_data.get("responses", {})
        draft.save(update_fields=["responses", "date_modified"])

        return JsonResponse({"success": True, "message": "Draft saved successfully", "draft_id": draft.pk})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@solicitation_access_required
@require_POST
def upload_attachment(request, pk):
    """
    Standard Django file upload endpoint (following opportunity app pattern)
    """
    solicitation = get_object_or_404(Solicitation, pk=pk)
    # solicitation_access_required decorator already ensures user has organization membership
    user_org = request.user.memberships.first().organization

    # Get or create draft response
    draft, created = SolicitationResponse.objects.get_or_create(
        solicitation=solicitation,
        organization=user_org,
        status=SolicitationResponse.Status.DRAFT,
        defaults={"submitted_by": request.user, "responses": {}},
    )

    # Handle file upload
    uploaded_file = request.FILES.get("attachment")
    if not uploaded_file:
        messages.error(request, "No file provided")
        return redirect("solicitations:respond", pk=pk)

    # Validate file size (10MB limit)
    max_size = 10 * 1024 * 1024  # 10MB
    if uploaded_file.size > max_size:
        messages.error(request, "File too large. Maximum size is 10MB.")
        return redirect("solicitations:respond", pk=pk)

    # Validate file type
    allowed_extensions = [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".jpg", ".jpeg", ".png"]
    file_extension = os.path.splitext(uploaded_file.name)[1].lower()
    if file_extension not in allowed_extensions:
        messages.error(request, f"File type not allowed. Allowed types: {', '.join(allowed_extensions)}")
        return redirect("solicitations:respond", pk=pk)

    # Create attachment using the standard pattern
    try:
        ResponseAttachment.objects.create(
            response=draft,
            file=uploaded_file,
            original_filename=uploaded_file.name,
            file_size=uploaded_file.size,
            uploaded_by=request.user,
        )
        messages.success(request, f"File '{uploaded_file.name}' uploaded successfully")
    except Exception as e:
        messages.error(request, f"Failed to upload file: {str(e)}")

    return redirect("solicitations:respond", pk=pk)


@solicitation_access_required
@require_POST
def delete_attachment(request, pk, attachment_id):
    """
    Standard Django file deletion endpoint
    """
    attachment = get_object_or_404(ResponseAttachment, pk=attachment_id)

    # Check permissions - user must be the uploader or in same org
    # solicitation_access_required decorator already ensures user has organization membership
    user_org = request.user.memberships.first().organization
    if attachment.uploaded_by != request.user and attachment.response.organization != user_org:
        messages.error(request, "You don't have permission to delete this file")
        return redirect("solicitations:respond", pk=pk)

    try:
        filename = attachment.original_filename
        attachment.delete()
        messages.success(request, f"File '{filename}' deleted successfully")
    except Exception as e:
        messages.error(request, f"Failed to delete file: {str(e)}")

    return redirect("solicitations:respond", pk=pk)
