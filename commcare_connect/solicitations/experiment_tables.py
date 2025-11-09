"""
Django tables for ExperimentRecord-based solicitations.

These tables work with the proxy models (SolicitationRecord, ResponseRecord, ReviewRecord)
that use JSON data storage instead of traditional Django ORM models.
"""

import django_tables2 as tables
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from commcare_connect.solicitations.experiment_models import ResponseRecord, ReviewRecord, SolicitationRecord

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
        "approved": "badge badge-sm bg-green-600/20 text-green-600",
        "rejected": "badge badge-sm bg-red-600/20 text-red-600",
        "needs_revision": "badge badge-sm bg-orange-600/20 text-orange-600",
        "under_review": "badge badge-sm bg-violet-500/20 text-violet-500",
        # Solicitation types
        "eoi": "badge badge-sm bg-green-600/20 text-green-600",
        "rfp": "badge badge-sm bg-orange-600/20 text-orange-600",
    }
    return status_classes.get(status, "badge badge-sm bg-slate-100 text-slate-400")


def render_text_with_badge(title, solicitation_type):
    """Render solicitation title with type badge at the end"""
    badge_class = get_status_badge_class(solicitation_type)
    badge_text = solicitation_type.upper()
    return format_html('<div class="text-wrap">{} <span class="{}">{}</span></div>', title, badge_class, badge_text)


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
# Table Classes for ExperimentRecord Models
# =============================================================================


class SolicitationRecordTable(tables.Table):
    """
    Table for displaying solicitations using ExperimentRecord-based SolicitationRecord.

    Key differences from old SolicitationTable:
    - Uses proxy model properties (.title, .status, etc.) instead of model fields
    - No ForeignKey relationships - uses production IDs
    - Updated URL patterns for labs (no org_slug)
    """

    title = tables.Column(verbose_name="Title", orderable=True)
    status = tables.Column(verbose_name="Status", orderable=True)
    application_deadline = tables.Column(verbose_name="Deadline", orderable=True, empty_values=())
    total = tables.Column(empty_values=(), verbose_name="Responses", orderable=False)
    actions = tables.Column(empty_values=(), verbose_name="Actions", orderable=False)

    class Meta:
        model = SolicitationRecord
        fields = ("title", "status", "application_deadline", "total", "actions")
        order_by = ("-date_created",)
        template_name = "base_table.html"

    def render_title(self, value, record):
        """Render solicitation title with type badge"""
        return render_text_with_badge(record.title, record.solicitation_type)

    def render_status(self, value, record):
        """Render status with badge"""
        badge_class = get_status_badge_class(record.status)
        return format_html('<span class="{}">{}</span>', badge_class, record.status.capitalize())

    def render_application_deadline(self, value, record):
        """Render deadline from JSON data"""
        deadline = record.application_deadline
        if not deadline:
            return "—"

        # Handle both string and date objects
        if isinstance(deadline, str):
            from datetime import datetime

            try:
                deadline_date = datetime.fromisoformat(deadline).date()
                return deadline_date.strftime("%d-%b-%Y")
            except (ValueError, AttributeError):
                return deadline
        return deadline.strftime("%d-%b-%Y") if hasattr(deadline, "strftime") else str(deadline)

    def render_total(self, record):
        """Render total responses count"""
        # Count child responses
        total = record.children.filter(type="SolicitationResponse").count()
        return format_html('<span class="font-medium">{}</span>', total)

    def render_actions(self, record):
        """Render action links"""
        actions = []

        # Public view link
        public_url = reverse("solicitations:detail", kwargs={"pk": record.pk})
        actions.append(create_action_link(public_url, "fa-external-link-alt", "View Public Page", target="_blank"))

        # Edit link (labs URLs don't need org_slug)
        edit_url = reverse("solicitations:edit", kwargs={"pk": record.pk})
        actions.append(create_action_link(edit_url, "fa-edit", "Edit Solicitation"))

        return format_html('<div class="flex items-center space-x-2">{}</div>', mark_safe("".join(actions)))


