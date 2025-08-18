import django_tables2 as tables
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from commcare_connect.solicitations.models import Solicitation, SolicitationResponse
from commcare_connect.utils.tables import OrgContextTable


class SolicitationResponseTable(OrgContextTable):
    """Table for displaying solicitation responses in program manager interface"""

    def __init__(self, *args, **kwargs):
        self.program_pk = kwargs.pop("program_pk", None)
        super().__init__(*args, **kwargs)

    organization = tables.Column(accessor="organization.name", verbose_name="Organization")
    submitted_by = tables.Column(accessor="submitted_by", verbose_name="Submitted By")
    status = tables.Column(verbose_name="Status")
    submission_date = tables.Column(accessor="submission_date", verbose_name="Submission Date")
    review_status = tables.Column(empty_values=(), verbose_name="Review Status", orderable=False)
    actions = tables.Column(empty_values=(), verbose_name="Actions", orderable=False)

    class Meta:
        model = SolicitationResponse
        fields = ("organization", "submitted_by", "status", "submission_date", "review_status", "actions")
        sequence = ("organization", "submitted_by", "status", "submission_date", "review_status", "actions")
        order_by = ("-submission_date",)

    def render_organization(self, value, record):
        """Render organization name with file attachment info"""
        html = f'<div class="font-medium">{value}</div>'
        if hasattr(record, "file_attachments") and record.file_attachments.exists():
            count = record.file_attachments.count()
            html += (
                f'<div class="text-gray-500 text-xs">'
                f'<i class="fa-solid fa-paperclip mr-1"></i>'
                f'{count} attachment{"s" if count != 1 else ""}</div>'
            )

        return format_html(
            (
                '<div class="flex text-sm font-normal truncate text-brand-deep-purple '
                'overflow-clip overflow-ellipsis justify-start text-wrap">{}</div>'
            ),
            mark_safe(html),
        )

    def render_submitted_by(self, value, record):
        """Render submitted by user info"""
        name = value.get_full_name() or value.email
        html = f"<div>{name}</div>" f'<div class="text-gray-500 text-xs">{value.email}</div>'

        return format_html(
            (
                '<div class="flex text-sm font-normal truncate text-brand-deep-purple '
                'overflow-clip overflow-ellipsis justify-start">{}</div>'
            ),
            mark_safe(html),
        )

    def render_status(self, value, record):
        """Render status badge similar to opportunities table"""
        if value == "submitted":
            badge_class = "badge badge-sm bg-slate-100 text-slate-400"
        elif value == "under_review":
            badge_class = "badge badge-sm bg-orange-600/20 text-orange-600"
        elif value == "accepted":
            badge_class = "badge badge-sm bg-green-600/20 text-green-600"
        elif value == "rejected":
            badge_class = "badge badge-sm bg-red-600/20 text-red-600"
        else:
            badge_class = "badge badge-sm bg-slate-100 text-slate-400"

        return format_html(
            (
                '<div class="flex justify-start text-sm font-normal truncate '
                'text-brand-deep-purple overflow-clip overflow-ellipsis">'
                '  <span class="{}">{}</span>'
                "</div>"
            ),
            badge_class,
            record.get_status_display(),
        )

    def render_submission_date(self, value):
        """Render submission date in consistent format"""
        formatted_date = value.strftime("%d-%b-%Y %H:%M") if value else "—"
        return format_html(
            (
                '<div class="flex text-sm font-normal truncate text-brand-deep-purple '
                'overflow-clip overflow-ellipsis justify-start">{}</div>'
            ),
            formatted_date,
        )

    def render_review_status(self, record):
        """Render review status with score and recommendation"""
        if record.reviews.exists():
            latest_review = record.reviews.first()
            html_parts = []

            if latest_review.score:
                html_parts.append(
                    f'<span class="badge badge-sm bg-blue-600/20 text-blue-600 mr-2">{latest_review.score}/100</span>'
                )

            if latest_review.recommendation:
                html_parts.append(f'<span class="text-xs">{latest_review.get_recommendation_display()}</span>')

            html = "".join(html_parts) if html_parts else '<span class="text-gray-400">Reviewed</span>'
        else:
            html = '<span class="text-gray-400">Not reviewed</span>'

        return format_html(
            (
                '<div class="flex text-sm font-normal truncate text-brand-deep-purple '
                'overflow-clip overflow-ellipsis justify-start">{}</div>'
            ),
            mark_safe(html),
        )

    def render_actions(self, record):
        """Render action links"""
        url = reverse(
            "org_solicitations:program_response_review",
            kwargs={"org_slug": self.org_slug, "pk": self.program_pk, "response_pk": record.pk},
        )

        return format_html(
            (
                '<div class="flex text-sm font-normal truncate text-brand-deep-purple '
                'overflow-clip overflow-ellipsis justify-start">'
                '  <a href="{}" class="text-brand-indigo hover:text-brand-deep-purple">Review</a>'
                "</div>"
            ),
            url,
        )


