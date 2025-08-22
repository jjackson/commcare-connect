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
    """Get CSS class for status badges"""
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
    }
    return status_classes.get(status, "badge badge-sm bg-slate-100 text-slate-400")


def get_type_badge_info(solicitation_type):
    """Get badge info for solicitation types"""
    if solicitation_type == "eoi":
        return "EOI", "badge badge-sm bg-purple-600/20 text-purple-600"
    else:
        return "RFP", "badge badge-sm bg-orange-600/20 text-orange-600"


def render_status_badge(value, display_text=None):
    """Render a status badge"""
    badge_class = get_status_badge_class(value)
    text = display_text or value.replace("_", " ").title()
    return format_html('<span class="{}">{}</span>', badge_class, text)


def render_two_line_text(title, subtitle=None):
    """Render two-line text content"""
    if subtitle:
        return format_html(
            '<div><div class="font-medium">{}</div><div class="text-xs text-gray-500">{}</div></div>', title, subtitle
        )
    return format_html('<div class="font-medium">{}</div>', title)


def render_attachment_info(record):
    """Render file attachment count if present"""
    if hasattr(record, "file_attachments") and record.file_attachments.exists():
        count = record.file_attachments.count()
        return f'{count} attachment{"s" if count != 1 else ""}'
    return None


# =============================================================================
# Table Classes
# =============================================================================


class SolicitationResponseTable(OrgContextTable):
    """Table for displaying solicitation responses in program manager interface"""

    def __init__(self, *args, **kwargs):
        self.program_pk = kwargs.pop("program_pk", None)
        super().__init__(*args, **kwargs)

    organization = tables.Column(accessor="organization.name", verbose_name="Organization")
    status = tables.Column(verbose_name="Status")
    review_status = tables.Column(empty_values=(), verbose_name="Review Status", orderable=False)
    actions = tables.Column(empty_values=(), verbose_name="Actions", orderable=False)

    class Meta:
        model = SolicitationResponse
        fields = ("organization", "submitted_by", "status", "submission_date", "review_status", "actions")
        sequence = ("organization", "submitted_by", "status", "submission_date", "review_status", "actions")
        labels = {
            "submitted_by": "Submitted By",
            "submission_date": "Submission Date",
        }
        order_by = ("-submission_date",)

    def render_organization(self, value, record):
        """Render organization name with file attachment info"""
        attachment_info = render_attachment_info(record)
        return render_two_line_text(value, attachment_info)

    def render_submitted_by(self, value, record):
        """Render submitted by user info"""
        name = value.get_full_name() or value.email
        return render_two_line_text(name, value.email)

    def render_status(self, value, record):
        """Render status badge"""
        return render_status_badge(value, record.get_status_display())

    def render_review_status(self, record):
        """Render review status with score and recommendation"""
        if not record.reviews.exists():
            return format_html('<span class="text-gray-400">Not reviewed</span>')

        latest_review = record.reviews.first()
        parts = []

        if latest_review.score:
            parts.append(
                format_html(
                    '<span class="badge badge-sm bg-blue-600/20 text-blue-600">{}/100</span>', latest_review.score
                )
            )

        if latest_review.recommendation:
            parts.append(format_html('<span class="text-xs">{}</span>', latest_review.get_recommendation_display()))

        return mark_safe(" ".join(parts)) if parts else format_html('<span class="text-gray-400">Reviewed</span>')

    def render_actions(self, record):
        """Render action links"""
        url = reverse(
            "org_solicitations:program_response_review",
            kwargs={"org_slug": self.org_slug, "pk": self.program_pk, "response_pk": record.pk},
        )
        return format_html('<a href="{}" class="text-brand-indigo hover:text-brand-deep-purple">Review</a>', url)


class SolicitationTable(OrgContextTable):
    """Table for displaying solicitations in admin overview and public views"""

    def __init__(self, *args, **kwargs):
        self.show_program_org = kwargs.pop("show_program_org", True)
        super().__init__(*args, **kwargs)

        # Hide program_organization column for program dashboard
        if not self.show_program_org:
            self.columns.hide("program_organization")

    program_organization = tables.Column(empty_values=(), verbose_name="Program & Organization", orderable=False)
    total = tables.Column(empty_values=(), verbose_name="Total", orderable=False)
    reviewed = tables.Column(empty_values=(), verbose_name="Reviewed", orderable=False)
    actions = tables.Column(empty_values=(), verbose_name="Actions", orderable=False)

    class Meta:
        model = Solicitation
        fields = (
            "title",
            "program_organization",
            "solicitation_type",
            "status",
            "date_created",
            "application_deadline",
            "total",
            "reviewed",
            "actions",
        )
        sequence = (
            "title",
            "program_organization",
            "solicitation_type",
            "status",
            "date_created",
            "application_deadline",
            "total",
            "reviewed",
            "actions",
        )
        labels = {
            "title": "Solicitation",
            "solicitation_type": "Type",
            "date_created": "Published",
            "application_deadline": "Deadline",
        }
        order_by = ("-date_created",)

    def render_title(self, value, record):
        """Render solicitation title"""
        return format_html('<div class="font-medium">{}</div>', value)

    def render_program_organization(self, record):
        """Render program name and organization"""
        return render_two_line_text(record.program.name, record.program.organization.name)

    def render_solicitation_type(self, value, record):
        """Render type badge"""
        text, badge_class = get_type_badge_info(value)
        return format_html('<span class="{}">{}</span>', badge_class, text)

    def render_status(self, value, record):
        """Render status badge"""
        return render_status_badge(value, record.get_status_display())

    def render_date_created(self, value):
        """Render published date"""
        return value.strftime("%b %d, %Y") if value else "—"

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
        if hasattr(self, "org_slug") and self.org_slug:
            public_url = reverse("org_solicitations:detail", kwargs={"org_slug": self.org_slug, "pk": record.pk})
        else:
            public_url = reverse("solicitations:detail", kwargs={"pk": record.pk})

        actions.append(
            format_html(
                '<a href="{}" class="text-brand-indigo hover:text-brand-deep-purple" target="_blank" '
                'title="View Public Page">'
                '<i class="fa-solid fa-external-link-alt"></i></a>',
                public_url,
            )
        )

        # Management actions (if user has permissions)
        if hasattr(record, "program") and hasattr(record.program, "organization"):
            org_slug = getattr(self, "org_slug", None) or record.program.organization.slug

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
                    format_html(
                        '<a href="{}" class="text-brand-indigo hover:text-brand-deep-purple" '
                        'title="Edit Solicitation">'
                        '<i class="fa-solid fa-edit"></i></a>',
                        edit_url,
                    ),
                    format_html(
                        '<a href="{}" class="text-brand-indigo hover:text-brand-deep-purple" title="View Responses">'
                        '<i class="fa-solid fa-inbox"></i></a>',
                        responses_url,
                    ),
                ]
            )

        return format_html('<div class="flex items-center space-x-2">{}</div>', mark_safe("".join(actions)))


