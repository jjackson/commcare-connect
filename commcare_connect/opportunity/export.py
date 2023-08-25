from django_tables2.export import TableExport

from commcare_connect.opportunity.models import Opportunity, UserVisit
from commcare_connect.opportunity.tables import UserVisitTable


def export_user_visits(opportunity: Opportunity, export_format: str) -> TableExport:
    """
    Export user visits for a given opportunity to a CSV file.
    """
    if not TableExport.is_valid_format(export_format):
        raise ValueError(f"Invalid export format: {export_format}")
    user_visits = UserVisit.objects.filter(opportunity=opportunity)
    table = UserVisitTable(user_visits)
    exporter = TableExport(export_format, table, exclude_columns=("visit_date",))
    return exporter
