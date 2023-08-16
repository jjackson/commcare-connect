from django_tables2 import columns, tables, utils

from commcare_connect.opportunity.models import OpportunityAccess, UserVisit


class OpportunityAccessTable(tables.Table):
    learn_progress = columns.Column(verbose_name="Modules Completed")
    last_visit_date = columns.DateColumn(accessor="last_visit_date", default="N/A")
    details = columns.LinkColumn(
        "opportunity:user_learn_progress",
        verbose_name="",
        text="View Details",
        args=[utils.A("opportunity.organization.slug"), utils.A("opportunity.id"), utils.A("pk")],
    )

    class Meta:
        model = OpportunityAccess
        fields = ("user.name", "learn_progress", "visit_count")
        orderable = False
        empty_text = "No learn progress for users."


class UserVisitTable(tables.Table):
    deliver_form = columns.Column(verbose_name="Form Name", accessor="deliver_form.name")

    class Meta:
        model = UserVisit
        fields = ("user.name", "visit_date", "status")
        sequence = ("user.name", "deliver_form", "visit_date", "status")
        empty_text = "No forms."
        orderable = False
