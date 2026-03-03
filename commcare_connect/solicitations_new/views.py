import logging

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import Http404
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from commcare_connect.solicitations_new.data_access import SolicitationsNewDataAccess

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


# -- Placeholder (replaced in Task 7) --------------------------------------


class RespondPlaceholderView(LabsLoginRequiredMixin, View):
    """Placeholder for the respond view. Redirects to detail until Task 7."""

    def get(self, request, pk):
        return redirect("solicitations_new:public_detail", pk=pk)