class SolicitationTable(OrgContextTable):
    """Table for displaying solicitations in admin overview and public views"""

    def __init__(self, *args, **kwargs):
        self.show_program_org = kwargs.pop("show_program_org", True)
        super().__init__(*args, **kwargs)

        # Hide program_organization column for program dashboard
        if not self.show_program_org:
            self.columns.hide("program_organization")

    title = tables.Column(verbose_name="Solicitation")
    program_organization = tables.Column(empty_values=(), verbose_name="Program & Organization", orderable=False)
    solicitation_type = tables.Column(verbose_name="Type")
    status = tables.Column(verbose_name="Status")
    date_created = tables.Column(verbose_name="Published")
    application_deadline = tables.Column(verbose_name="Deadline")
    response_statistics = tables.Column(empty_values=(), verbose_name="Response Statistics", orderable=False)
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
            "response_statistics",
            "actions",
        )
        sequence = (
            "title",
            "program_organization",
            "solicitation_type",
            "status",
            "date_created",
            "application_deadline",
            "response_statistics",
            "actions",
        )
        order_by = ("-date_created",)

    def render_title(self, value, record):
        """Render solicitation title"""
        return format_html(
            (
                '<div class="flex text-sm font-normal truncate text-brand-deep-purple '
                'overflow-clip overflow-ellipsis justify-start text-wrap">'
                '  <div class="font-medium">{}</div>'
                "</div>"
            ),
            value,
        )

    def render_program_organization(self, record):
        """Render program name and organization"""
        html = f'<div class="font-medium">{record.program.name}</div>'
        html += f'<div class="text-gray-500 text-xs">{record.program.organization.name}</div>'

        return format_html(
            (
                '<div class="flex text-sm font-normal truncate text-brand-deep-purple '
                'overflow-clip overflow-ellipsis justify-start">{}</div>'
            ),
            mark_safe(html),
        )

    def render_solicitation_type(self, value, record):
        """Render type badge similar to opportunities table"""
        if value == "eoi":
            badge_class = "badge badge-sm bg-purple-600/20 text-purple-600"
            text = "Expression of Interest"
        else:
            badge_class = "badge badge-sm bg-orange-600/20 text-orange-600"
            text = "Request for Proposals"

        return format_html(
            (
                '<div class="flex justify-start text-sm font-normal truncate '
                'text-brand-deep-purple overflow-clip overflow-ellipsis">'
                '  <span class="{}">{}</span>'
                "</div>"
            ),
            badge_class,
            text,
        )

    def render_status(self, value, record):
        """Render status badge similar to opportunities table"""
        if value == "active":
            badge_class = "badge badge-sm bg-green-600/20 text-green-600"
        elif value == "draft":
            badge_class = "badge badge-sm bg-slate-100 text-slate-400"
        elif value == "completed":
            badge_class = "badge badge-sm bg-blue-600/20 text-blue-600"
        else:  # closed
            badge_class = "badge badge-sm bg-red-600/20 text-red-600"

        return format_html(
            (
                '<div class="flex justify-start text-sm font-normal truncate '
                'text-brand-deep-purple overflow-clip overflow-ellipsis">'
                '  <span class="{}">{}</span>'
                "</div>"
            ),
            badge_class,
            record.get_status_display(),
        )

    def render_date_created(self, value):
        """Render published date in consistent format"""
        formatted_date = value.strftime("%b %d, %Y") if value else "—"
        return format_html(
            (
                '<div class="flex text-sm font-normal truncate text-brand-deep-purple '
                'overflow-clip overflow-ellipsis justify-start">{}</div>'
            ),
            formatted_date,
        )

    def render_application_deadline(self, value):
        """Render deadline in consistent format"""
        formatted_date = value.strftime("%d-%b-%Y") if value else "—"
        return format_html(
            (
                '<div class="flex text-sm font-normal truncate text-brand-deep-purple '
                'overflow-clip overflow-ellipsis justify-start">{}</div>'
            ),
            formatted_date,
        )

    def render_response_statistics(self, record):
        """Render response statistics with colored dots"""
        # Get the annotated counts from the queryset
        total = getattr(record, "total_responses", 0)
        under_review = getattr(record, "under_review_count", 0)
        accepted = getattr(record, "accepted_count", 0)
        rejected = getattr(record, "rejected_count", 0)

        html_parts = [
            (
                f'<div class="flex items-center">'
                f'<div class="w-2 h-2 bg-blue-500 rounded-full mr-1"></div>'
                f'<span class="text-xs text-gray-600">{total}</span></div>'
            ),
            (
                f'<div class="flex items-center">'
                f'<div class="w-2 h-2 bg-yellow-500 rounded-full mr-1"></div>'
                f'<span class="text-xs text-gray-600">{under_review}</span></div>'
            ),
            (
                f'<div class="flex items-center">'
                f'<div class="w-2 h-2 bg-green-500 rounded-full mr-1"></div>'
                f'<span class="text-xs text-gray-600">{accepted}</span></div>'
            ),
            (
                f'<div class="flex items-center">'
                f'<div class="w-2 h-2 bg-red-500 rounded-full mr-1"></div>'
                f'<span class="text-xs text-gray-600">{rejected}</span></div>'
            ),
        ]

        return format_html('<div class="flex items-center space-x-4">{}</div>', mark_safe("".join(html_parts)))

    def render_actions(self, record):
        """Render action links"""
        public_url = reverse("solicitations:detail", kwargs={"pk": record.pk})

        actions = []

        # Public view link
        actions.append(
            f'<a href="{public_url}" class="text-brand-indigo hover:text-brand-deep-purple" '
            f'target="_blank" title="View Public Page">'
            f'<i class="fa-solid fa-external-link-alt"></i></a>'
        )

        # For admin overview, we might not have org context, so handle gracefully
        if hasattr(record, "program") and hasattr(record.program, "organization"):
            # Edit link (only for program managers)
            edit_url = reverse(
                "org_solicitations:program_solicitation_edit",
                kwargs={
                    "org_slug": record.program.organization.slug,
                    "program_pk": record.program.pk,
                    "pk": record.pk,
                },
            )
            actions.append(
                f'<a href="{edit_url}" class="text-brand-indigo hover:text-brand-deep-purple" '
                f'title="Edit Solicitation"><i class="fa-solid fa-edit"></i></a>'
            )

            # Responses link
            responses_url = reverse(
                "org_solicitations:program_response_list",
                kwargs={
                    "org_slug": record.program.organization.slug,
                    "pk": record.program.pk,
                    "solicitation_pk": record.pk,
                },
            )
            actions.append(
                f'<a href="{responses_url}" class="text-brand-indigo hover:text-brand-deep-purple" '
                f'title="View Responses"><i class="fa-solid fa-inbox"></i></a>'
            )

        return format_html('<div class="flex items-center space-x-2">{}</div>', mark_safe("".join(actions)))
