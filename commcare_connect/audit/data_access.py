"""
Optimized Data Access Layer for Audit.

Uses the analysis pipeline's FieldComputation infrastructure for field extraction,
with optimized CSV caching that skips form_json parsing for selection operations.

Key optimizations:
1. Raw CSV caching - stores ~50MB instead of ~350MB parsed objects
2. skip_form_json for selection - doesn't parse form_json for preview/filtering
3. filter_visit_ids for extraction - only parses form_json for selected visits
4. Uses FieldComputation with custom extractors - leverages analysis pipeline infrastructure
"""

import logging
from dataclasses import dataclass

import httpx
import pandas as pd
from django.conf import settings
from django.http import HttpRequest

from commcare_connect.audit.analysis_config import AUDIT_EXTRACTION_CONFIG
from commcare_connect.audit.models import AuditSessionRecord, AuditTemplateRecord
from commcare_connect.labs.analysis.base import LocalUserVisit
from commcare_connect.labs.analysis.computations import compute_visit_fields
from commcare_connect.labs.api_cache import fetch_user_visits_cached
from commcare_connect.labs.integrations.connect.api_client import LabsRecordAPIClient

logger = logging.getLogger(__name__)


# =============================================================================
# Filtering Logic
# =============================================================================


@dataclass
class AuditCriteria:
    """Structured audit selection criteria."""

    audit_type: str = "date_range"
    start_date: str | None = None
    end_date: str | None = None
    count_per_flw: int = 10
    count_per_opp: int = 10
    count_across_all: int = 100
    sample_percentage: int = 100
    selected_flw_user_ids: list[str] | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "AuditCriteria":
        """Create from dict, handling both snake_case and camelCase keys."""
        return cls(
            audit_type=data.get("audit_type") or data.get("type", "date_range"),
            start_date=data.get("start_date") or data.get("startDate"),
            end_date=data.get("end_date") or data.get("endDate"),
            count_per_flw=data.get("count_per_flw") or data.get("countPerFlw", 10),
            count_per_opp=data.get("count_per_opp") or data.get("countPerOpp", 10),
            count_across_all=data.get("count_across_all") or data.get("countAcrossAll", 100),
            sample_percentage=data.get("sample_percentage") or data.get("samplePercentage", 100),
            selected_flw_user_ids=data.get("selected_flw_user_ids", []),
        )


def filter_visits_for_audit(
    visits: list[dict], criteria: AuditCriteria, return_visits: bool = False
) -> list[int] | list[dict]:
    """
    Filter visits based on audit criteria.

    Uses pandas for efficient filtering and sampling.

    Args:
        visits: List of visit dicts
        criteria: AuditCriteria with filter settings
        return_visits: If True, return filtered visit dicts instead of just IDs

    Returns:
        List of visit IDs (default) or list of filtered visit dicts (if return_visits=True)
    """
    if not visits:
        return []

    df = pd.DataFrame(visits)

    if "id" not in df.columns:
        return []

    # Parse dates
    if "visit_date" in df.columns:
        df["visit_date"] = pd.to_datetime(df["visit_date"], format="mixed", utc=True, errors="coerce")

    # Apply filters based on audit type
    if criteria.audit_type == "date_range":
        if criteria.start_date and "visit_date" in df.columns:
            start = pd.to_datetime(criteria.start_date)
            df = df[df["visit_date"].dt.date >= start.date()]
        if criteria.end_date and "visit_date" in df.columns:
            end = pd.to_datetime(criteria.end_date)
            df = df[df["visit_date"].dt.date <= end.date()]

    elif criteria.audit_type == "last_n_per_flw":
        if "visit_date" in df.columns and "username" in df.columns:
            df = df.sort_values("visit_date", ascending=False)
            df = df.groupby("username", dropna=False).head(criteria.count_per_flw)

    elif criteria.audit_type == "last_n_per_opp":
        if "visit_date" in df.columns and "opportunity_id" in df.columns:
            df = df.sort_values("visit_date", ascending=False)
            df = df.groupby("opportunity_id").head(criteria.count_per_opp)

    elif criteria.audit_type == "last_n_across_all":
        if "visit_date" in df.columns:
            df = df.sort_values("visit_date", ascending=False)
            df = df.head(criteria.count_across_all)

    # Filter by selected FLWs if provided
    if criteria.selected_flw_user_ids and "username" in df.columns:
        df = df[df["username"].isin(criteria.selected_flw_user_ids)]

    # Apply sample percentage
    if criteria.sample_percentage < 100 and len(df) > 0:
        sample_size = max(1, int(len(df) * criteria.sample_percentage / 100))
        df = df.sample(n=min(sample_size, len(df)), random_state=42)

    if return_visits:
        return df.to_dict("records")
    return df["id"].dropna().astype(int).unique().tolist()