class ResponseRecordTable(tables.Table):
    """
    Table for displaying responses using ExperimentRecord-based ResponseRecord.

    Key differences from old SolicitationResponseAndReviewTable:
    - Uses proxy model properties (.response_status, .responses, etc.)
    - Accesses parent solicitation via .parent relationship
    - Reviews accessed via .children relationship
    - No ForeignKey dependencies - uses production IDs
    """

    solicitation = tables.Column(verbose_name="Solicitation", orderable=False, empty_values=())
    status = tables.Column(verbose_name="Status", orderable=False, empty_values=())
    last_edited = tables.Column(accessor="date_modified", verbose_name="Last Edited", orderable=True)
    recommendation = tables.Column(empty_values=(), verbose_name="Recommendation", orderable=False)
    score = tables.Column(empty_values=(), verbose_name="Score", orderable=False)
    actions = tables.Column(empty_values=(), verbose_name="Actions", orderable=False)

    class Meta:
        model = ResponseRecord
        fields = ("solicitation", "status", "last_edited", "recommendation", "score", "actions")
        order_by = ("-date_modified",)
        template_name = "base_table.html"

    def render_solicitation(self, value, record):
        """Render solicitation title with type badge"""
        # Get parent solicitation and cast to SolicitationRecord proxy model
        if record.parent:
            # Cast ExperimentRecord to SolicitationRecord to access properties
            solicitation = SolicitationRecord.objects.get(pk=record.parent.pk)
            return render_text_with_badge(solicitation.title, solicitation.solicitation_type)
        return "—"

    def render_status(self, value, record):
        """Render response status with badge"""
        status = record.response_status
        badge_class = get_status_badge_class(status)
        return format_html('<span class="{}">{}</span>', badge_class, status.capitalize())

    def render_last_edited(self, value):
        """Render last edit date and time on separate lines"""
        if not value:
            return "—"
        date_str = value.strftime("%d-%b-%Y")
        time_str = value.strftime("%I:%M %p").lower()
        return render_two_line_text(date_str, time_str)

    def render_recommendation(self, record):
        """Render recommendation from review if it exists"""
        try:
            review_base = record.children.filter(type="SolicitationReview").first()
            if review_base:
                # Cast to ReviewRecord proxy to access properties
                review = ReviewRecord.objects.get(pk=review_base.pk)
                recommendation = review.recommendation
                if recommendation:
                    badge_class = get_status_badge_class(recommendation)
                    return format_html(
                        '<span class="{}">{}</span>', badge_class, recommendation.replace("_", " ").title()
                    )
        except Exception:
            pass
        return "—"

    def render_score(self, record):
        """Render score from review if it exists"""
        try:
            review_base = record.children.filter(type="SolicitationReview").first()
            if review_base:
                # Cast to ReviewRecord proxy to access properties
                review = ReviewRecord.objects.get(pk=review_base.pk)
                if review.score is not None:
                    return review.score
        except Exception:
            pass
        return "—"

    def render_actions(self, record):
        """Render action links"""
        actions = []

        # View response detail
        detail_url = reverse("solicitations:response_detail", kwargs={"pk": record.pk})
        actions.append(create_action_link(detail_url, "fa-eye", "View Response"))

        # Edit if draft
        if record.response_status == "draft":
            edit_url = reverse("solicitations:response_edit", kwargs={"pk": record.pk})
            actions.append(create_action_link(edit_url, "fa-pen-to-square", "Edit Response"))

        # Review link
        if record.parent:
            review_url = reverse("solicitations:review_create", kwargs={"response_pk": record.pk})
            actions.append(create_action_link(review_url, "fa-clipboard-check", "Review"))

        return format_html('<div class="flex items-center space-x-2">{}</div>', mark_safe("".join(actions)))
