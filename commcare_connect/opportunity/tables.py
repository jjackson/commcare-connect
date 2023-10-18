from django.utils.safestring import mark_safe
from django_tables2 import columns, tables, utils

from commcare_connect.opportunity.models import OpportunityAccess, Payment, PaymentUnit, UserVisit


class OpportunityAccessTable(tables.Table):
    learn_progress = columns.Column(verbose_name="Modules Completed")
    details = columns.LinkColumn(
        "opportunity:user_learn_progress",
        verbose_name="",
        text="View Details",
        args=[utils.A("opportunity.organization.slug"), utils.A("opportunity.id"), utils.A("pk")],
    )

    class Meta:
        model = OpportunityAccess
        fields = ("user.name", "user.username", "learn_progress")
        orderable = False
        empty_text = "No learn progress for users."


class UserVisitTable(tables.Table):
    # export only columns
    visit_id = columns.Column("Visit ID", accessor="xform_id", visible=False)
    username = columns.Column("Username", accessor="user.username", visible=False)
    form_json = columns.Column("Form JSON", accessor="form_json", visible=False)
    visit_date_export = columns.DateTimeColumn(
        verbose_name="Visit date", accessor="visit_date", format="c", visible=False
    )

    deliver_unit = columns.Column("Unit Name", accessor="deliver_unit.name")
    entity_id = columns.Column("Entity ID", accessor="entity_id", visible=False)
    entity_name = columns.Column("Entity Name", accessor="entity_name")

    class Meta:
        model = UserVisit
        fields = ("user.name", "username", "visit_date", "status")
        sequence = (
            "visit_id",
            "visit_date",
            "visit_date_export",
            "status",
            "username",
            "user.name",
            "deliver_unit",
        )
        empty_text = "No forms."
        orderable = False


class PaymentTable(tables.Table):
    class Meta:
        model = Payment
        fields = ("opportunity_access.user.name", "opportunity_access.user.username", "amount", "date_paid")
        orderable = False
        empty_text = "No payments"


class UserStatusTable(tables.Table):
    class Meta:
        model = OpportunityAccess
        fields = ("user.name", "user.username", "accepted")
        empty_text = "No users invited for this opportunity."
        orderable = False


class PaymentUnitTable(tables.Table):
    deliver_units = columns.Column("Deliver Units")
    details = columns.LinkColumn(
        "opportunity:edit_payment_unit",
        verbose_name="",
        text="Edit",
        args=[utils.A("opportunity.organization.slug"), utils.A("opportunity.id"), utils.A("pk")],
    )

    class Meta:
        model = PaymentUnit
        fields = ("name", "amount")
        empty_text = "No payment units for this opportunity."
        orderable = False

    def render_deliver_units(self, record):
        deliver_units = "".join([f"<li>{d.name}</li>" for d in record.deliver_units.all()])
        return mark_safe(f"<ul>{deliver_units}</ul>")
