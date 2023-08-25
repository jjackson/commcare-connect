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
    # export only columns
    username = columns.Column(verbose_name="Username", accessor="user.username", visible=False)
    form_json = columns.Column(verbose_name="Form JSON", accessor="form_json", visible=False)
    visit_date_export = columns.DateTimeColumn(
        verbose_name="Visit date", accessor="visit_date", format="c", visible=False
    )

    deliver_form = columns.Column(verbose_name="Form Name", accessor="deliver_form.name")

    class Meta:
        model = UserVisit
        fields = ("user.name", "visit_date", "status")
        sequence = ("visit_date", "visit_date_export", "username", "user.name", "deliver_form", "status")
        empty_text = "No forms."
        orderable = False
