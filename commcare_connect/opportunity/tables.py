from django.utils.safestring import mark_safe
from django_tables2 import columns, tables, utils

from commcare_connect.opportunity.models import OpportunityAccess, Payment, PaymentUnit, UserVisit


class OpportunityAccessTable(tables.Table):
    display_name = columns.Column(verbose_name="Name")
    learn_progress = columns.Column(verbose_name="Modules Completed")
    details = columns.LinkColumn(
        "opportunity:user_learn_progress",
        verbose_name="",
        text="View Details",
        args=[utils.A("opportunity__organization__slug"), utils.A("opportunity__id"), utils.A("pk")],
    )

    class Meta:
        model = OpportunityAccess
        fields = ("display_name", "user__username", "learn_progress")
        orderable = False
        empty_text = "No learn progress for users."
        attrs = {"thead": {"class": ""}, "class": "table table-bordered mb-0"}


class UserVisitTable(tables.Table):
    # export only columns
    visit_id = columns.Column("Visit ID", accessor="xform_id", visible=False)
    username = columns.Column("Username", accessor="user__username", visible=False)
    form_json = columns.Column("Form JSON", accessor="form_json", visible=False)
    visit_date_export = columns.DateTimeColumn(
        verbose_name="Visit date", accessor="visit_date", format="c", visible=False
    )
    reason = columns.Column("Rejected Reason", accessor="reason", visible=False)

    deliver_unit = columns.Column("Unit Name", accessor="deliver_unit__name")
    entity_id = columns.Column("Entity ID", accessor="entity_id", visible=False)
    entity_name = columns.Column("Entity Name", accessor="entity_name")

    class Meta:
        model = UserVisit
        fields = ("user__name", "username", "visit_date", "status")
        sequence = (
            "visit_id",
            "visit_date",
            "visit_date_export",
            "status",
            "username",
            "user__name",
            "deliver_unit",
        )
        empty_text = "No forms."
        orderable = False
        attrs = {"thead": {"class": ""}, "class": "table table-bordered mb-0"}


class OpportunityPaymentTable(tables.Table):
    view_payments = columns.LinkColumn(
        "opportunity:user_payments_table",
        verbose_name="",
        text="View Details",
        args=[utils.A("opportunity__organization__slug"), utils.A("opportunity__id"), utils.A("pk")],
    )

    class Meta:
        model = OpportunityAccess
        fields = ("user__name", "user__username", "payment_accrued", "total_paid")
        orderable = False
        empty_text = "No user have payments accrued yet."
        attrs = {"thead": {"class": ""}, "class": "table table-bordered mb-0"}


class UserPaymentsTable(tables.Table):
    class Meta:
        model = Payment
        fields = ("amount", "date_paid")
        orderable = False
        empty_text = "No payments made for this user"
        template_name = "django_tables2/bootstrap5.html"
        attrs = {"thead": {"class": ""}, "class": "table table-bordered mb-0"}


class AggregateColumn(columns.Column):
    def render_footer(self, bound_column, table):
        return sum(1 if bound_column.accessor.resolve(row) else 0 for row in table.data)


class BooleanAggregateColumn(columns.BooleanColumn, AggregateColumn):
    pass


class UserStatusTable(tables.Table):
    display_name = columns.Column(verbose_name="Name", footer="Total")
    accepted = BooleanAggregateColumn(verbose_name="Accepted")
    claimed = AggregateColumn(verbose_name="Job Claimed", accessor="job_claimed")
    started_learning = AggregateColumn(verbose_name="Started Learning", accessor="date_learn_started")
    completed_learning = AggregateColumn(verbose_name="Completed Learning", accessor="date_learn_completed")
    passed_assessment = BooleanAggregateColumn(verbose_name="Passed Assessment")
    started_delivery = AggregateColumn(verbose_name="Started Delivery", accessor="date_deliver_started")
    last_visit_date = columns.Column(accessor="last_visit_date_d")

    class Meta:
        model = OpportunityAccess
        fields = ("display_name", "user__username", "accepted", "last_visit_date")
        sequence = (
            "display_name",
            "user__username",
            "accepted",
            "started_learning",
            "completed_learning",
            "passed_assessment",
            "claimed",
            "started_delivery",
            "last_visit_date",
        )
        empty_text = "No users invited for this opportunity."
        orderable = False
        attrs = {"thead": {"class": ""}, "class": "table table-bordered mb-0"}


class PaymentUnitTable(tables.Table):
    deliver_units = columns.Column("Deliver Units")
    details = columns.LinkColumn(
        "opportunity:edit_payment_unit",
        verbose_name="",
        text="Edit",
        args=[utils.A("opportunity__organization__slug"), utils.A("opportunity__id"), utils.A("pk")],
    )

    class Meta:
        model = PaymentUnit
        fields = ("name", "amount")
        empty_text = "No payment units for this opportunity."
        orderable = False
        attrs = {"thead": {"class": ""}, "class": "table table-bordered mb-0"}

    def render_deliver_units(self, record):
        deliver_units = "".join([f"<li>{d.name}</li>" for d in record.deliver_units.all()])
        return mark_safe(f"<ul>{deliver_units}</ul>")


class DeliverStatusTable(tables.Table):
    name = columns.Column("Name of the User", accessor="display_name")
    visits_completed = columns.Column("Completed Visits")
    visits_approved = columns.Column("Approved Visits")
    visits_pending = columns.Column("Pending Visits")
    visits_rejected = columns.Column("Rejected Visits")
    visits_over_limit = columns.Column("Over Limit Visits")
    visits_duplicate = columns.Column("Duplicate Visits")
    details = columns.LinkColumn(
        "opportunity:user_visits_list",
        verbose_name="",
        text="View Details",
        args=[utils.A("opportunity__organization__slug"), utils.A("opportunity__id"), utils.A("pk")],
    )

    class Meta:
        model = OpportunityAccess
        fields = ("user__username", "last_visit_date")
        orderable = False
        sequence = (
            "name",
            "user__username",
            "visits_completed",
            "visits_approved",
            "visits_pending",
            "visits_rejected",
            "visits_over_limit",
            "visits_duplicate",
            "last_visit_date",
            "details",
        )
        attrs = {"thead": {"class": ""}, "class": "table table-bordered mb-0"}
