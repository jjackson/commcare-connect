import django_tables2 as tables
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from commcare_connect.solicitations.models import Solicitation, SolicitationResponse, SolicitationReview
from commcare_connect.utils.tables import OrgContextTable

# =============================================================================
# Utility Functions
# =============================================================================


def get_status_badge_class(status):
    """Get CSS class for all badge types (statuses, recommendations, solicitation types)"""
    status_classes = {
        # Response statuses
        "draft": "badge badge-sm bg-slate-100 text-slate-400",
        "submitted": "badge badge-sm bg-blue-600/20 text-blue-600",
        # Solicitation statuses
        "active": "badge badge-sm bg-green-600/20 text-green-600",
        "closed": "badge badge-sm bg-red-600/20 text-red-600",
        # Review recommendations
        "recommended": "badge badge-sm bg-green-600/20 text-green-600",
        "not_recommended": "badge badge-sm bg-red-600/20 text-red-600",
        "neutral": "badge badge-sm bg-orange-600/20 text-orange-600",
        # Solicitation types
        "eoi": "badge badge-sm bg-green-600/20 text-green-600",
        "rfp": "badge badge-sm bg-orange-600/20 text-orange-600",
    }
    return status_classes.get(status, "badge badge-sm bg-slate-100 text-slate-400")


def render_text_with_badge(title, solicitation_type):
    """Render solicitation title with type badge at the end"""
    badge_class = get_status_badge_class(solicitation_type)
    badge_text = solicitation_type.upper()
    return format_html(
        '<div class="break-words max-w-xs">{} <span class="{}">{}</span></div>', title, badge_class, badge_text
    )


def render_two_line_text(title, subtitle=None):
    """Render two-line text content"""
    if subtitle:
        return format_html(
            '<div><div class="font-medium">{}</div><div class="text-xs text-gray-500">{}</div></div>',
            title,
            mark_safe(subtitle) if isinstance(subtitle, str) and ("<" in subtitle and ">" in subtitle) else subtitle,
        )
    return format_html('<div class="font-medium">{}</div>', title)


def create_action_link(url, icon, title, target="_self"):
    """Create a standardized action link"""
    target_attr = f' target="{target}"' if target != "_self" else ""
    return (
        f'<a href="{url}" class="text-brand-indigo hover:text-brand-deep-purple" title="{title}"{target_attr}>'
        f'<i class="fa-solid {icon}"></i></a>'
    )


# =============================================================================
# Program  Table - shown when user is in admin or user mode for dashboard
# =============================================================================
class ProgramTable(tables.Table):
    """Table for displaying programs where user can create solicitations"""

    name = tables.Column(verbose_name="Program Name")
    organization = tables.Column(accessor="organization__name")
    active_solicitations = tables.Column(empty_values=(), verbose_name="Active Solicitations", orderable=False)
    total_responses = tables.Column(empty_values=(), verbose_name="Total Responses", orderable=False)
    actions = tables.Column(empty_values=(), verbose_name="Actions", orderable=False)

    class Meta:
        model = None  # Will be set dynamically to Program model
        fields = ("name", "organization", "active_solicitations", "total_responses", "actions")
        order_by = ("name",)

    def __init__(self, *args, **kwargs):
        self.org_slug = kwargs.pop("org_slug", "")
        super().__init__(*args, **kwargs)

    def render_name(self, value, record):
        """Render program name with description"""
        description = getattr(record, "description", "") or "No description available"
        return render_two_line_text(value, description[:50] + "..." if len(description) > 50 else description)

    def render_organization(self, value, record):
        """Render organization name"""
        return render_two_line_text(value, "Program Manager Organization")

    def render_active_solicitations(self, record):
        """Render count of active solicitations for this program"""
        return getattr(record, "active_solicitations_count", 0)

    def render_total_responses(self, record):
        """Render total responses across all solicitations for this program"""
        return getattr(record, "total_responses_count", 0)

    def render_actions(self, record):
        """Render action links for program management"""
        # Create new solicitation
        create_url = reverse(
            "org_solicitations:program_solicitation_create",
            kwargs={
                "org_slug": record.organization.slug,
                "program_pk": record.pk,
            },
        )

        # View program dashboard
        dashboard_url = reverse(
            "org_solicitations:program_dashboard",
            kwargs={
                "org_slug": record.organization.slug,
                "pk": record.pk,
            },
        )

        actions = [
            create_action_link(create_url, "fa-plus-circle", "Create Solicitation"),
            create_action_link(dashboard_url, "fa-eye", "View Dashboard"),
        ]

        return format_html('<div class="flex items-center space-x-3">{}</div>', mark_safe("".join(actions)))