def generate_audit_description(criteria: AuditCriteria) -> str:
    """Generate human-readable description of audit criteria."""
    parts = []

    if criteria.audit_type == "date_range":
        if criteria.start_date and criteria.end_date:
            parts.append(f"Visits from {criteria.start_date} to {criteria.end_date}")
        elif criteria.start_date:
            parts.append(f"Visits from {criteria.start_date}")
        elif criteria.end_date:
            parts.append(f"Visits until {criteria.end_date}")
        else:
            parts.append("All visits (date range)")
    elif criteria.audit_type == "last_n_per_flw":
        parts.append(f"Last {criteria.count_per_flw} visits per FLW")
    elif criteria.audit_type == "last_n_per_opp":
        parts.append(f"Last {criteria.count_per_opp} visits per opportunity")
    elif criteria.audit_type == "last_n_across_all":
        parts.append(f"Last {criteria.count_across_all} visits across all")
    else:
        parts.append(f"Audit type: {criteria.audit_type}")

    if criteria.sample_percentage < 100:
        parts.append(f"({criteria.sample_percentage}% sample)")

    return " ".join(parts)


# =============================================================================
# Main Data Access Class
# =============================================================================


class AuditDataAccess:
    """
    Optimized data access layer for audit operations.

    Uses the analysis pipeline's FieldComputation infrastructure for extraction,
    with optimized CSV caching for memory efficiency.
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

        Supports both old signature (access_token) and new (request).
        """
        self.request = request
        self.opportunity_id = opportunity_id
        self.organization_id = organization_id
        self.program_id = program_id

        # Use labs_context from middleware if available (takes precedence)
        if request and hasattr(request, "labs_context"):
            labs_context = request.labs_context or {}
            if not opportunity_id and "opportunity_id" in labs_context:
                self.opportunity_id = labs_context["opportunity_id"]
            if not program_id and "program_id" in labs_context:
                self.program_id = labs_context["program_id"]
            if not organization_id and "organization_id" in labs_context:
                self.organization_id = labs_context["organization_id"]

        # Get OAuth token from labs session if not provided
        if not access_token and request:
            labs_oauth = request.session.get("labs_oauth", {})
            access_token = labs_oauth.get("access_token")

        if not access_token:
            raise ValueError("OAuth access token required")

        self.access_token = access_token
        self.production_url = settings.CONNECT_PRODUCTION_URL.rstrip("/")

        # Lazy-initialized clients
        self._http_client: httpx.Client | None = None
        self._labs_api: LabsRecordAPIClient | None = None

    @property
    def http_client(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(
                headers={"Authorization": f"Bearer {self.access_token}"},
                timeout=120.0,
            )
        return self._http_client

    @property
    def labs_api(self) -> LabsRecordAPIClient:
        if self._labs_api is None:
            self._labs_api = LabsRecordAPIClient(
                self.access_token,
                opportunity_id=self.opportunity_id,
                organization_id=self.organization_id,
                program_id=self.program_id,
            )
        return self._labs_api

    def close(self):
        if self._http_client:
            self._http_client.close()
        if self._labs_api:
            self._labs_api.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # =========================================================================
    # Visit Fetching (Optimized)
    # =========================================================================

    def _make_api_call(self, opportunity_id: int):
        def call():
            url = f"{self.production_url}/export/opportunity/{opportunity_id}/user_visits/"
            return self.http_client.get(url)

        return call

    def fetch_visits_slim(self, opportunity_id: int | None = None) -> list[dict]:
        """Fetch visits WITHOUT form_json (~20MB for 10k visits vs ~350MB)."""
        opp_id = opportunity_id or self.opportunity_id
        if not opp_id:
            raise ValueError("opportunity_id required")

        return fetch_user_visits_cached(
            request=self.request,
            opportunity_id=opp_id,
            api_call_func=self._make_api_call(opp_id),
            skip_form_json=True,
        )

    def fetch_visits_for_ids(self, visit_ids: list[int], opportunity_id: int | None = None) -> list[dict]:
        """Fetch visits WITH form_json for specific IDs only (chunked, memory efficient)."""
        opp_id = opportunity_id or self.opportunity_id
        if not opp_id:
            raise ValueError("opportunity_id required")

        return fetch_user_visits_cached(
            request=self.request,
            opportunity_id=opp_id,
            api_call_func=self._make_api_call(opp_id),
            filter_visit_ids=set(visit_ids),
        )

    # =========================================================================
    # Visit Selection (uses slim fetching)
    # =========================================================================

    def get_visit_ids_for_audit(
        self,
        opportunity_ids: list[int],
        audit_type: str | None = None,
        criteria: AuditCriteria | dict | None = None,
        visits_cache: dict[int, list[dict]] | None = None,
        return_visits: bool = False,
    ) -> list[int] | tuple[list[int], list[dict]]:
        """
        Get visit IDs matching audit criteria. Uses slim fetching (no form_json).

        Supports both old signature (audit_type + criteria dict) and new (AuditCriteria).

        Args:
            return_visits: If True, returns (visit_ids, filtered_visits) tuple to avoid re-fetching
        """
        # Handle both old and new calling patterns
        if criteria is None:
            criteria = AuditCriteria()
        elif isinstance(criteria, dict):
            # Merge audit_type into criteria dict if provided separately
            if audit_type and "audit_type" not in criteria:
                criteria["audit_type"] = audit_type
            criteria = AuditCriteria.from_dict(criteria)

        all_visits = []
        for opp_id in opportunity_ids:
            if visits_cache and opp_id in visits_cache:
                visits = visits_cache[opp_id]
            else:
                visits = self.fetch_visits_slim(opp_id)
            all_visits.extend(visits)

        filtered_visits = filter_visits_for_audit(all_visits, criteria, return_visits=True)
        visit_ids = [v["id"] for v in filtered_visits]

        if return_visits:
            return visit_ids, filtered_visits
        return visit_ids

    # COMMENTED OUT - Not used in current implementation
    # def get_visits_with_flw_info(
    #     self,
    #     visit_ids: list[int],
    #     opportunity_id: int | None = None,
    # ) -> list[dict]:
    #     """Get slim visit data for specific IDs (for FLW grouping)."""
    #     opp_id = opportunity_id or self.opportunity_id
    #     if not opp_id:
    #         raise ValueError("opportunity_id required")
    #
    #     all_visits = self.fetch_visits_slim(opp_id)
    #     visit_id_set = set(visit_ids)
    #     return [v for v in all_visits if v.get("id") in visit_id_set]

    # =========================================================================
    # Visit Data Methods
    # =========================================================================

    def _fetch_visits_for_opportunity(self, opportunity_id: int) -> list[dict]:
        """Fetch all visits for an opportunity (with form_json for backward compat)."""
        return fetch_user_visits_cached(
            request=self.request,
            opportunity_id=opportunity_id,
            api_call_func=self._make_api_call(opportunity_id),
        )

    def get_visit_data(
        self, visit_id: int, opportunity_id: int | None = None, visit_cache: dict | None = None
    ) -> dict | None:
        """Get detailed data for a single visit."""
        if visit_cache and visit_id in visit_cache:
            return visit_cache[visit_id]

        opp_id = opportunity_id or self.opportunity_id
        if not opp_id:
            raise ValueError("opportunity_id required when visit_cache not provided")

        visits = self._fetch_visits_for_opportunity(opp_id)
        for visit in visits:
            if visit["id"] == visit_id:
                return visit

        return None

    def get_visits_batch(self, visit_ids: list[int], opportunity_id: int) -> list[dict]:
        """Batch fetch multiple visits."""
        all_visits = self._fetch_visits_for_opportunity(opportunity_id)
        visit_id_set = set(visit_ids)
        return [v for v in all_visits if v["id"] in visit_id_set]

    # =========================================================================
    # Image Extraction (uses analysis pipeline's FieldComputation)
    # =========================================================================

    def extract_images_for_visits(
        self,
        visit_ids: list[int],
        opportunity_id: int | None = None,
    ) -> dict[str, list]:
        """
        Extract images with question IDs for selected visits.

        Uses the analysis pipeline's compute_visit_fields with custom extractor.
        Memory efficient - only loads form_json for selected visits.

        Returns:
            Dict mapping visit_id (str) to list of image dicts
        """
        if not visit_ids:
            return {}

        opp_id = opportunity_id or self.opportunity_id

        # Fetch visits WITH form_json for selected IDs only
        visit_dicts = self.fetch_visits_for_ids(visit_ids, opp_id)

        # Convert to LocalUserVisit for pipeline compatibility
        visits = [LocalUserVisit(v) for v in visit_dicts]

        # Use the analysis pipeline's compute_visit_fields with our audit config
        computed = compute_visit_fields(visits, AUDIT_EXTRACTION_CONFIG.fields)

        # Build result mapping
        result = {}
        for i, visit in enumerate(visits):
            visit_id = visit.id
            if computed and i < len(computed):
                images = computed[i].get("images_with_questions", [])
            else:
                images = []
            result[str(visit_id)] = images

        # Add empty lists for any visit_ids not found
        for vid in visit_ids:
            if str(vid) not in result:
                result[str(vid)] = []

        return result

    # =========================================================================
    # Template Management
    # =========================================================================

    def create_audit_template(
        self,
        username: str,
        opportunity_ids: list[int],
        audit_type: str | None = None,
        granularity: str = "combined",
        criteria: AuditCriteria | dict | None = None,
        preview_data: list[dict] | None = None,
    ) -> AuditTemplateRecord:
        """Create an audit template. Supports both old and new calling patterns."""
        if criteria is None:
            criteria = AuditCriteria(audit_type=audit_type or "date_range")
        elif isinstance(criteria, dict):
            if audit_type and "audit_type" not in criteria:
                criteria["audit_type"] = audit_type
            criteria = AuditCriteria.from_dict(criteria)

        data = {
            "opportunity_ids": opportunity_ids,
            "audit_type": criteria.audit_type,
            "granularity": granularity,
            "preview_data": preview_data or [],
            "start_date": criteria.start_date,
            "end_date": criteria.end_date,
            "count_per_flw": criteria.count_per_flw,
            "count_per_opp": criteria.count_per_opp,
            "count_across_all": criteria.count_across_all,
            "sample_percentage": criteria.sample_percentage,
        }

        record = self.labs_api.create_record(
            experiment="audit",
            type="AuditTemplate",
            data=data,
            username=username,
        )

        return AuditTemplateRecord(
            {
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
        )

    # COMMENTED OUT - Not used in current implementation
    # def get_audit_template(self, template_id: int) -> AuditTemplateRecord | None:
    #     return self.labs_api.get_record_by_id(
    #         record_id=template_id,
    #         experiment="audit",
    #         type="AuditTemplate",
    #         model_class=AuditTemplateRecord,
    #     )

    # COMMENTED OUT - Not used in current implementation
    # def get_audit_templates(self, username: str | None = None) -> list[AuditTemplateRecord]:
    #     return self.labs_api.get_records(
    #         experiment="audit",
    #         type="AuditTemplate",
    #         username=username,
    #         model_class=AuditTemplateRecord,
    #     )

    # =========================================================================
    # Session Management
    # =========================================================================

    def create_audit_session(
        self,
        template_id: int,
        username: str,
        visit_ids: list[int],
        title: str,
        tag: str = "",
        opportunity_id: int | None = None,
        audit_type: str | None = None,
        criteria: AuditCriteria | dict | None = None,
        visits_cache: list[dict] | None = None,  # Kept for backward compat, not used
        opportunity_name: str | None = None,  # Pass to avoid redundant API call
        visit_images: dict[str, list] | None = None,  # Pass pre-extracted images for batch operations
    ) -> AuditSessionRecord:
        """Create an audit session with extracted image metadata."""
        opp_id = opportunity_id or self.opportunity_id

        # Get opportunity name (use passed value to avoid redundant API calls in batch operations)
        if opportunity_name is None:
            opportunity_name = ""
            if opp_id:
                opp_details = self.get_opportunity_details(opp_id)
                if opp_details:
                    opportunity_name = opp_details.get("name", "")

        # Generate description
        description = ""
        if criteria:
            if isinstance(criteria, dict):
                if audit_type and "audit_type" not in criteria:
                    criteria["audit_type"] = audit_type
                criteria = AuditCriteria.from_dict(criteria)
            description = generate_audit_description(criteria)

        # Extract images (use passed value to avoid redundant CSV parsing in batch operations)
        if visit_images is None:
            visit_images = self.extract_images_for_visits(visit_ids, opp_id)

        data = {
            "title": title,
            "tag": tag,
            "status": "in_progress",
            "overall_result": None,
            "notes": "",
            "kpi_notes": "",
            "visit_ids": visit_ids,
            "visit_results": {},
            "opportunity_id": opp_id,
            "opportunity_name": opportunity_name,
            "description": description,
            "visit_images": visit_images,
        }

        record = self.labs_api.create_record(
            experiment="audit",
            type="AuditSession",
            data=data,
            labs_record_id=template_id,
            username=username,
        )

        return AuditSessionRecord(
            {
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
        )

    def get_audit_session(
        self, session_id: int, try_multiple_opportunities: bool = False
    ) -> AuditSessionRecord | None:
        """Get an audit session by ID."""
        # First try with current opportunity_id
        sessions = self.labs_api.get_records(
            experiment="audit",
            type="AuditSession",
            model_class=AuditSessionRecord,
        )

        for session in sessions:
            if session.id == session_id:
                return session

        # If not found and try_multiple_opportunities is True, search other opportunities
        if try_multiple_opportunities:
            try:
                opportunities = self.search_opportunities(query="", limit=1000)

                for opp in opportunities:
                    opp_id = opp.get("id")
                    if opp_id == self.opportunity_id:
                        continue

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
                pass

        return None

    def get_audit_sessions(
        self,
        username: str | None = None,
        status: str | None = None,
    ) -> list[AuditSessionRecord]:
        """Query audit sessions."""
        kwargs = {}
        if status:
            kwargs["status"] = status

        return self.labs_api.get_records(
            experiment="audit",
            type="AuditSession",
            username=username,
            model_class=AuditSessionRecord,
            **kwargs,
        )

    def save_audit_session(self, session: AuditSessionRecord) -> AuditSessionRecord:
        updated = self.labs_api.update_record(
            record_id=session.id,
            experiment="audit",
            type="AuditSession",
            data=session.data,
            username=session.username,
        )

        return AuditSessionRecord(
            {
                "id": updated.id,
                "experiment": updated.experiment,
                "type": updated.type,
                "data": updated.data,
                "username": updated.username,
                "opportunity_id": updated.opportunity_id,
                "organization_id": updated.organization_id,
                "program_id": updated.program_id,
                "labs_record_id": updated.labs_record_id,
            }
        )

    def complete_audit_session(
        self,
        session: AuditSessionRecord,
        overall_result: str,
        notes: str = "",
        kpi_notes: str = "",
    ) -> AuditSessionRecord:
        session.data["status"] = "completed"
        session.data["overall_result"] = overall_result
        session.data["notes"] = notes
        session.data["kpi_notes"] = kpi_notes
        return self.save_audit_session(session)

    # =========================================================================
    # Opportunity/Image APIs
    # =========================================================================

    def get_opportunity_details(self, opportunity_id: int) -> dict | None:
        url = f"{self.production_url}/export/opp_org_program_list/"
        response = self.http_client.get(url)
        response.raise_for_status()

        for opp in response.json().get("opportunities", []):
            if opp.get("id") == opportunity_id:
                return opp
        return None

    def search_opportunities(self, query: str = "", limit: int = 100, program_id: int | None = None) -> list[dict]:
        """Search for opportunities."""
        url = f"{self.production_url}/export/opp_org_program_list/"
        response = self.http_client.get(url)
        response.raise_for_status()

        results = []
        query_lower = query.lower().strip()

        for opp in response.json().get("opportunities", []):
            # Filter by program_id if provided
            if program_id and opp.get("program") != program_id:
                continue

            if query_lower:
                if not (
                    (query_lower.isdigit() and int(query_lower) == opp.get("id"))
                    or query_lower in opp.get("name", "").lower()
                ):
                    continue
            results.append(opp)
            if len(results) >= limit:
                break

        return results

    def download_image_from_connect(self, blob_id: str, opportunity_id: int) -> bytes:
        """Download image from Connect API."""
        response = self.http_client.get(
            f"{self.production_url}/export/opportunity/{opportunity_id}/image/",
            params={"blob_id": blob_id},
        )
        response.raise_for_status()
        return response.content
