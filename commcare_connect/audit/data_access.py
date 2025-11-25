"""
Data Access Layer for Audit.

This layer uses LabsRecordAPIClient to interact with production LabsRecord API.
It handles:
1. Fetching visit/user/opportunity data dynamically from Connect OAuth APIs
2. Managing audit state via production API (templates, sessions)
3. Simulating blob metadata availability via CommCare HQ

This is a pure API client with no local database storage.
"""

from typing import Any

import httpx
import pandas as pd
from django.conf import settings
from django.http import HttpRequest

from commcare_connect.audit.blob_api import BlobMetadataAPI
from commcare_connect.audit.models import AuditSessionRecord, AuditTemplateRecord
from commcare_connect.labs.integrations.connect.api_client import LabsRecordAPIClient


class AuditDataAccess:
    """
    Data access layer for audit that uses LabsRecordAPIClient for state
    and fetches visit data dynamically from Connect OAuth APIs.
    """

    def __init__(
        self,
        opportunity_id: int | None = None,
        organization_id: int | None = None,
        program_id: int | None = None,
        access_token: str | None = None,
        request: HttpRequest | None = None,
    ):
        """
        Initialize the audit data access layer.

        Args:
            opportunity_id: Optional opportunity ID for scoped API requests
            organization_id: Optional organization ID for scoped API requests
            program_id: Optional program ID for scoped API requests
            access_token: OAuth token for Connect production APIs
            request: HttpRequest object (for extracting token and org context in labs mode)
        """
        self.opportunity_id = opportunity_id
        self.organization_id = organization_id
        self.program_id = program_id

        # Store request for later use (e.g., getting CommCare OAuth token, org context)
        self.request = request

        # Use labs_context from middleware if available (takes precedence)
        if request and hasattr(request, "labs_context"):
            labs_context = request.labs_context
            if not opportunity_id and "opportunity_id" in labs_context:
                self.opportunity_id = labs_context["opportunity_id"]
            if not program_id and "program_id" in labs_context:
                self.program_id = labs_context["program_id"]
            if not organization_id and "organization_id" in labs_context:
                self.organization_id = labs_context["organization_id"]

        # Get OAuth token from labs session
        if not access_token and request:
            from django.utils import timezone

            labs_oauth = request.session.get("labs_oauth", {})
            expires_at = labs_oauth.get("expires_at", 0)
            if timezone.now().timestamp() < expires_at:
                access_token = labs_oauth.get("access_token")

        if not access_token:
            raise ValueError("OAuth access token required for audit data access")

        self.access_token = access_token
        self.production_url = settings.CONNECT_PRODUCTION_URL.rstrip("/")

        # Initialize HTTP client with Bearer token
        self.http_client = httpx.Client(
            headers={"Authorization": f"Bearer {self.access_token}"},
            timeout=120.0,
        )

        # Initialize Labs API client for state management
        self.labs_api = LabsRecordAPIClient(
            access_token,
            opportunity_id=self.opportunity_id,
            organization_id=self.organization_id,
            program_id=self.program_id,
        )

        # Lazy-initialize blob API for CommCare integration (only when needed)
        self._blob_api = None

    @property
    def blob_api(self):
        """Lazy-load BlobMetadataAPI only when needed for CommCare API calls.

        Note: As of PR #859, Connect production now provides image APIs:
        - UserVisit records include 'images' field with blob metadata:
          [{"blob_id": "...", "name": "...", "parent_id": "..."}]
        - Images can be fetched via: /export/opportunity/<int:opp_id>/image/
          (POST with {"blob_id": "..."} in request body)
        - This provides an alternative to CommCare HQ blob API
        - TODO: Integrate Connect image API into audit app
        """
        if self._blob_api is None:
            # Try to get CommCare OAuth token from session
            oauth_token = None
            if self.request:
                from django.utils import timezone

                commcare_oauth = self.request.session.get("commcare_oauth", {})
                expires_at = commcare_oauth.get("expires_at", 0)
                if timezone.now().timestamp() < expires_at:
                    oauth_token = commcare_oauth.get("access_token")

            # Initialize BlobMetadataAPI with OAuth token if available
            self._blob_api = BlobMetadataAPI(oauth_token=oauth_token)
        return self._blob_api

    def close(self):
        """Close HTTP client."""
        if self.http_client:
            self.http_client.close()

    # Template Methods

    def create_audit_template(
        self,
        username: str,
        opportunity_ids: list[int],
        audit_type: str,
        granularity: str,
        criteria: dict,
        preview_data: list[dict] | None = None,
    ) -> AuditTemplateRecord:
        """
        Create a new audit template.

        Args:
            username: Creator username (from OAuth profile)
            opportunity_ids: List of opportunity IDs to audit
            audit_type: Type of audit (date_range, last_n_per_flw, etc.)
            granularity: Audit granularity (combined, per_opp, per_flw)
            criteria: Audit criteria dict (start_date, end_date, counts, etc.)
            preview_data: Preview statistics from preview step

        Returns:
            AuditTemplateRecord instance
        """
        data = {
            "opportunity_ids": opportunity_ids,
            "audit_type": audit_type,
            "granularity": granularity,
            "preview_data": preview_data or [],
            **criteria,  # Unpack all criteria fields
        }

        record = self.labs_api.create_record(
            experiment="audit",
            type="AuditTemplate",
            data=data,
            username=username,
        )

        # Cast to AuditTemplateRecord for convenience properties
        api_data = {
            "id": record.id,
            "experiment": record.experiment,
            "type": record.type,
            "data": record.data,
            "username": record.username,
            "opportunity_id": record.opportunity_id,
            "organization_id": record.organization_id,
            "program_id": record.program_id,
            "labs_record_id": record.labs_record_id,
        }
        return AuditTemplateRecord(api_data)

    def get_audit_template(self, template_id: int) -> AuditTemplateRecord | None:
        """
        Get an audit template by ID.

        Args:
            template_id: Template ID

        Returns:
            AuditTemplateRecord or None
        """
        record = self.labs_api.get_record_by_id(
            record_id=template_id, experiment="audit", type="AuditTemplate", model_class=AuditTemplateRecord
        )
        return record

    def get_audit_templates(self, username: str | None = None) -> list[AuditTemplateRecord]:
        """
        Query audit templates.

        Args:
            username: Filter by creator username

        Returns:
            List of AuditTemplateRecord instances
        """
        return self.labs_api.get_records(
            experiment="audit", type="AuditTemplate", username=username, model_class=AuditTemplateRecord
        )

    # Session Methods

    def _generate_audit_description(self, audit_type: str, criteria: dict) -> str:
        """
        Generate a human-readable description of how an audit session was created.

        Args:
            audit_type: Type of audit (date_range, last_n_per_flw, etc.)
            criteria: Audit criteria dict

        Returns:
            Human-readable description string
        """
        parts = []

        if audit_type == "date_range":
            start_date = criteria.get("start_date") or criteria.get("startDate")
            end_date = criteria.get("end_date") or criteria.get("endDate")
            if start_date and end_date:
                parts.append(f"Visits from {start_date} to {end_date}")
            elif start_date:
                parts.append(f"Visits from {start_date}")
            elif end_date:
                parts.append(f"Visits until {end_date}")
            else:
                parts.append("All visits (date range)")

        elif audit_type == "last_n_per_flw":
            count = criteria.get("count_per_flw") or criteria.get("countPerFlw", 10)
            parts.append(f"Last {count} visits per FLW")

        elif audit_type == "last_n_per_opp":
            count = criteria.get("count_per_opp") or criteria.get("countPerOpp", 10)
            parts.append(f"Last {count} visits per opportunity")

        elif audit_type == "last_n_across_all":
            count = criteria.get("count_across_all") or criteria.get("countAcrossAll", 100)
            parts.append(f"Last {count} visits across all")

        else:
            parts.append(f"Audit type: {audit_type}")

        # Add sample percentage if less than 100%
        sample_percentage = criteria.get("sample_percentage") or criteria.get("samplePercentage", 100)
        if sample_percentage and sample_percentage < 100:
            parts.append(f"({sample_percentage}% sample)")

        return " ".join(parts)

    def create_audit_session(
        self,
        template_id: int,
        username: str,
        visit_ids: list[int],
        title: str,
        tag: str,
        opportunity_id: int | None = None,
        audit_type: str | None = None,
        criteria: dict | None = None,
        visits_cache: list[dict] | None = None,
    ) -> AuditSessionRecord:
        """
        Create a new audit session.

        Args:
            template_id: Parent template ID
            username: Auditor username (from OAuth profile)
            visit_ids: List of visit IDs to audit
            title: Session title
            tag: Session tag
            opportunity_id: Primary opportunity ID
            audit_type: Type of audit (date_range, last_n_per_flw, etc.)
            criteria: Audit criteria dict for generating description

        Returns:
            AuditSessionRecord instance with empty visit_results
        """
        # Fetch opportunity name if opportunity_id is provided
        opportunity_name = ""
        if opportunity_id:
            opportunity_details = self.get_opportunity_details(opportunity_id)
            if opportunity_details:
                opportunity_name = opportunity_details.get("name", "")

        # Generate human-readable description from audit settings
        description = ""
        if audit_type and criteria:
            description = self._generate_audit_description(audit_type, criteria)

        # Extract and store complete image metadata for all visits
        visit_images = {}
        if opportunity_id:
            # Use provided visits cache if available, otherwise fetch
            if visits_cache is not None:
                all_visits = visits_cache
            else:
                all_visits = self._fetch_visits_for_opportunity(opportunity_id)
            visit_cache = {visit["id"]: visit for visit in all_visits}

            for visit_id in visit_ids:
                try:
                    visit_data = self.get_visit_data(visit_id, opportunity_id=opportunity_id, visit_cache=visit_cache)
                    if visit_data:
                        images_with_questions = self.get_images_with_question_ids(visit_data)
                        visit_images[str(visit_id)] = images_with_questions
                except Exception as e:
                    # Log but continue if image extraction fails for one visit
                    print(f"[WARNING] Failed to extract images for visit {visit_id}: {e}")
                    visit_images[str(visit_id)] = []

        data = {
            "title": title,
            "tag": tag,
            "status": "in_progress",
            "overall_result": None,
            "notes": "",
            "kpi_notes": "",
            "visit_ids": visit_ids,
            "visit_results": {},  # Initialize empty
            "opportunity_id": opportunity_id,  # Store primary opportunity ID for later use
            "opportunity_name": opportunity_name,  # Store opportunity name for display
            "description": description,  # Human-readable description of audit creation settings
            "visit_images": visit_images,  # Store complete image metadata with question_ids
        }

        record = self.labs_api.create_record(
            experiment="audit",
            type="AuditSession",
            data=data,
            labs_record_id=template_id,
            username=username,
        )

        # Cast to AuditSessionRecord for convenience properties
        api_data = {
            "id": record.id,
            "experiment": record.experiment,
            "type": record.type,
            "data": record.data,
            "username": record.username,
            "opportunity_id": record.opportunity_id,
            "organization_id": record.organization_id,
            "program_id": record.program_id,
            "labs_record_id": record.labs_record_id,
        }
        return AuditSessionRecord(api_data)

    def get_audit_session(
        self, session_id: int, try_multiple_opportunities: bool = False
    ) -> AuditSessionRecord | None:
        """
        Get an audit session by ID.

        Args:
            session_id: Session ID
            try_multiple_opportunities: If True, searches across multiple opportunities
                when the session is not found under the current opportunity_id

        Returns:
            AuditSessionRecord or None
        """
        # First try with current opportunity_id
        sessions = self.labs_api.get_records(
            experiment="audit",
            type="AuditSession",
            model_class=AuditSessionRecord,
        )

        # Find the session with matching ID
        for session in sessions:
            if session.id == session_id:
                return session

        # If not found and try_multiple_opportunities is True, search other opportunities
        if try_multiple_opportunities:
            # Get all opportunities user has access to
            try:
                opportunities = self.search_opportunities(query="", limit=1000)

                # Try each opportunity
                for opp in opportunities:
                    opp_id = opp.get("id")
                    if opp_id == self.opportunity_id:
                        continue  # Already tried this one

                    # Create a temporary API client for this opportunity
                    temp_labs_api = LabsRecordAPIClient(self.access_token, opp_id)
                    try:
                        sessions = temp_labs_api.get_records(
                            experiment="audit",
                            type="AuditSession",
                            model_class=AuditSessionRecord,
                        )

                        for session in sessions:
                            if session.id == session_id:
                                return session
                    finally:
                        temp_labs_api.close()
            except Exception:
                pass  # If search fails, just return None

        return None

    def get_audit_sessions(self, username: str | None = None, status: str | None = None) -> list[AuditSessionRecord]:
        """
        Query audit sessions.

        Args:
            username: Filter by auditor username
            status: Filter by status (in_progress, completed)

        Returns:
            List of AuditSessionRecord instances
        """
        # Pass status as data filter
        kwargs = {}
        if status:
            kwargs["status"] = status

        records = self.labs_api.get_records(
            experiment="audit",
            type="AuditSession",
            username=username,
            model_class=AuditSessionRecord,
            **kwargs,
        )

        return records

    def save_audit_session(self, session: AuditSessionRecord) -> AuditSessionRecord:
        """
        Save in-memory changes to an audit session.

        Args:
            session: AuditSessionRecord with modified data

        Returns:
            Updated AuditSessionRecord
        """
        updated_record = self.labs_api.update_record(
            record_id=session.id,
            experiment="audit",
            type="AuditSession",
            data=session.data,
            username=session.username,
        )
        # Cast to AuditSessionRecord
        api_data = {
            "id": updated_record.id,
            "experiment": updated_record.experiment,
            "type": updated_record.type,
            "data": updated_record.data,
            "username": updated_record.username,
            "opportunity_id": updated_record.opportunity_id,
            "organization_id": updated_record.organization_id,
            "program_id": updated_record.program_id,
            "labs_record_id": updated_record.labs_record_id,
        }
        return AuditSessionRecord(api_data)

    def complete_audit_session(
        self, session: AuditSessionRecord, overall_result: str, notes: str = "", kpi_notes: str = ""
    ) -> AuditSessionRecord:
        """
        Mark audit session as completed.

        Args:
            session: AuditSessionRecord to complete
            overall_result: Overall audit result (pass, fail)
            notes: General notes
            kpi_notes: KPI notes

        Returns:
            Updated AuditSessionRecord
        """
        session.data["status"] = "completed"
        session.data["overall_result"] = overall_result
        session.data["notes"] = notes
        session.data["kpi_notes"] = kpi_notes

        return self.save_audit_session(session)

    # Visit Data Methods (Fetch from Connect API)

    def get_visit_ids_for_audit(
        self,
        opportunity_ids: list[int],
        audit_type: str,
        criteria: dict,
        visits_cache: dict[int, list[dict]] | None = None,
    ) -> list[int]:
        """
        Get list of visit IDs for audit based on criteria.

        Fetches from Connect OAuth API and applies filters.

        Args:
            opportunity_ids: List of opportunity IDs
            audit_type: Audit type (date_range, last_n_per_flw, etc.)
            criteria: Criteria dict with filtering parameters
            visits_cache: Optional dict mapping opportunity_id to list of visits (to avoid re-fetching)

        Returns:
            List of visit IDs
        """
        all_visits = []

        # Fetch visits for each opportunity (use cache if provided)
        for opp_id in opportunity_ids:
            if visits_cache and opp_id in visits_cache:
                visits = visits_cache[opp_id]
            else:
                visits = self._fetch_visits_for_opportunity(opp_id)
            all_visits.extend(visits)

        # Convert to DataFrame for easier filtering
        if not all_visits:
            return []

        df = pd.DataFrame(all_visits)

        # Parse dates with mixed ISO8601 format support
        df["visit_date"] = pd.to_datetime(df["visit_date"], format="mixed", utc=True)

        # Apply filters based on audit type and criteria
        if audit_type == "date_range":
            start_date = criteria.get("start_date")
            end_date = criteria.get("end_date")
            if start_date:
                df = df[df["visit_date"].dt.date >= pd.to_datetime(start_date).date()]
            if end_date:
                df = df[df["visit_date"].dt.date <= pd.to_datetime(end_date).date()]

        elif audit_type == "last_n_per_flw":
            # TODO: Check with team whether to use user_id or username as primary identifier
            # Currently using username since it's unique and always populated in the API
            # If we switch to user_id, we need to ensure it's populated in the export API
            count_per_flw = criteria.get("count_per_flw", 10)
            df = df.sort_values("visit_date", ascending=False)
            df = df.groupby("username", dropna=False).head(count_per_flw)

        elif audit_type == "last_n_per_opp":
            count_per_opp = criteria.get("count_per_opp", 10)
            df = df.sort_values("visit_date", ascending=False)
            df = df.groupby("opportunity_id").head(count_per_opp)

        elif audit_type == "last_n_across_all":
            count_across_all = criteria.get("count_across_all", 100)
            df = df.sort_values("visit_date", ascending=False)
            df = df.head(count_across_all)

        # Apply sample percentage if provided
        sample_percentage = criteria.get("sample_percentage", 100)
        if sample_percentage < 100:
            sample_size = int(len(df) * sample_percentage / 100)
            df = df.sample(n=sample_size, random_state=42)

        # Return list of unique visit IDs (deduplicate in case of data issues)
        return df["id"].unique().tolist()

    def get_visit_data(
        self, visit_id: int, opportunity_id: int | None = None, visit_cache: dict | None = None
    ) -> dict[str, Any] | None:
        """
        Get detailed data for a single visit.

        Fetches from Connect OAuth API.

        Args:
            visit_id: Visit ID
            opportunity_id: Opportunity ID (required if visit_cache not provided)
            visit_cache: Optional dict of visit_id -> visit_data for performance

        Returns:
            Dict with visit data including id, xform_id, visit_date, etc., or None if not found
        """
        # If we have a cache, use it
        if visit_cache and visit_id in visit_cache:
            return visit_cache[visit_id]

        # Otherwise fetch from API (requires opportunity_id)
        if not opportunity_id:
            raise ValueError("opportunity_id required when visit_cache not provided")

        visits = self._fetch_visits_for_opportunity(opportunity_id)
        for visit in visits:
            if visit["id"] == visit_id:
                return visit

        return None

    def get_visits_batch(self, visit_ids: list[int], opportunity_id: int) -> list[dict]:
        """
        Batch fetch multiple visits.

        Args:
            visit_ids: List of visit IDs
            opportunity_id: Opportunity ID to fetch from

        Returns:
            List of visit dicts
        """
        all_visits = self._fetch_visits_for_opportunity(opportunity_id)

        # Filter to requested IDs
        visit_id_set = set(visit_ids)
        return [v for v in all_visits if v["id"] in visit_id_set]

    # Blob Methods

    def get_blob_metadata_for_visit(self, xform_id: str, cc_domain: str) -> dict[str, dict]:
        """
        Get blob metadata for a visit's form.

        Delegates to BlobMetadataAPI which fetches from CommCare HQ.

        Args:
            xform_id: Form ID
            cc_domain: CommCare domain

        Returns:
            Dict mapping blob_id to metadata
        """
        return self.blob_api.get_blob_metadata_for_visit(xform_id, cc_domain)

    def download_blob(self, blob_url: str) -> bytes:
        """
        Download blob content.

        Args:
            blob_url: Full URL to blob

        Returns:
            Blob content as bytes
        """
        return self.blob_api.download_blob(blob_url)

    def extract_question_id_from_form_json(self, form_json: dict, filename: str) -> str | None:
        """
        Extract question ID for an attachment from form_json.

        Walks the form data tree to find the question whose value matches the filename.

        Args:
            form_json: Full form JSON data
            filename: Attachment filename to search for

        Returns:
            Question ID path (e.g., "/data/beneficiary_photo") or None
        """

        def search_dict(data, target_filename, path=""):
            """Recursively search for filename in nested dict structure"""
            if not isinstance(data, dict):
                return None

            for key, value in data.items():
                # Skip metadata and special fields
                if key in ["@xmlns", "@name", "@uiVersion", "@version", "meta", "#type", "attachments"]:
                    continue

                current_path = f"{path}/{key}" if path else key

                # Check if this value matches our filename
                if isinstance(value, str) and value == target_filename:
                    return current_path

                # Recursively search nested dicts
                if isinstance(value, dict):
                    result = search_dict(value, target_filename, current_path)
                    if result:
                        return result

            return None

        # Search in the form data
        form_data = form_json.get("form", form_json)
        question_path = search_dict(form_data, filename)
        return question_path

    def get_images_with_question_ids(self, visit_data: dict) -> list[dict]:
        """
        Build complete image metadata by combining images array with question_ids from form_json.

        Args:
            visit_data: Visit data dict with 'form_json' and 'images' fields

        Returns:
            List of dicts with blob_id, name, question_id, plus visit-level data:
            [
                {
                    "blob_id": "abc123",
                    "name": "photo.jpg",
                    "question_id": "/data/beneficiary_photo",
                    "username": "user123",
                    "visit_date": "2024-01-01T12:00:00Z",
                    "entity_name": "Entity Name"
                }
            ]
        """
        form_json = visit_data.get("form_json", {})
        images = visit_data.get("images", [])

        # Extract visit-level data to store with images
        username = visit_data.get("username") or visit_data.get("user_login") or ""
        visit_date = visit_data.get("visit_date") or ""
        entity_name = visit_data.get("entity_name") or "No Entity"

        result = []
        for image in images:
            question_id = self.extract_question_id_from_form_json(form_json, image["name"])
            result.append(
                {
                    "blob_id": image["blob_id"],
                    "name": image["name"],
                    "question_id": question_id,
                    "username": username,
                    "visit_date": visit_date,
                    "entity_name": entity_name,
                }
            )

        return result

    def download_image_from_connect(self, blob_id: str, opportunity_id: int) -> bytes:
        """
        Download image from Connect API.

        Args:
            blob_id: Blob ID to download
            opportunity_id: Opportunity ID for authorization

        Returns:
            Image content as bytes
        """
        # Use GET request with blob_id as query parameter
        response = self.http_client.get(
            f"{self.production_url}/export/opportunity/{opportunity_id}/image/", params={"blob_id": blob_id}
        )
        response.raise_for_status()
        return response.content

    # Connect API Helper Methods

    def _call_connect_api(self, endpoint: str) -> httpx.Response:
        """
        Make an API call to Connect production.

        Args:
            endpoint: API endpoint (e.g., "/export/opp_org_program_list/")

        Returns:
            httpx Response object
        """
        url = f"{self.production_url}{endpoint}"
        response = self.http_client.get(url)
        response.raise_for_status()
        return response

    def _fetch_visits_for_opportunity(self, opportunity_id: int) -> list[dict]:
        """
        Fetch all visits for an opportunity from Connect API.

        Uses centralized Labs caching - no project-specific caching logic needed.

        Args:
            opportunity_id: Opportunity ID

        Returns:
            List of visit dicts
        """
        from commcare_connect.labs.api_cache import fetch_user_visits_cached

        # Define the API call function
        def make_api_call():
            return self._call_connect_api(f"/export/opportunity/{opportunity_id}/user_visits/")

        # Use Labs centralized caching (handles cache check, fetch, store automatically)
        return fetch_user_visits_cached(
            request=self.request if hasattr(self, "request") else None,
            opportunity_id=opportunity_id,
            api_call_func=make_api_call,
        )

    def search_opportunities(self, query: str = "", limit: int = 100, program_id: int | None = None) -> list[dict]:
        """
        Search for opportunities.

        Args:
            query: Search query (name or ID)
            limit: Maximum results
            program_id: Optional program ID to filter by

        Returns:
            List of opportunity dicts
        """
        # Call Connect API
        response = self._call_connect_api("/export/opp_org_program_list/")
        data = response.json()

        opportunities_list = data.get("opportunities", [])
        results = []

        query_lower = query.lower().strip()
        for opp_data in opportunities_list:
            # Filter by program_id if provided
            if program_id and opp_data.get("program") != program_id:
                continue

            # Filter by query if provided
            if query_lower:
                opp_id_match = query_lower.isdigit() and int(query_lower) == opp_data.get("id")
                name_match = query_lower in opp_data.get("name", "").lower()
                if not (opp_id_match or name_match):
                    continue

            results.append(opp_data)

            if len(results) >= limit:
                break

        return results

    def get_opportunity_details(self, opportunity_id: int) -> dict | None:
        """
        Get detailed information about an opportunity.

        Args:
            opportunity_id: Opportunity ID

        Returns:
            Opportunity dict or None
        """
        # Search for this specific opportunity
        response = self._call_connect_api("/export/opp_org_program_list/")
        data = response.json()

        opportunities_list = data.get("opportunities", [])

        for opp_data in opportunities_list:
            if opp_data.get("id") == opportunity_id:
                return opp_data

        return None
