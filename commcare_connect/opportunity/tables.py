from django_tables2 import columns, tables, utils

from commcare_connect.opportunity.models import OpportunityAccess


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