# =============================================================================
# Table Classes
# =============================================================================
class SolicitationTable(OrgContextTable):
    """Table for displaying solicitations in admin overview and public views"""

    def __init__(self, *args, **kwargs):
        self.show_program_org = kwargs.pop("show_program_org", True)
        super().__init__(*args, **kwargs)

        # Hide program_org column for program dashboard
        if not self.show_program_org:
            self.columns.hide("program_org")

    program_org = tables.Column(empty_values=(), verbose_name="Program & Org", orderable=False)
    total = tables.Column(empty_values=(), verbose_name="Total", orderable=False)
    reviewed = tables.Column(empty_values=(), verbose_name="Reviewed", orderable=False)
    actions = tables.Column(empty_values=(), verbose_name="Actions", orderable=False)

    class Meta:
        model = Solicitation
        fields = ("title", "program_org", "status", "application_deadline", "total", "reviewed", "actions")
        order_by = ("-application_deadline",)

    def render_title(self, value, record):
        """Render solicitation title with type badge"""
        return render_text_with_badge(value, record.solicitation_type)

    def render_program_org(self, record):
        """Render program name and organization"""
        return render_two_line_text(record.program.name, record.program.organization.name)

    def render_application_deadline(self, value):
        """Render deadline"""
        return value.strftime("%d-%b-%Y") if value else "—"

    def render_total(self, record):
        """Render total responses count"""
        total = getattr(record, "total_responses", 0)
        return format_html('<span class="font-medium">{}</span>', total)

    def render_reviewed(self, record):
        """Render reviewed responses count"""
        # With simplified status, this shows total submitted responses
        submitted = getattr(record, "submitted_count", 0)
        return format_html('<span class="font-medium">{}</span>', submitted)

    def render_actions(self, record):
        """Render action links"""
        actions = []

        # Public view link
        public_url = reverse("solicitations:detail", kwargs={"pk": record.pk})
        actions.append(create_action_link(public_url, "fa-external-link-alt", "View Public Page", target="_blank"))

        # Management actions (if user has permissions)
        if hasattr(record, "program") and hasattr(record.program, "organization"):
            org_slug = record.program.organization.slug

            edit_url = reverse(
                "org_solicitations:program_solicitation_edit",
                kwargs={"org_slug": org_slug, "program_pk": record.program.pk, "pk": record.pk},
            )
            responses_url = reverse(
                "org_solicitations:program_response_list",
                kwargs={"org_slug": org_slug, "pk": record.program.pk, "solicitation_pk": record.pk},
            )

            actions.extend(
                [
                    create_action_link(edit_url, "fa-edit", "Edit Solicitation"),
                    create_action_link(responses_url, "fa-inbox", "View Responses"),
                ]
            )

        return format_html('<div class="flex items-center space-x-2">{}</div>', mark_safe("".join(actions)))


