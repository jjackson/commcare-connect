import json
import logging

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import Http404
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from commcare_connect.solicitations_new.data_access import SolicitationsNewDataAccess
from commcare_connect.solicitations_new.forms import SolicitationForm

logger = logging.getLogger(__name__)


# -- Permission Mixins ------------------------------------------------------


class LabsLoginRequiredMixin(LoginRequiredMixin):
    """Redirect to labs login."""

    login_url = "/labs/login/"


class ManagerRequiredMixin(LabsLoginRequiredMixin, UserPassesTestMixin):
    """Require authenticated labs user (manager access)."""

    def test_func(self):
        return getattr(self.request.user, "is_labs_user", False)


# -- Helpers ----------------------------------------------------------------


def _get_data_access(request):
    """Create data access from request. Works for authed requests."""
    return SolicitationsNewDataAccess(request=request)


# -- Public Views (no login) -----------------------------------------------


class PublicSolicitationListView(TemplateView):
    template_name = "solicitations_new/public_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        solicitation_type = self.request.GET.get("type")
        try:
            da = _get_data_access(self.request)
            ctx["solicitations"] = da.get_public_solicitations(
                solicitation_type=solicitation_type,
            )
        except Exception:
            logger.exception("Failed to load public solicitations")
            ctx["solicitations"] = []
        ctx["selected_type"] = solicitation_type or ""
        return ctx


class PublicSolicitationDetailView(TemplateView):
    template_name = "solicitations_new/public_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        pk = kwargs["pk"]
        try:
            da = _get_data_access(self.request)
            solicitation = da.get_solicitation_by_id(pk)
            if not solicitation:
                raise Http404("Solicitation not found")
            ctx["solicitation"] = solicitation
        except Http404:
            raise
        except Exception:
            logger.exception("Failed to load solicitation %s", pk)
            raise Http404("Solicitation not found")
        return ctx


# -- Manager Views (login required) ----------------------------------------


class ManageSolicitationsView(ManagerRequiredMixin, TemplateView):
    """List solicitations for the current program with response counts."""

    template_name = "solicitations_new/manage_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        try:
            da = _get_data_access(self.request)
            solicitations = da.get_solicitations()
            for s in solicitations:
                try:
                    responses = da.get_responses_for_solicitation(s.pk)
                    s._response_count = len(responses)
                except Exception:
                    s._response_count = 0
            ctx["solicitations"] = solicitations
        except Exception:
            logger.exception("Failed to load solicitations for manage view")
            ctx["solicitations"] = []
        return ctx


class SolicitationCreateView(ManagerRequiredMixin, TemplateView):
    """Create a new solicitation."""

    template_name = "solicitations_new/solicitation_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form"] = SolicitationForm()
        ctx["is_create"] = True
        ctx["existing_questions_json"] = "[]"
        return ctx

    def post(self, request, *args, **kwargs):
        form = SolicitationForm(request.POST)
        if form.is_valid():
            data = form.to_data_dict()
            data["created_by"] = request.user.username
            labs_context = getattr(request, "labs_context", {})
            data["program_name"] = labs_context.get("program_name", "")
            try:
                da = _get_data_access(request)
                da.create_solicitation(data)
                return redirect("solicitations_new:manage_list")
            except Exception:
                logger.exception("Failed to create solicitation")
                ctx = self.get_context_data(**kwargs)
                ctx["form"] = form
                ctx["error"] = "Failed to create solicitation. Please try again."
                return self.render_to_response(ctx)
        else:
            ctx = self.get_context_data(**kwargs)
            ctx["form"] = form
            return self.render_to_response(ctx)


class SolicitationEditView(ManagerRequiredMixin, TemplateView):
    """Edit an existing solicitation."""

    template_name = "solicitations_new/solicitation_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        pk = kwargs["pk"]
        try:
            da = _get_data_access(self.request)
            solicitation = da.get_solicitation_by_id(pk)
            if not solicitation:
                raise Http404("Solicitation not found")
            ctx["solicitation"] = solicitation
            # Populate form with initial data from the existing solicitation
            initial = {
                "title": solicitation.title,
                "description": solicitation.description,
                "scope_of_work": solicitation.scope_of_work,
                "solicitation_type": solicitation.solicitation_type,
                "status": solicitation.status,
                "is_public": solicitation.is_public,
                "application_deadline": solicitation.application_deadline,
                "expected_start_date": solicitation.expected_start_date,
                "expected_end_date": solicitation.expected_end_date,
                "estimated_scale": solicitation.estimated_scale,
                "contact_email": solicitation.contact_email,
            }
            ctx["form"] = SolicitationForm(initial=initial)
            ctx["is_create"] = False
            ctx["existing_questions_json"] = json.dumps(solicitation.questions)
        except Http404:
            raise
        except Exception:
            logger.exception("Failed to load solicitation %s for editing", pk)
            raise Http404("Solicitation not found")
        return ctx

    def post(self, request, *args, **kwargs):
        pk = kwargs["pk"]
        form = SolicitationForm(request.POST)
        if form.is_valid():
            data = form.to_data_dict()
            try:
                da = _get_data_access(request)
                da.update_solicitation(pk, data)
                return redirect("solicitations_new:manage_list")
            except Exception:
                logger.exception("Failed to update solicitation %s", pk)
                ctx = self.get_context_data(**kwargs)
                ctx["form"] = form
                ctx["error"] = "Failed to update solicitation. Please try again."
                return self.render_to_response(ctx)
        else:
            ctx = self.get_context_data(**kwargs)
            ctx["form"] = form
            return self.render_to_response(ctx)


class ResponsesListView(ManagerRequiredMixin, TemplateView):
    """List responses for a solicitation with review data."""

    template_name = "solicitations_new/responses_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        pk = kwargs["pk"]
        try:
            da = _get_data_access(self.request)
            solicitation = da.get_solicitation_by_id(pk)
            if not solicitation:
                raise Http404("Solicitation not found")
            ctx["solicitation"] = solicitation

            responses = da.get_responses_for_solicitation(pk)
            for r in responses:
                try:
                    reviews = da.get_reviews_for_response(r.pk)
                    r._reviews = reviews
                    r._latest_review = reviews[-1] if reviews else None
                except Exception:
                    r._reviews = []
                    r._latest_review = None
            ctx["responses"] = responses
        except Http404:
            raise
        except Exception:
            logger.exception("Failed to load responses for solicitation %s", pk)
            raise Http404("Solicitation not found")
        return ctx


# -- Placeholder (replaced in Task 7) --------------------------------------


class RespondPlaceholderView(LabsLoginRequiredMixin, View):
    """Placeholder for respond/response_detail/review views. Redirects to public list."""

    def get(self, request, pk=None, response_pk=None):
        if pk:
            return redirect("solicitations_new:public_detail", pk=pk)
        return redirect("solicitations_new:public_list")
