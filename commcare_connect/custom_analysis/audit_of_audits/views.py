"""
Views for the Audit of Audits admin report.

Access is restricted to users with @dimagi.com email addresses via
DimagiUserRequiredMixin. This report is intentionally not visible to
normal users (Network Managers, FLWs, etc.) — the tile is also hidden
from the overview page for non-@dimagi.com users.
"""

import logging

from django.contrib.auth.mixins import AccessMixin, LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.views.generic import TemplateView

from commcare_connect.labs.integrations.connect.api_client import LabsAPIError

from .data_access import AuditOfAuditsDataAccess

logger = logging.getLogger(__name__)

DIMAGI_EMAIL_DOMAIN = "@dimagi.com"


class DimagiUserRequiredMixin(AccessMixin):
    """
    Restricts view access to users whose email ends with @dimagi.com.

    Works with LabsUser (transient OAuth user) which always has .email
    populated from the OAuth token user_profile, as well as with the
    standard Django User model.

    Unauthenticated users are redirected to login (via handle_no_permission).
    Authenticated non-@dimagi.com users receive a 403 PermissionDenied.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        email = getattr(request.user, "email", "") or ""
        if not email.endswith(DIMAGI_EMAIL_DOMAIN):
            raise PermissionDenied("This report is restricted to Dimagi staff.")
        return super().dispatch(request, *args, **kwargs)


class AuditOfAuditsView(LoginRequiredMixin, DimagiUserRequiredMixin, TemplateView):
    """
    Cross-opportunity admin report of all workflow runs and their audit sessions.

    Fetches data from the production Connect API without opportunity scoping,
    so all runs across all opportunities are included. Restricted to @dimagi.com
    users only. Supports optional ?template_type= GET filter.
    """

    template_name = "custom_analysis/audit_of_audits/report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        labs_oauth = self.request.session.get("labs_oauth", {})
        access_token = labs_oauth.get("access_token")

        if not access_token:
            context["error"] = "No OAuth token found. Please log in to Connect Labs first."
            context["rows"] = []
            context["total_runs"] = 0
            context["bulk_image_run_count"] = 0
            context["completed_run_count"] = 0
            context["filter_type"] = ""
            context["user_email"] = getattr(self.request.user, "email", "")
            return context

        rows = []
        error = None

        try:
            with AuditOfAuditsDataAccess(access_token=access_token) as da:
                rows = da.build_report_data()
        except LabsAPIError as e:
            logger.error("[AuditOfAudits] API error: %s", e, exc_info=True)
            error = f"Failed to load data from Connect API: {e}"
        except Exception as e:
            logger.error("[AuditOfAudits] Unexpected error: %s", e, exc_info=True)
            error = "An unexpected error occurred while loading the report."

        # Apply optional template_type filter from GET params
        filter_type = self.request.GET.get("template_type", "").strip()
        filtered_rows = [r for r in rows if r["template_type"] == filter_type] if filter_type else rows

        # Collect unique template types for the filter dropdown
        all_template_types = sorted({r["template_type"] for r in rows if r["template_type"]})

        context.update(
            {
                "rows": filtered_rows,
                "total_runs": len(rows),
                "bulk_image_run_count": sum(1 for r in rows if r["template_type"] == "bulk_image_audit"),
                "completed_run_count": sum(1 for r in rows if r["status"] == "completed"),
                "filter_type": filter_type,
                "all_template_types": all_template_types,
                "user_email": getattr(self.request.user, "email", ""),
                "error": error,
            }
        )
        return context
