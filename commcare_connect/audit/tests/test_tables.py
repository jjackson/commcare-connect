import pytest

from commcare_connect.audit.tables import AuditReportExportTable
from commcare_connect.audit.tests.factories import AuditReportFactory


@pytest.mark.django_db
def test_export_table_emits_raw_values_and_na(make_audit_entry):
    report = AuditReportFactory()
    make_audit_entry(report, "Bob", 0.5, in_range=False)  # out-of-range still exports raw value
    make_audit_entry(report, "Ann", None, has_data=False)  # insufficient data -> "N/A"

    rows = report.entries.order_by("opportunity_access__user__name")
    table = AuditReportExportTable(rows, columns_spec=[("calc_a", "Calc A")])

    values = list(table.as_values())

    assert values[0] == ["Connect Worker", "Calc A"]
    assert values[1] == ["Ann", "N/A"]
    assert values[2] == ["Bob", 0.5]
