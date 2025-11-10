"""
Data Access Layer for Audit.

This layer wraps the generic ExperimentRecordAPI to provide audit-specific
data access methods. It handles:
1. Fetching visit/user/opportunity data dynamically from Connect OAuth APIs
2. Managing audit state in ExperimentRecords (templates, sessions)
3. Simulating blob metadata availability via CommCare HQ

This is an API-first architecture with no local data syncing.
"""

import os
import tempfile
from typing import Any

import httpx
import pandas as pd
from django.conf import settings
from django.db.models import QuerySet
from django.http import HttpRequest

from commcare_connect.audit.blob_api import BlobMetadataAPI
from commcare_connect.audit.experiment_models import AuditSessionRecord, AuditTemplateRecord
from commcare_connect.labs.api_helpers import ExperimentRecordAPI


class AuditDataAccess:
    """
    Data access layer for audit that uses ExperimentRecordAPI for state
    and fetches visit data dynamically from Connect OAuth APIs.
    """

    def __init__(self, access_token: str | None = None, request: HttpRequest | None = None):
        """
        Initialize the audit data access layer.

        Args:
            access_token: OAuth token for Connect production APIs
            request: HttpRequest object (for extracting token in labs mode)
        """
        # Get OAuth token
        if not access_token and request:
            from commcare_connect.audit.helpers import get_connect_oauth_token

            access_token = get_connect_oauth_token(request.user, request)

        if not access_token:
            raise ValueError("OAuth access token required for audit data access")

        self.access_token = access_token
        self.production_url = settings.CONNECT_PRODUCTION_URL.rstrip("/")

        # Initialize HTTP client with Bearer token
        self.http_client = httpx.Client(
            headers={"Authorization": f"Bearer {self.access_token}"},
            timeout=120.0,
        )

        # Initialize experiment API for state management
        self.experiment_api = ExperimentRecordAPI()

        # Initialize blob API for CommCare integration
        self.blob_api = BlobMetadataAPI()

    def close(self):
        """Close HTTP client."""
        if self.http_client:
            self.http_client.close()

    # Template Methods

    def create_audit_template(
        self,
        user_id: int,
        opportunity_ids: list[int],
        audit_type: str,
        granularity: str,
        criteria: dict,
        preview_data: list[dict] | None = None,
    ) -> AuditTemplateRecord:
        """
        Create a new audit template.

        Args:
            user_id: Creator user ID
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

        record = self.experiment_api.create_record(
            experiment="audit",
            type="AuditTemplate",
            data=data,
            user_id=user_id,
        )

        # Cast to AuditTemplateRecord proxy model
        record.__class__ = AuditTemplateRecord
        return record

    def get_audit_template(self, template_id: int) -> AuditTemplateRecord | None:
        """
        Get an audit template by ID.

        Args:
            template_id: Template ID

        Returns:
            AuditTemplateRecord or None
        """
        record = self.experiment_api.get_record_by_id(record_id=template_id, experiment="audit", type="AuditTemplate")

        if record:
            record.__class__ = AuditTemplateRecord
            return record
        return None

    def get_audit_templates(self, user_id: int | None = None) -> QuerySet[AuditTemplateRecord]:
        """
        Query audit templates.

        Args:
            user_id: Filter by creator user ID

        Returns:
            QuerySet of AuditTemplateRecord instances
        """
        qs = self.experiment_api.get_records(experiment="audit", type="AuditTemplate", user_id=user_id)

        # Cast to AuditTemplateRecord proxy model
        return AuditTemplateRecord.objects.filter(pk__in=qs.values_list("pk", flat=True))

    # Session Methods

    def create_audit_session(
        self,
        template_id: int,
        auditor_id: int,
        visit_ids: list[int],
        title: str,
        tag: str,
        opportunity_id: int | None = None,
    ) -> AuditSessionRecord:
        """
        Create a new audit session.

        Args:
            template_id: Parent template ID
            auditor_id: Auditor user ID
            visit_ids: List of visit IDs to audit
            title: Session title
            tag: Session tag
            opportunity_id: Primary opportunity ID

        Returns:
            AuditSessionRecord instance with empty visit_results
        """
        data = {
            "title": title,
            "tag": tag,
            "status": "in_progress",
            "overall_result": None,
            "notes": "",
            "kpi_notes": "",
            "visit_ids": visit_ids,
            "visit_results": {},  # Initialize empty
        }

        record = self.experiment_api.create_record(
            experiment="audit",
            type="AuditSession",
            data=data,
            parent_id=template_id,
            user_id=auditor_id,
            opportunity_id=opportunity_id,
        )

        # Cast to AuditSessionRecord proxy model
        record.__class__ = AuditSessionRecord
        return record

    def get_audit_session(self, session_id: int) -> AuditSessionRecord | None:
        """
        Get an audit session by ID.

        Args:
            session_id: Session ID

        Returns:
            AuditSessionRecord or None
        """
        record = self.experiment_api.get_record_by_id(record_id=session_id, experiment="audit", type="AuditSession")

        if record:
            record.__class__ = AuditSessionRecord
            return record
        return None

    def get_audit_sessions(
        self, auditor_id: int | None = None, status: str | None = None
    ) -> QuerySet[AuditSessionRecord]:
        """
        Query audit sessions.

        Args:
            auditor_id: Filter by auditor user ID
            status: Filter by status (in_progress, completed)

        Returns:
            QuerySet of AuditSessionRecord instances
        """
        data_filters = {}
        if status:
            data_filters["status"] = status

        qs = self.experiment_api.get_records(
            experiment="audit",
            type="AuditSession",
            user_id=auditor_id,
            data_filters=data_filters if data_filters else None,
        )

        # Cast to AuditSessionRecord proxy model
        return AuditSessionRecord.objects.filter(pk__in=qs.values_list("pk", flat=True))

    def save_audit_session(self, session: AuditSessionRecord) -> AuditSessionRecord:
        """
        Save in-memory changes to an audit session.

        Args:
            session: AuditSessionRecord with modified data

        Returns:
            Updated AuditSessionRecord
        """
        updated_record = self.experiment_api.update_record(record_id=session.id, data=session.data)

        # Cast to AuditSessionRecord
        updated_record.__class__ = AuditSessionRecord
        return updated_record

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
    ) -> list[int]:
        """
        Get list of visit IDs for audit based on criteria.

        Fetches from Connect OAuth API and applies filters.

        Args:
            opportunity_ids: List of opportunity IDs
            audit_type: Audit type (date_range, last_n_per_flw, etc.)
            criteria: Criteria dict with filtering parameters

        Returns:
            List of visit IDs
        """
        all_visits = []

        # Fetch visits for each opportunity
        for opp_id in opportunity_ids:
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
            count_per_flw = criteria.get("count_per_flw", 10)
            df = df.sort_values("visit_date", ascending=False)
            df = df.groupby("user_id").head(count_per_flw)

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

        # Return list of visit IDs
        return df["id"].tolist()

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

        Args:
            opportunity_id: Opportunity ID

        Returns:
            List of visit dicts
        """
        # Download visits CSV
        response = self._call_connect_api(f"/export/opportunity/{opportunity_id}/user_visits/")

        # Write to temp file and parse
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".csv") as tmp_file:
            for chunk in response.iter_bytes():
                tmp_file.write(chunk)
            tmp_path = tmp_file.name

        try:
            df = pd.read_csv(tmp_path)

            # Convert to list of dicts
            visits = []
            for _, row in df.iterrows():
                # Extract visit ID - Connect CSV uses 'completed_work_id' as the visit ID
                visit_id = None
                if "completed_work_id" in row and pd.notna(row["completed_work_id"]):
                    visit_id = int(row["completed_work_id"])
                elif "id" in row and pd.notna(row["id"]):
                    visit_id = int(row["id"])

                # Extract xform_id from form_json if available
                xform_id = None
                if "form_json" in row and pd.notna(row["form_json"]):
                    try:
                        import json

                        form_json = json.loads(row["form_json"])
                        xform_id = form_json.get("id")
                    except (json.JSONDecodeError, AttributeError):
                        pass

                # Extract user_id - need to look up from username since CSV doesn't have it
                user_id = None  # Would need to map username to user_id

                visit = {
                    "id": visit_id,
                    "xform_id": xform_id,
                    "visit_date": str(row["visit_date"]) if pd.notna(row.get("visit_date")) else None,
                    "entity_id": str(row["entity_id"]) if pd.notna(row.get("entity_id")) else None,
                    "entity_name": str(row["entity_name"]) if pd.notna(row.get("entity_name")) else None,
                    "status": str(row["status"]) if pd.notna(row.get("status")) else None,
                    "flagged": bool(row["flagged"]) if pd.notna(row.get("flagged")) else False,
                    "user_id": user_id,
                    "username": str(row["username"]) if pd.notna(row.get("username")) else None,
                    "opportunity_id": opportunity_id,
                    "form_json": row.get("form_json"),  # Include raw form_json for blob extraction
                }
                visits.append(visit)

            return visits

        finally:
            # Clean up temp file
            os.unlink(tmp_path)

    def search_opportunities(self, query: str = "", limit: int = 100) -> list[dict]:
        """
        Search for opportunities.

        Args:
            query: Search query (name or ID)
            limit: Maximum results

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
