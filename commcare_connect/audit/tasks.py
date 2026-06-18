from __future__ import annotations

import logging
import uuid

from django.core.files.base import ContentFile
from django.db.models import Q
from django.utils import timezone
from django_tables2.export.export import TableExport

from commcare_connect.audit.models import AuditReport
from commcare_connect.audit.services import (
    column_specs,
    entries_for_export,
    generate_audit_report_for_opportunity,
    period_for,
)
from commcare_connect.audit.tables import AuditReportExportTable
from commcare_connect.flags.flag_names import WEEKLY_PERFORMANCE_REPORT
from commcare_connect.flags.models import Flag
from commcare_connect.opportunity.models import Opportunity
from config.celery_app import app

logger = logging.getLogger(__name__)


@app.task(name="audit.generate_audit_reports")
def generate_audit_reports() -> None:
    try:
        flag = Flag.objects.get(name=WEEKLY_PERFORMANCE_REPORT)
    except Flag.DoesNotExist:
        logger.info("WEEKLY_PERFORMANCE_REPORT flag is not configured; nothing to do.")
        return

    period_start, period_end = period_for(timezone.now().date())

    opportunities = Opportunity.objects.filter(
        Q(pk__in=flag.opportunities.values_list("pk", flat=True))
        | Q(managedopportunity__program__in=flag.programs.all()),
        active=True,
    ).distinct()

    for opportunity in opportunities:
        try:
            generate_audit_report_for_opportunity(
                opportunity,
                period_start=period_start,
                period_end=period_end,
            )
        except Exception:
            logger.exception("Failed to generate weekly report for opportunity %s", opportunity.pk)


@app.task()
def export_audit_report_task(audit_report_id, name_filter):
    from commcare_connect.utils.storages import ExportS3Boto3Storage

    report = AuditReport.objects.get(audit_report_id=audit_report_id)
    columns_spec = column_specs(list(report.entries.all()))
    rows = entries_for_export(report, name_filter)

    table = AuditReportExportTable(rows, columns_spec=columns_spec)
    exporter = TableExport("csv", table)
    content = exporter.export()

    filename = f"weekly-performance-report-{uuid.uuid4()}.csv"
    return ExportS3Boto3Storage().save(filename, ContentFile(content.encode("utf-8")))
