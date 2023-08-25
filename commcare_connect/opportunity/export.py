from django.utils.encoding import force_str
from tablib import Dataset

from commcare_connect.opportunity.models import Opportunity, UserVisit
from commcare_connect.opportunity.tables import UserVisitTable


def export_user_visits(opportunity: Opportunity) -> Dataset:
    user_visits = UserVisit.objects.filter(opportunity=opportunity)
    table = UserVisitTable(user_visits)
    exclude_columns = ("visit_date",)
    columns = [
        column
        for column in table.columns.iterall()
        if not (column.column.exclude_from_export or column.name in exclude_columns)
    ]

    dataset = Dataset(title="Export", headers=[force_str(column.header, strings_only=True) for column in columns])
    for row in table.rows:
        dataset.append([force_str(row.get_cell_value(column.name), strings_only=True) for column in columns])
    return dataset
