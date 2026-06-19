from __future__ import annotations

import csv
import datetime

from django.db import transaction
from django.utils.translation import gettext

from commcare_connect.audit import calculations
from commcare_connect.audit.calculations import get_registered_calculations
from commcare_connect.audit.models import AuditReport, AuditReportEntry
from commcare_connect.opportunity.models import Opportunity, OpportunityAccess
from commcare_connect.utils.file import EchoWriter

STREAM_CHUNK_SIZE = 2000


def stream_audit_report_csv(report, name_filter=""):
    columns = column_specs(list(report.entries.all()))
    writer = csv.writer(EchoWriter())

    yield writer.writerow([gettext("Connect Worker"), *(label for _name, label in columns)])

    entries = entries_for_export(report, name_filter)
    for entry in entries.iterator(chunk_size=STREAM_CHUNK_SIZE):
        cells = [_export_cell_value(entry.results, name) for name, _label in columns]
        yield writer.writerow([entry.opportunity_access.user.name, *cells])


def _export_cell_value(results, calc_name):
    result = results.get(calc_name, {})
    if not result.get("has_sufficient_data"):
        return gettext("N/A")
    return result.get("value")


def column_specs(entries):
    """Calculation columns to render, ordered by registry then by appearance."""
    registry_names = [c.name for c in get_registered_calculations()]
    seen = {}
    for entry in entries:
        for name, result in entry.results.items():
            if name not in seen:
                seen[name] = result.get("label", name)
    ordered = [(name, seen[name]) for name in registry_names if name in seen]
    leftovers = [(name, label) for name, label in seen.items() if name not in registry_names]
    return ordered + leftovers


def entries_for_export(report, name_filter=""):
    """Report entries for CSV export, optionally filtered by worker name, ordered by name."""
    rows = report.entries.select_related("opportunity_access__user")
    if name_filter:
        rows = rows.filter(opportunity_access__user__name__icontains=name_filter)
    return rows.order_by("opportunity_access__user__name")


def period_for(today: datetime.date) -> tuple[datetime.date, datetime.date]:
    """Return the most recently completed Monday-Sunday week strictly before `today`.

    Stable regardless of which weekday the task runs on: calling this on any day
    always returns the previous full Mon-Sun window, never a current/in-progress one.
    """
    # Monday = 0 ... Sunday = 6. Days since the most recent *completed* Sunday:
    # Mon=1, Tue=2, ..., Sat=6, Sun=7 (the Sunday a week ago, not today).
    days_since_last_sunday = today.weekday() + 1
    period_end = today - datetime.timedelta(days=days_since_last_sunday)
    period_start = period_end - datetime.timedelta(days=6)
    return period_start, period_end


@transaction.atomic
def generate_audit_report_for_opportunity(
    opportunity: Opportunity,
    period_start: datetime.date,
    period_end: datetime.date,
) -> AuditReport:
    report = AuditReport.objects.create(
        opportunity=opportunity,
        period_start=period_start,
        period_end=period_end,
    )

    active_accesses = (
        OpportunityAccess.objects.filter(
            opportunity=opportunity,
            accepted=True,
            suspended=False,
        )
        .select_related("user")
        .order_by("user__name")
    )

    calcs = calculations.get_registered_calculations()
    entries = []
    for access in active_accesses:
        results = {}
        flagged = False
        for calc in calcs:
            result = calc.run(access, period_start, period_end)
            results[result.name] = result.to_dict()
            if result.has_sufficient_data and not result.in_range:
                flagged = True
        entries.append(
            AuditReportEntry(
                audit_report=report,
                opportunity_access=access,
                results=results,
                flagged=flagged,
            )
        )

    if entries:
        AuditReportEntry.objects.bulk_create(entries)

    return report
