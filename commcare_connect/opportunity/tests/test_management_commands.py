import datetime

from django.core.management import call_command
from django.test import TestCase

from commcare_connect.opportunity.models import InvoiceStatus
from commcare_connect.opportunity.tests.factories import OpportunityFactory, PaymentInvoiceFactory


class ArchivePendingInvoicesTest(TestCase):
    def test_archive_pending_invoices(self):
        fixed_cutoff_date = datetime.date(2025, 11, 1)

        opp_past = OpportunityFactory(end_date=fixed_cutoff_date - datetime.timedelta(days=1))  # 2025-10-31
        opp_on_cutoff = OpportunityFactory(end_date=fixed_cutoff_date)  # 2025-11-01
        opp_future = OpportunityFactory(end_date=fixed_cutoff_date + datetime.timedelta(days=1))  # 2025-11-02

        invoice1 = PaymentInvoiceFactory(opportunity=opp_past, status=InvoiceStatus.PENDING)
        invoice2 = PaymentInvoiceFactory(opportunity=opp_on_cutoff, status=InvoiceStatus.PENDING)
        invoice3 = PaymentInvoiceFactory(opportunity=opp_future, status=InvoiceStatus.PENDING)
        invoice4 = PaymentInvoiceFactory(opportunity=opp_past, status=InvoiceStatus.APPROVED)
        invoice5 = PaymentInvoiceFactory(opportunity=opp_past, status=InvoiceStatus.PENDING)

        call_command("archive_pending_invoices")

        invoice1.refresh_from_db()
        invoice2.refresh_from_db()
        invoice3.refresh_from_db()
        invoice4.refresh_from_db()
        invoice5.refresh_from_db()

        self.assertEqual(invoice1.status, InvoiceStatus.ARCHIVED)
        self.assertIsNotNone(invoice1.archived_date)

        self.assertEqual(invoice2.status, InvoiceStatus.ARCHIVED)
        self.assertIsNotNone(invoice2.archived_date)

        self.assertEqual(invoice3.status, InvoiceStatus.PENDING)
        self.assertIsNone(invoice3.archived_date)

        self.assertEqual(invoice4.status, InvoiceStatus.APPROVED)
        self.assertIsNone(invoice4.archived_date)

        self.assertEqual(invoice5.status, InvoiceStatus.ARCHIVED)
        self.assertIsNotNone(invoice5.archived_date)
