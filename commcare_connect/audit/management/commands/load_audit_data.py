import os
from datetime import datetime
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_datetime

from commcare_connect.audit.management.extractors.commcare_extractor import CommCareExtractor
from commcare_connect.audit.models import AuditSession, AuditVisit
from commcare_connect.opportunity.models import BlobMeta


class Command(BaseCommand):
    help = "Load audit data from CommCare HQ for local auditing"

    def add_arguments(self, parser):
        parser.add_argument("--domain", type=str, required=True, help="CommCare domain/project space")
        parser.add_argument("--app-id", type=str, required=True, help="CommCare application ID")
        parser.add_argument(
            "--start-date", type=str, required=False, help="Start date for data extraction (YYYY-MM-DD)"
        )
        parser.add_argument("--end-date", type=str, required=False, help="End date for data extraction (YYYY-MM-DD)")
        parser.add_argument(
            "--username", type=str, help="CommCare API username (defaults to COMMCARE_USERNAME env var)"
        )
        parser.add_argument("--api-key", type=str, help="CommCare API key (defaults to COMMCARE_API_KEY env var)")
        parser.add_argument("--limit", type=int, help="Limit number of forms to process (for testing)")
        parser.add_argument(
            "--dry-run", action="store_true", help="Show what would be loaded without actually loading data"
        )

    def handle(self, *args, **options):
        domain = options["domain"]
        app_id = options["app_id"]
        start_date = options.get("start_date")
        end_date = options.get("end_date")
        username = options.get("username")
        api_key = options.get("api_key")
        limit = options.get("limit")
        dry_run = options["dry_run"]

        self.stdout.write(self.style.SUCCESS(f"Loading audit data from CommCare HQ"))
        self.stdout.write(f"   Domain: {domain}")
        self.stdout.write(f"   App ID: {app_id}")
        if start_date and end_date:
            self.stdout.write(f"   Date range: {start_date} to {end_date}")
        else:
            self.stdout.write("   Date range: All available data")
        if limit:
            self.stdout.write(f"   Limit: {limit} forms")
        if dry_run:
            self.stdout.write(self.style.WARNING("   DRY RUN MODE - No data will be saved"))

        try:
            # Initialize CommCare extractor
            extractor = CommCareExtractor(domain=domain, username=username, api_key=api_key)

            # Fetch forms from CommCare
            self.stdout.write("\nFetching forms from CommCare HQ...")
            forms = extractor.get_forms(
                app_id=app_id, received_start=start_date, received_end=end_date, limit=limit, verbose=True
            )

            if not forms:
                self.stdout.write(self.style.WARNING("No forms found for the specified criteria"))
                return

            # Filter forms that would be "approved" (simulate verification)
            approved_forms = self._filter_approved_forms(forms)
            self.stdout.write(f"Found {len(approved_forms)} forms that would be approved for audit")

            if dry_run:
                self._show_dry_run_summary(approved_forms, domain, app_id)
                return

            # Create local database records
            self.stdout.write("\nCreating local audit records...")
            with transaction.atomic():
                # Create audit session
                audit_session = self._create_audit_session(domain, app_id, start_date, end_date)

                # Process forms and create AuditVisit records
                created_visits = []
                for form in approved_forms:
                    try:
                        audit_visit = self._create_audit_visit(form, audit_session)
                        if audit_visit:
                            created_visits.append(audit_visit)
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f'Error processing form {form.get("id")}: {e}'))

                self.stdout.write(self.style.SUCCESS(f"Created {len(created_visits)} AuditVisit records"))

                # Download attachments
                if created_visits:
                    self.stdout.write("\nDownloading form attachments...")
                    self._download_attachments(extractor, forms, created_visits)

            self.stdout.write(self.style.SUCCESS(f"\nSuccessfully loaded audit data!"))
            self.stdout.write(f"   Audit Session: {audit_session}")
            self.stdout.write(f"   Visits loaded: {len(created_visits)}")
            self.stdout.write(f"\nYou can now access the audit interface at /audit/")

        except Exception as e:
            raise CommandError(f"Failed to load audit data: {e}")
        finally:
            if "extractor" in locals():
                extractor.close()

    def _filter_approved_forms(self, forms):
        """
        Filter forms that would be considered 'approved' for audit.
        For now, we'll simulate this by including forms with attachments.
        """
        approved_forms = []
        for form in forms:
            # Simulate approval criteria:
            # 1. Form has attachments (images)
            # 2. Form is not archived/deleted
            # 3. Form has required metadata

            if form.get("attachments") and form.get("metadata") and not form.get("archived", False):
                approved_forms.append(form)

        return approved_forms

    def _show_dry_run_summary(self, forms, domain, app_id):
        """Show what would be created in dry run mode"""
        self.stdout.write("\nDRY RUN SUMMARY:")
        self.stdout.write(f"   Would create AuditSession for domain: {domain}")
        self.stdout.write(f"   Would create AuditSession for app: {app_id}")

        users = set()
        total_attachments = 0

        for form in forms:
            # Extract user info
            metadata = form.get("metadata", {})
            username = metadata.get("username", "unknown")
            users.add(username)

            # Count attachments
            attachments = form.get("attachments", {})
            total_attachments += len([a for a in attachments.keys() if not a.endswith(".xml")])

        self.stdout.write(f"   Would create {len(forms)} AuditVisit records")
        self.stdout.write(f'   Would process {len(users)} users: {", ".join(sorted(users))}')
        self.stdout.write(f"   Would download {total_attachments} attachments")

    def _create_audit_session(self, domain, app_id, start_date, end_date):
        """Create an audit session for the loaded data"""
        from datetime import date, datetime

        # Convert string dates to date objects, use defaults if not provided
        if start_date:
            start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
        else:
            start_date_obj = date(2020, 1, 1)  # Default start date

        if end_date:
            end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date()
        else:
            end_date_obj = date.today()  # Default to today

        # For now, use a default auditor username
        auditor_username = "audit_admin"

        # Create audit session
        audit_session = AuditSession.objects.create(
            auditor_username=auditor_username,
            flw_username="multiple_users",  # Will be updated when we process forms
            opportunity_name=f"Audit - {app_id}",
            domain=domain,
            app_id=app_id,
            start_date=start_date_obj,
            end_date=end_date_obj,
            notes=f"Audit session created for {domain}/{app_id} from {start_date_obj} to {end_date_obj}",
        )

        self.stdout.write(f"   Created audit session: {audit_session}")
        return audit_session

    def _create_audit_visit(self, form, audit_session):
        """Create AuditVisit record from CommCare form data"""

        # Extract form metadata
        form_id = form.get("id")
        metadata = form.get("metadata", {})
        received_on = form.get("received_on")

        if not received_on:
            self.stdout.write(self.style.WARNING(f"Skipping form {form_id}: no received_on date"))
            return None

        # Parse visit date
        visit_date = parse_datetime(received_on)
        if not visit_date:
            self.stdout.write(self.style.WARNING(f"Skipping form {form_id}: invalid date format"))
            return None

        # Extract entity info from form
        form_data = form.get("form", {})
        case_data = form_data.get("case", {}) if isinstance(form_data.get("case"), dict) else {}

        # Create AuditVisit
        audit_visit, created = AuditVisit.objects.get_or_create(
            audit_session=audit_session,
            xform_id=form_id,
            defaults={
                "visit_date": visit_date,
                "entity_id": case_data.get("@case_id", ""),
                "entity_name": case_data.get("case_name", ""),
                "location": metadata.get("location", ""),
                "form_json": form,
            },
        )

        if created:
            return audit_visit
        else:
            self.stdout.write(f"   AuditVisit already exists for form {form_id}")
            return audit_visit

    def _download_attachments(self, extractor, forms, audit_visits):
        """Download form attachments and create BlobMeta records (same as production)"""

        # Create mapping of form_id to audit_visit
        form_to_visit = {visit.xform_id: visit for visit in audit_visits}

        downloaded_count = 0

        for form in forms:
            form_id = form.get("id")
            audit_visit = form_to_visit.get(form_id)

            if not audit_visit:
                continue

            attachments = form.get("attachments", {})

            for filename, attachment_info in attachments.items():
                # Skip XML files
                if filename.endswith(".xml"):
                    continue

                try:
                    # Extract attachment URL and metadata
                    if isinstance(attachment_info, dict):
                        attachment_url = attachment_info.get("url")
                        content_type = attachment_info.get("content_type", "image/jpeg")
                        content_length = attachment_info.get("content_length", 0)
                    else:
                        attachment_url = attachment_info
                        content_type = "image/jpeg"
                        content_length = 0

                    if not attachment_url:
                        continue

                    # Download the file
                    response = extractor.session.get(attachment_url, timeout=30, stream=True)
                    response.raise_for_status()

                    # Create BlobMeta record (same as production UserVisit system)
                    blob_meta, created = BlobMeta.objects.get_or_create(
                        name=filename,
                        parent_id=form_id,
                        defaults={
                            "content_length": len(response.content),
                            "content_type": content_type,
                        },
                    )

                    if created:
                        # Save file to storage (same as production)
                        default_storage.save(str(blob_meta.blob_id), ContentFile(response.content, filename))

                    if created:
                        downloaded_count += 1

                        if downloaded_count % 10 == 0:
                            self.stdout.write(f"   Downloaded {downloaded_count} attachments...")

                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"Error downloading {filename}: {e}"))

        self.stdout.write(self.style.SUCCESS(f"Downloaded {downloaded_count} attachments"))
