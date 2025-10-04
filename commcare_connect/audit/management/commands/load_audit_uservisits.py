from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_datetime

from commcare_connect.audit.management.extractors.commcare_extractor import CommCareExtractor
from commcare_connect.audit.models import AuditSession
from commcare_connect.opportunity.models import BlobMeta, DeliverUnit, Opportunity, OpportunityAccess, User, UserVisit


class Command(BaseCommand):
    help = "Load audit data from CommCare HQ directly into UserVisit records"

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

        self.stdout.write(self.style.SUCCESS(f"Loading audit data from CommCare HQ into UserVisit records"))
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
            # Check if audit dependencies exist
            self._check_dependencies(domain, app_id)

            # Initialize CommCare extractor
            extractor = CommCareExtractor(domain=domain, username=username, api_key=api_key)

            # Fetch forms from CommCare
            self.stdout.write("\nFetching forms from CommCare HQ...")
            forms = extractor.get_forms(
                app_id=app_id, received_start=start_date, received_end=end_date, limit=limit, verbose=True
            )

            if not forms:
                self.stdout.write("No forms found for the specified criteria")
                return

            # Filter for approved forms
            approved_forms = self._filter_approved_forms(forms)
            self.stdout.write(f"Found {len(approved_forms)} forms that would be approved for audit")

            if dry_run:
                self._show_dry_run_summary(approved_forms)
                return

            with transaction.atomic():
                audit_session = self._create_audit_session(domain, app_id, start_date, end_date)
                created_visits = []

                self.stdout.write("\nCreating UserVisit records...")
                for form in approved_forms:
                    try:
                        user_visit = self._create_user_visit(form, domain, app_id)
                        if user_visit:
                            created_visits.append(user_visit)
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f'Error processing form {form.get("id")}: {e}'))

                self.stdout.write(self.style.SUCCESS(f"Created {len(created_visits)} UserVisit records"))

                # Download attachments
                if created_visits:
                    self.stdout.write("\nDownloading form attachments...")
                    self._download_attachments(extractor, forms, created_visits)

            self.stdout.write(self.style.SUCCESS(f"\nSuccessfully loaded audit data!"))
            self.stdout.write(f"   Audit Session: {audit_session}")
            self.stdout.write(f"   UserVisits loaded: {len(created_visits)}")
            self.stdout.write(f"\nYou can now access the audit interface at /audit/")

        except Exception as e:
            raise CommandError(f"Failed to load audit data: {e}")
        finally:
            if "extractor" in locals():
                extractor.close()

    def _check_dependencies(self, domain, app_id):
        """Check if required audit dependencies exist"""
        try:
            opportunity = Opportunity.objects.get(deliver_app__cc_domain=domain, deliver_app__cc_app_id=app_id)
            user = User.objects.get(username="audit_flw_user")  # From YAML config
            deliver_unit = DeliverUnit.objects.filter(app__cc_app_id=app_id).first()

            if not deliver_unit:
                raise CommandError(f"No DeliverUnit found for app {app_id}. Run setup_audit_dependencies first.")

            self.stdout.write(f"   Using Opportunity: {opportunity}")
            self.stdout.write(f"   Using User: {user}")
            self.stdout.write(f"   Using DeliverUnit: {deliver_unit}")

        except Opportunity.DoesNotExist:
            raise CommandError(
                f"No Opportunity found for domain {domain} and app {app_id}. " "Run setup_audit_dependencies first."
            )
        except User.DoesNotExist:
            raise CommandError("Audit user not found. Run setup_audit_dependencies first.")

    def _filter_approved_forms(self, forms):
        """Filter forms that would be considered 'approved' for audit"""
        approved_forms = []
        for form in forms:
            # Simulate approval criteria:
            # 1. Form has attachments (images)
            # 2. Form is not archived
            if form.get("attachments") and not form.get("archived", False):
                approved_forms.append(form)
        return approved_forms

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
            flw_username="audit_flw_user",  # From YAML config
            opportunity_name=f"Audit - {app_id}",
            domain=domain,
            app_id=app_id,
            start_date=start_date_obj,
            end_date=end_date_obj,
            notes=f"Audit session created for {domain}/{app_id} from {start_date_obj} to {end_date_obj}",
        )

        self.stdout.write(f"   Created audit session: {audit_session}")
        return audit_session

    def _create_user_visit(self, form, domain, app_id):
        """Create UserVisit record from CommCare form data"""

        # Get required objects
        opportunity = Opportunity.objects.get(deliver_app__cc_domain=domain, deliver_app__cc_app_id=app_id)
        user = User.objects.get(username="audit_flw_user")
        deliver_unit = DeliverUnit.objects.filter(app__cc_app_id=app_id).first()

        # Get or create opportunity access
        opportunity_access, _ = OpportunityAccess.objects.get_or_create(
            opportunity=opportunity, user=user, defaults={"accepted": True}
        )

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

        # Create UserVisit
        user_visit, created = UserVisit.objects.get_or_create(
            xform_id=form_id,
            entity_id=case_data.get("@case_id", ""),
            deliver_unit=deliver_unit,
            defaults={
                "opportunity": opportunity,
                "user": user,
                "opportunity_access": opportunity_access,
                "visit_date": visit_date,
                "entity_name": case_data.get("case_name", ""),
                "location": metadata.get("location", ""),
                "form_json": form,
                "status": "approved",  # Set as approved for audit
            },
        )

        if created:
            return user_visit
        else:
            self.stdout.write(f"   UserVisit already exists for form {form_id}")
            return user_visit

    def _download_attachments(self, extractor, forms, user_visits):
        """Download form attachments and create BlobMeta records"""

        # Create mapping of form_id to user_visit
        form_to_visit = {visit.xform_id: visit for visit in user_visits}

        downloaded_count = 0

        for form in forms:
            form_id = form.get("id")
            user_visit = form_to_visit.get(form_id)

            if not user_visit:
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
                        downloaded_count += 1

                        if downloaded_count % 10 == 0:
                            self.stdout.write(f"   Downloaded {downloaded_count} attachments...")

                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"Error downloading {filename}: {e}"))

        self.stdout.write(self.style.SUCCESS(f"Downloaded {downloaded_count} attachments"))

    def _show_dry_run_summary(self, forms):
        """Show what would be created in dry run mode"""
        self.stdout.write("\nDRY RUN SUMMARY:")

        # Count users and attachments
        users = set()
        total_attachments = 0

        for form in forms:
            metadata = form.get("metadata", {})
            username = metadata.get("username", "unknown")
            users.add(username)

            attachments = form.get("attachments", {})
            total_attachments += len([f for f in attachments.keys() if not f.endswith(".xml")])

        self.stdout.write(f"   Would create {len(forms)} UserVisit records")
        self.stdout.write(f'   Would process {len(users)} users: {", ".join(sorted(users))}')
        self.stdout.write(f"   Would download {total_attachments} attachments")