class SolicitationResponseTable(OrgContextTable):
    """Unified table for displaying solicitation responses across all dashboard modes"""

    def __init__(self, *args, **kwargs):
        self.mode = kwargs.pop("mode", "user")  # 'admin', 'program', 'user'
        self.program_pk = kwargs.pop("program_pk", None)
        super().__init__(*args, **kwargs)

    solicitation = tables.Column(accessor="solicitation__title", verbose_name="Solicitation")
    program_org = tables.Column(empty_values=(), verbose_name="Program & Org", orderable=False)
    # submitted_by = tables.Column()
    # status = tables.Column()
    last_edit_date = tables.Column(accessor="submission_date", verbose_name="Last Edited")
    actions = tables.Column(empty_values=(), verbose_name="Actions", orderable=False)

    class Meta:
        model = SolicitationResponse
        fields = ("solicitation", "program_org", "submitted_by", "status", "last_edit_date", "actions")
        order_by = ("-last_edit_date",)

    def render_solicitation(self, value, record):
        """Render solicitation title with type badge"""
        return render_text_with_badge(value, record.solicitation.solicitation_type)

    def render_program_org(self, record):
        """Render program name with organization"""
        program = record.solicitation.program
        return render_two_line_text(program.name, program.organization.name)

    def render_last_edit_date(self, value):
        """Render last edit date and time on separate lines"""
        if not value:
            return "—"
        date_str = value.strftime("%d-%b-%Y")
        time_str = value.strftime("%I:%M %p").lower()
        return render_two_line_text(date_str, time_str)

    def render_submitted_by(self, value, record):
        """Render submitted by user info"""
        if not value:
            return "—"
        name = value.get_full_name() or value.email
        return render_two_line_text(name, value.email)

    def render_status(self, value, record):
        """Render status badge"""
        badge_class = get_status_badge_class(value)
        return format_html('<span class="{}">{}</span>', badge_class, record.get_status_display())

    def render_actions(self, record):
        """Render action links based on mode"""
        if self.mode == "admin":
            url = f"/admin/solicitations/solicitationresponse/{record.pk}/change/"
            action = create_action_link(url, "fa-eye", "View in Admin")
        elif self.mode == "program":
            url = reverse(
                "org_solicitations:program_response_review",
                kwargs={"org_slug": self.org_slug, "pk": self.program_pk, "response_pk": record.pk},
            )
            action = create_action_link(url, "fa-pen-to-square", "Review Response")
        else:
            # User mode - Edit or View response
            if record.status == SolicitationResponse.Status.DRAFT:
                url = reverse(
                    "org_solicitations:user_response_edit",
                    kwargs={"org_slug": self.org_slug, "pk": record.pk},
                )
                action = create_action_link(url, "fa-pen-to-square", "Edit Response")
            else:
                url = reverse(
                    "org_solicitations:user_response_detail",
                    kwargs={"org_slug": self.org_slug, "pk": record.pk},
                )
                action = create_action_link(url, "fa-eye", "View Response")

        return format_html('<div class="flex items-center space-x-3">{}</div>', mark_safe(action))


class SolicitationReviewTable(tables.Table):
    """Unified table for displaying solicitation reviews across all dashboard modes"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    solicitation = tables.Column(accessor="response.solicitation.title", verbose_name="Solicitation")
    submitting_org = tables.Column(empty_values=(), verbose_name="Submitting Org", orderable=False)
    actions = tables.Column(empty_values=(), verbose_name="Actions", orderable=False)

    class Meta:
        model = SolicitationReview
        fields = ("solicitation", "submitting_org", "recommendation", "score", "review_date", "actions")
        order_by = ("-review_date",)

    def render_solicitation(self, value, record):
        """Render solicitation title with type badge"""
        return render_text_with_badge(value, record.response.solicitation.solicitation_type)

    def render_submitting_org(self, record):
        """Render submitting organization with response status"""
        org_name = record.response.organization.name
        status_info = f"Status: {record.response.status.title()}"
        return render_two_line_text(org_name, status_info)

    def render_recommendation(self, value, record):
        """Render recommendation badge"""
        if not value:
            return "—"
        badge_class = get_status_badge_class(value)
        return format_html('<span class="{}">{}</span>', badge_class, record.get_recommendation_display())

    def render_review_date(self, value):
        """Render review date"""
        return value.strftime("%d-%b-%Y") if value else "—"

    def render_actions(self, record):
        """Render action links - view review (permissions handled by the page)"""
        # Always link to view the review - the page will handle edit permissions
        url = reverse(
            "org_solicitations:user_response_detail",
            kwargs={
                "org_slug": record.response.organization.slug,
                "pk": record.response.pk,
            },
        )
        action = create_action_link(url, "fa-eye", "View Review")
        return format_html('<div class="flex items-center space-x-3">{}</div>', mark_safe(action))
