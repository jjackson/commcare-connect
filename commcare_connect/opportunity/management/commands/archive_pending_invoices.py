from datetime import datetime

from django.core.management import BaseCommand
from django.utils.timezone import now

from commcare_connect.opportunity.models import InvoiceStatus, PaymentInvoice


class Command(BaseCommand):
    help = "Archive Pending Invoices in Opportunities."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", type=bool, required=False, help="Dry Run. Returns the Number of invoice that will be updated."
        )

    def handle(self, *args, dry_run=False, **options):
        cutoff_date = datetime(2025, 11, 1)
        invoices = PaymentInvoice.objects.filter(opportunity__end_date__lte=cutoff_date, status=InvoiceStatus.PENDING)

        print(f"Marking {len(invoices)} invoices as Archived.")

        if not dry_run:
            invoices.update(status=InvoiceStatus.ARCHIVED, archived_date=now())