class UserSolicitationResponseTable(tables.Table):
    """Table for displaying user's own solicitation responses"""

    solicitation = tables.Column(accessor="solicitation.title", verbose_name="Solicitation")
    program = tables.Column(accessor="solicitation.program.name", verbose_name="Program")
    status = tables.Column(verbose_name="Status")
    actions = tables.Column(empty_values=(), verbose_name="Actions", orderable=False)

    class Meta:
        model = SolicitationResponse
        fields = ("solicitation", "program", "status", "submission_date", "actions")
        sequence = ("solicitation", "program", "status", "submission_date", "actions")
        labels = {
            "submission_date": "Submitted",
        }
        order_by = ("-date_modified",)

    def render_solicitation(self, value, record):
        """Render solicitation title with type badge"""
        solicitation = record.solicitation
        type_text, badge_class = get_type_badge_info(solicitation.solicitation_type)
        badge_html = format_html('<span class="{}">{}</span>', badge_class, type_text)
        return render_two_line_text(value, badge_html)

    def render_program(self, value, record):
        """Render program name with organization"""
        return render_two_line_text(value, record.solicitation.program.organization.name)

    def render_status(self, value, record):
        """Render status badge"""
        return render_status_badge(value, record.get_status_display())

    def render_actions(self, record):
        """Render action links"""
        actions = []

        # Status-specific action
        if record.status == "draft":
            edit_url = reverse("solicitations:user_response_edit", kwargs={"pk": record.pk})
            actions.append(
                format_html(
                    '<a href="{}" class="text-brand-indigo hover:text-brand-deep-purple" title="Edit Draft">'
                    '<i class="fa-solid fa-edit"></i></a>',
                    edit_url,
                )
            )
        elif record.status == "submitted":
            view_url = reverse("solicitations:user_response_detail", kwargs={"pk": record.pk})
            actions.append(
                format_html(
                    '<a href="{}" class="text-brand-indigo hover:text-brand-deep-purple" title="View Response">'
                    '<i class="fa-solid fa-eye"></i></a>',
                    view_url,
                )
            )

        # View solicitation (always available)
        detail_url = reverse("solicitations:detail", kwargs={"pk": record.solicitation.pk})
        actions.append(
            format_html(
                '<a href="{}" class="text-brand-indigo hover:text-brand-deep-purple" '
                'title="View Solicitation" target="_blank">'
                '<i class="fa-solid fa-external-link-alt"></i></a>',
                detail_url,
            )
        )

        return format_html('<div class="flex items-center space-x-2">{}</div>', mark_safe("".join(actions)))


class UserSolicitationReviewTable(tables.Table):
    """Table for displaying user's own solicitation reviews"""

    response_organization = tables.Column(accessor="response.organization.name", verbose_name="Organization")
    solicitation = tables.Column(accessor="response.solicitation.title", verbose_name="Solicitation")
    recommendation = tables.Column(verbose_name="Recommendation")
    actions = tables.Column(empty_values=(), verbose_name="Actions", orderable=False)

    class Meta:
        model = SolicitationReview
        fields = ("response_organization", "solicitation", "recommendation", "score", "review_date", "actions")
        labels = {
            "review_date": "Review Date",
        }
        order_by = ("-review_date",)

    def render_response_organization(self, value, record):
        """Render organization name with status info"""
        status_info = f"Status: {record.response.status.title()}"
        return render_two_line_text(value, status_info)

    def render_solicitation(self, value, record):
        """Render solicitation title with program"""
        return render_two_line_text(value, record.response.solicitation.program.name)

    def render_recommendation(self, value, record):
        """Render recommendation badge"""
        if not value:
            return "—"
        return render_status_badge(value, record.get_recommendation_display())

    def render_score(self, value):
        """Render score"""
        return f"{value}/100" if value else "—"

    def render_review_date(self, value):
        """Render review date"""
        return value.strftime("%d-%b-%Y") if value else "—"

    def render_actions(self, record):
        """Render action links"""
        detail_url = reverse("solicitations:detail", kwargs={"pk": record.response.solicitation.pk})
        return format_html(
            '<a href="{}" class="text-brand-indigo hover:text-brand-deep-purple" '
            'title="View Solicitation" target="_blank">'
            '<i class="fa-solid fa-external-link-alt"></i></a>',
            detail_url,
        )
