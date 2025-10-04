from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db import transaction

from commcare_connect.audit.models import AuditResult, AuditSession
from commcare_connect.opportunity.models import BlobMeta, UserVisit


class Command(BaseCommand):
    help = "Clear audit data from local database and storage"

    def add_arguments(self, parser):
        parser.add_argument(
            "--sessions-only", action="store_true", help="Clear only audit sessions and results, keep visit data"
        )
        parser.add_argument("--domain", type=str, help="Clear data only for specific domain")
        parser.add_argument("--session-id", type=int, help="Clear data only for specific audit session ID")
        parser.add_argument("--confirm", action="store_true", help="Skip confirmation prompt")
        parser.add_argument(
            "--dry-run", action="store_true", help="Show what would be deleted without actually deleting"
        )

    def handle(self, *args, **options):
        sessions_only = options["sessions_only"]
        domain = options.get("domain")
        session_id = options.get("session_id")
        confirm = options["confirm"]
        dry_run = options["dry_run"]

        self.stdout.write(self.style.WARNING("Clearing audit data from local database"))

        if domain:
            self.stdout.write(f"   Domain filter: {domain}")
        if session_id:
            self.stdout.write(f"   Session ID filter: {session_id}")

        if dry_run:
            self.stdout.write(self.style.WARNING("   DRY RUN MODE - No data will be deleted"))

        # Get confirmation unless --confirm flag is used
        if not confirm and not dry_run:
            self.stdout.write(self.style.WARNING("\nWARNING: This will permanently delete data!"))
            response = input("Are you sure you want to continue? (yes/no): ")
            if response.lower() != "yes":
                self.stdout.write("Operation cancelled.")
                return

        try:
            with transaction.atomic():
                if sessions_only:
                    self._clear_audit_sessions(domain, session_id, dry_run)
                else:
                    self._clear_all_audit_data(domain, session_id, dry_run)

            if not dry_run:
                self.stdout.write(self.style.SUCCESS("\nSuccessfully cleared audit data!"))
            else:
                self.stdout.write(self.style.SUCCESS("\nDry run completed - no data was deleted"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error clearing data: {e}"))

    def _clear_audit_sessions(self, domain, session_id, dry_run):
        """Clear only audit sessions and results"""
        self.stdout.write("\nClearing audit sessions and results...")

        # Filter sessions
        sessions_qs = AuditSession.objects.all()
        if domain:
            sessions_qs = sessions_qs.filter(domain=domain)
        if session_id:
            sessions_qs = sessions_qs.filter(id=session_id)

        sessions_count = sessions_qs.count()
        results_count = AuditResult.objects.filter(audit_session__in=sessions_qs).count()

        if dry_run:
            self.stdout.write(f"   Would delete {sessions_count} audit sessions")
            self.stdout.write(f"   Would delete {results_count} audit results")
        else:
            AuditResult.objects.filter(audit_session__in=sessions_qs).delete()
            sessions_qs.delete()
            self.stdout.write(f"   Deleted {sessions_count} audit sessions")
            self.stdout.write(f"   Deleted {results_count} audit results")

    def _clear_all_audit_data(self, domain, session_id, dry_run):
        """Clear all audit data including visits and images"""
        self.stdout.write("\nClearing all audit data...")

        # Filter sessions
        sessions_qs = AuditSession.objects.all()
        if domain:
            sessions_qs = sessions_qs.filter(domain=domain)
        if session_id:
            sessions_qs = sessions_qs.filter(id=session_id)

        # Get counts
        sessions_count = sessions_qs.count()
        # Get UserVisits that have audit results for these sessions
        audited_visits = UserVisit.objects.filter(auditresult__audit_session__in=sessions_qs).distinct()
        visits_count = audited_visits.count()
        # Get xform_ids from audited visits to find related BlobMeta records
        xform_ids = audited_visits.values_list("xform_id", flat=True)
        images_count = BlobMeta.objects.filter(parent_id__in=xform_ids).count()
        results_count = AuditResult.objects.filter(audit_session__in=sessions_qs).count()

        if dry_run:
            self.stdout.write(f"   Would delete {sessions_count} audit sessions")
            self.stdout.write(f"   Would delete {visits_count} audit visits")
            self.stdout.write(f"   Would delete {images_count} visit images")
            self.stdout.write(f"   Would delete {results_count} audit results")
        else:
            # Delete in correct order to avoid foreign key constraints
            AuditResult.objects.filter(audit_session__in=sessions_qs).delete()
            # Delete BlobMeta records and their files for audited visits
            audited_visits = UserVisit.objects.filter(auditresult__audit_session__in=sessions_qs).distinct()
            xform_ids = audited_visits.values_list("xform_id", flat=True)
            blob_metas = BlobMeta.objects.filter(parent_id__in=xform_ids)
            for blob_meta in blob_metas:
                # Delete the actual file from storage
                try:
                    default_storage.delete(str(blob_meta.blob_id))
                except Exception:
                    pass  # File might not exist
            blob_metas.delete()
            # Delete the UserVisit records that were created for audit
            audited_visits.delete()
            sessions_qs.delete()

            self.stdout.write(f"   Deleted {sessions_count} audit sessions")
            self.stdout.write(f"   Deleted {visits_count} audit visits")
            self.stdout.write(f"   Deleted {images_count} visit images")
            self.stdout.write(f"   Deleted {results_count} audit results")

        self.stdout.write(self.style.SUCCESS("\nAudit data cleared successfully!"))
