"""
Views for the Audit of Audits admin report.

Access is restricted to users with @dimagi.com email addresses via
DimagiUserRequiredMixin. This report is intentionally not visible to
normal users (Network Managers, FLWs, etc.) — the tile is also hidden
from the overview page for non-@dimagi.com users.
"""

import logging

from django.conf import settings
from django.contrib.auth.mixins import AccessMixin, LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.views.generic import TemplateView

from commcare_connect.labs.integrations.connect.api_client import LabsAPIError

from .data_access import AuditOfAuditsDataAccess

logger = logging.getLogger(__name__)

DIMAGI_EMAIL_DOMAIN = "@dimagi.com"


def _is_dimagi_user(user) -> bool:
    """
    Return True if the user is a Dimagi staff member.

    Two paths:
    1. Email-based: .email or .username ends with @dimagi.com (works when the
       OAuth profile contains the full email address).
    2. Allowlist-based: .username is in LABS_ADMIN_USERNAMES (works for Connect
       platform users whose OAuth profile returns a short username like 'matt'
       with no email address populated).
    """
    email = getattr(user, "email", "") or ""
    username = getattr(user, "username", "") or ""
    if email.endswith(DIMAGI_EMAIL_DOMAIN) or username.endswith(DIMAGI_EMAIL_DOMAIN):
        return True
    allowlist = getattr(settings, "LABS_ADMIN_USERNAMES", [])
    return bool(username and username in allowlist)


def _dimagi_display_name(user) -> str:
    """Return the best available identifier to display for the current user."""
    email = getattr(user, "email", "") or ""
    if email.endswith(DIMAGI_EMAIL_DOMAIN):
        return email
    username = getattr(user, "username", "") or ""
    return username or email


class DimagiUserRequiredMixin(AccessMixin):
    """
    Restricts view access to users with a @dimagi.com email or username.

    Checks both .email and .username because CommCare Connect OAuth profiles
    store the email address in the username field (e.g. mtheis@dimagi.com)
    while the .email field may be blank in the OAuth user_profile payload.

    Unauthenticated users are redirected to login (via handle_no_permission).
    Authenticated non-@dimagi.com users receive a 403 PermissionDenied.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not _is_dimagi_user(request.user):
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
            context["user_email"] = _dimagi_display_name(self.request.user)
            return context

        # Organization IDs (integers) — used for Phase 1 session queries.
        user_orgs: list[dict] = getattr(self.request.user, "organizations", []) or []
        organization_ids: list[int] = [
            o["id"] for o in user_orgs if isinstance(o.get("id"), int)
        ]

        # Opportunity IDs (integers) — used for Phase 2 run & definition queries.
        # Using ALL user opportunities (not just session-derived ones) ensures runs
        # without sessions yet are still surfaced in the report.
        user_opps: list[dict] = getattr(self.request.user, "opportunities", []) or []
        opportunity_ids: list[int] = [
            o["id"] for o in user_opps if isinstance(o.get("id"), int)
        ]

        # Opportunity name map — used to display "Opp Name : opp_id" in the report.
        # The OAuth opportunities list contains {"id": 956, "name": "EHA | CHC-Experiments | FP", ...}
        opp_name_map: dict[int, str] = {
            o["id"]: o.get("name", "") for o in user_opps if isinstance(o.get("id"), int)
        }

        logger.info(
            "[AuditOfAudits] User %s — %d orgs, %d opportunities",
            _dimagi_display_name(self.request.user),
            len(organization_ids),
            len(opportunity_ids),
        )

        rows = []
        error = None

        if not organization_ids and not opportunity_ids:
            error = "No organizations or opportunities found. Try refreshing your session via the Labs home page."

        try:
            with AuditOfAuditsDataAccess(
                access_token=access_token,
                organization_ids=organization_ids,
                opportunity_ids=opportunity_ids,
            ) as da:
                rows = da.build_report_data()

            # Annotate each row with the human-readable opportunity name
            for row in rows:
                opp_id = row.get("opportunity_id")
                row["opportunity_name"] = opp_name_map.get(opp_id, "") if opp_id else ""

        except LabsAPIError as e:
            logger.error("[AuditOfAudits] API error: %s", e, exc_info=True)
            error = f"Failed to load data from Connect API: {e}"
        except Exception as e:
            logger.error("[AuditOfAudits] Unexpected error: %s", e, exc_info=True)
            error = "An unexpected error occurred while loading the report."

        # filter_type is kept only to set the select's initial value on page load.
        # Actual filtering is done client-side in JS — no server round-trip needed.
        filter_type = self.request.GET.get("template_type", "").strip()

        # Collect unique template types for the filter dropdown
        all_template_types = sorted({r["template_type"] for r in rows if r["template_type"]})

        context.update(
            {
                "rows": rows,
                "total_runs": len(rows),
                "bulk_image_run_count": sum(1 for r in rows if r["template_type"] == "bulk_image_audit"),
                "completed_run_count": sum(1 for r in rows if r["status"] == "completed"),
                "filter_type": filter_type,
                "all_template_types": all_template_types,
                "user_email": _dimagi_display_name(self.request.user),
                "error": error,
            }
        )
        return context
