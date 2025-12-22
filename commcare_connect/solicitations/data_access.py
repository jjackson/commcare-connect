"""
Data Access Layer for Solicitations.

This layer uses LabsRecordAPIClient to interact with production LabsRecord API.
It handles casting API responses to typed proxy models
(SolicitationRecord, ResponseRecord, ReviewRecord).

This is a pure API client with no local database storage.
"""

import httpx
from django.conf import settings
from django.http import HttpRequest

from commcare_connect.labs.integrations.connect.api_client import LabsRecordAPIClient
from commcare_connect.solicitations.models import (
    DeliveryTypeDescriptionRecord,
    OppOrgEnrichmentRecord,
    ResponseRecord,
    ReviewRecord,
    SolicitationRecord,
)


class SolicitationDataAccess:
    """
    Data access layer for solicitations that uses LabsRecordAPIClient.

    This class provides solicitation-specific methods and handles casting
    API responses to appropriate proxy model types.
    """

    def __init__(
        self,
        organization_id: int | None = None,
        program_id: int | None = None,
        access_token: str | None = None,
        request: HttpRequest | None = None,
    ):
        """Initialize solicitations data access.

        Args:
            organization_id: Optional organization ID for API scoping
            program_id: Optional program ID for API scoping
            access_token: OAuth Bearer token for production API
            request: HttpRequest object (for extracting token and org context in labs mode)

        Note: Solicitations use program_id (for solicitation queries) and
        organization_id (for response queries). They do NOT use opportunity_id.
        """
        self.organization_id = organization_id
        self.program_id = program_id

        # Use labs_context from middleware if available (takes precedence)
        if request and hasattr(request, "labs_context"):
            labs_context = request.labs_context
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
            raise ValueError("OAuth access token required for solicitation data access")

        self.access_token = access_token
        self.labs_api = LabsRecordAPIClient(
            access_token,
            organization_id=self.organization_id,
            program_id=self.program_id,
        )

    # =========================================================================
    # Delivery Type Methods
    # =========================================================================

    def get_delivery_types(self, active_only: bool = True) -> list[DeliveryTypeDescriptionRecord]:
        """
        Get all delivery types (public records, no scope required).

        Args:
            active_only: If True, only return active delivery types

        Returns:
            List of DeliveryTypeDescriptionRecord instances sorted by name
        """
        records = self.labs_api.get_records(
            experiment="solicitations",
            type="DeliveryTypeDescriptionRecord",
            public=True,
            model_class=DeliveryTypeDescriptionRecord,
        )

        # Filter to active only if requested
        if active_only:
            records = [r for r in records if r.is_active]

        # Sort by name alphabetically
        records.sort(key=lambda r: r.name.lower())

        return records

    def get_delivery_type_by_slug(self, slug: str) -> DeliveryTypeDescriptionRecord | None:
        """
        Get a specific delivery type by slug.

        Args:
            slug: URL-safe slug identifier

        Returns:
            DeliveryTypeDescriptionRecord instance or None
        """
        records = self.labs_api.get_records(
            experiment="solicitations",
            type="DeliveryTypeDescriptionRecord",
            public=True,
            model_class=DeliveryTypeDescriptionRecord,
            slug=slug,
        )
        return records[0] if records else None

    # =========================================================================
    # Opportunity Enrichment Methods
    # =========================================================================

    def get_enrichment_record(self) -> OppOrgEnrichmentRecord | None:
        """
        Get the OppOrgEnrichmentRecord containing enrichment data for opportunities.

        Returns:
            OppOrgEnrichmentRecord instance or None if not found
        """
        records = self.labs_api.get_records(
            experiment="solicitations",
            type="OppOrgEnrichmentRecord",
            public=True,
            model_class=OppOrgEnrichmentRecord,
        )
        return records[0] if records else None

    def get_opp_org_program_data(self) -> tuple[list[dict], list[dict], dict[int, str]]:
        """
        Fetch opportunities, programs from Connect Prod API and build program->delivery_type lookup.

        Returns:
            Tuple of (opportunities, programs, program_delivery_type_map)
            - opportunities: List of opportunity dicts
            - programs: List of program dicts
            - program_delivery_type_map: Dict mapping program_id to delivery_type_slug
        """
        url = f"{settings.CONNECT_PRODUCTION_URL}/export/opp_org_program_list/"
        headers = {"Authorization": f"Bearer {self.access_token}"}

        try:
            response = httpx.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            data = response.json()

            opportunities = data.get("opportunities", [])
            programs = data.get("programs", [])

            # Build program_id -> delivery_type_slug lookup
            program_delivery_type_map = {}
            for prog in programs:
                prog_id = prog.get("id")
                delivery_type = prog.get("delivery_type")
                if prog_id and delivery_type:
                    program_delivery_type_map[prog_id] = delivery_type

            return opportunities, programs, program_delivery_type_map
        except httpx.HTTPError:
            return [], [], {}

    def get_opportunities_from_prod(self) -> list[dict]:
        """
        Fetch all opportunities from Connect Prod API.

        Returns:
            List of opportunity dictionaries from prod
        """
        opportunities, _, _ = self.get_opp_org_program_data()
        return opportunities

    def get_opportunity_by_id(self, opp_id: int) -> dict | None:
        """
        Get a single opportunity by ID with enrichment data.

        Args:
            opp_id: The opportunity ID

        Returns:
            Enriched opportunity dict or None if not found
        """
        # Fetch all data from prod
        opportunities, programs, program_delivery_type_map = self.get_opp_org_program_data()

        # Build program lookup for additional info
        program_map = {p["id"]: p for p in programs}

        # Find the opportunity
        opp = None
        for o in opportunities:
            if o.get("id") == opp_id:
                opp = o
                break

        if not opp:
            return None

        # Fetch enrichment data
        enrichment_record = self.get_enrichment_record()

        # Get delivery type
        opp_delivery_type = self._get_opp_delivery_type(opp, program_delivery_type_map, enrichment_record)

        # Get enrichment data
        enrichment = None
        if enrichment_record:
            enrichment = enrichment_record.get_enrichment_for_opp(opp_id)

        # Build enriched opportunity
        enriched_opp = opp.copy()
        enriched_opp["delivery_type_slug"] = opp_delivery_type

        # Add program info
        program_id = opp.get("program")
        if program_id and program_id in program_map:
            program = program_map[program_id]
            enriched_opp["program_name"] = program.get("name", "")
            enriched_opp["program_currency"] = program.get("currency", "")
        else:
            enriched_opp["program_name"] = ""
            enriched_opp["program_currency"] = ""

        # Add enrichment fields
        if enrichment:
            enriched_opp["opp_country"] = enrichment.get("opp_country", "")
            enriched_opp["amount_raised"] = enrichment.get("amount_raised", 0)
            enriched_opp["budget_goal"] = enrichment.get("budget_goal", 0)
            enriched_opp["visits_target"] = enrichment.get("visits_target", 0)
            enriched_opp["org_photo_url"] = enrichment.get("org_photo_url", "")
            enriched_opp["opp_description"] = enrichment.get("opp_description", "")
        else:
            enriched_opp["opp_country"] = ""
            enriched_opp["amount_raised"] = 0
            enriched_opp["budget_goal"] = 0
            enriched_opp["visits_target"] = 0
            enriched_opp["org_photo_url"] = ""
            enriched_opp["opp_description"] = ""

        # Calculate progress percentages
        visit_count = enriched_opp.get("visit_count", 0)
        visits_target = enriched_opp.get("visits_target", 0)
        amount_raised = enriched_opp.get("amount_raised", 0)
        budget_goal = enriched_opp.get("budget_goal", 0)

        enriched_opp["visits_progress_pct"] = (
            min(100, int((visit_count / visits_target) * 100)) if visits_target > 0 else 0
        )
        enriched_opp["funding_progress_pct"] = (
            min(100, int((amount_raised / budget_goal) * 100)) if budget_goal > 0 else 0
        )

        return enriched_opp

    def _get_opp_delivery_type(
        self,
        opp: dict,
        program_delivery_type_map: dict[int, str],
        enrichment_record,
    ) -> str | None:
        """
        Determine delivery type for an opportunity.

        Priority:
        1. If opp has a program, use program's delivery_type
        2. Otherwise, fall back to enrichment record (for legacy opps without program)

        Args:
            opp: Opportunity dict from prod API
            program_delivery_type_map: Dict mapping program_id to delivery_type_slug
            enrichment_record: OppOrgEnrichmentRecord or None

        Returns:
            delivery_type_slug or None if not determinable
        """
        opp_id = opp.get("id")
        program_id = opp.get("program")

        # Primary: Get from program's delivery_type
        if program_id and program_id in program_delivery_type_map:
            return program_delivery_type_map[program_id]

        # Fallback: Get from enrichment record (for legacy opps without program)
        if enrichment_record:
            enrichment = enrichment_record.get_enrichment_for_opp(opp_id)
            if enrichment:
                return enrichment.get("delivery_type_slug")

        return None

    def get_opportunities_by_delivery_type(
        self,
        delivery_type_slug: str,
        min_visits: int = 0,
        include_inactive: bool = False,
    ) -> list[dict]:
        """
        Get opportunities filtered by delivery type slug and minimum visits.

        Delivery type is determined by:
        1. Program's delivery_type (primary - for opps with a program)
        2. Enrichment record (fallback - for legacy opps without program)

        Additional enrichment data (country, etc.) comes from OppOrgEnrichmentRecord.

        Args:
            delivery_type_slug: The delivery type slug to filter by
            min_visits: Minimum visit threshold (default: 0)
            include_inactive: Include inactive/ended opportunities (default: False)

        Returns:
            List of opportunity dicts with enrichment data merged in
        """
        # Fetch opportunities and program data from prod
        opportunities, _, program_delivery_type_map = self.get_opp_org_program_data()

        # Fetch enrichment data for additional fields and legacy fallback
        enrichment_record = self.get_enrichment_record()

        # Filter and enrich opportunities
        results = []
        for opp in opportunities:
            opp_id = opp.get("id")
            visit_count = opp.get("visit_count", 0)

            # Apply min_visits filter
            if visit_count < min_visits:
                continue

            # Apply active filter
            if not include_inactive and not opp.get("is_active", False):
                continue

            # Get delivery type (from program or enrichment fallback)
            opp_delivery_type = self._get_opp_delivery_type(opp, program_delivery_type_map, enrichment_record)

            # Only include if delivery type matches
            if opp_delivery_type != delivery_type_slug:
                continue

            # Get enrichment data for this opportunity
            enrichment = None
            if enrichment_record:
                enrichment = enrichment_record.get_enrichment_for_opp(opp_id)

            # Merge enrichment data into opportunity
            enriched_opp = opp.copy()
            enriched_opp["delivery_type_slug"] = opp_delivery_type

            # Add enrichment fields (with defaults)
            if enrichment:
                enriched_opp["opp_country"] = enrichment.get("opp_country", "")
                enriched_opp["amount_raised"] = enrichment.get("amount_raised", 0)
                enriched_opp["budget_goal"] = enrichment.get("budget_goal", 0)
                enriched_opp["visits_target"] = enrichment.get("visits_target", 0)
                enriched_opp["org_photo_url"] = enrichment.get("org_photo_url", "")
                enriched_opp["opp_description"] = enrichment.get("opp_description", "")
            else:
                enriched_opp["opp_country"] = ""
                enriched_opp["amount_raised"] = 0
                enriched_opp["budget_goal"] = 0
                enriched_opp["visits_target"] = 0
                enriched_opp["org_photo_url"] = ""
                enriched_opp["opp_description"] = ""

            # Calculate progress percentages
            visit_count = enriched_opp.get("visit_count", 0)
            visits_target = enriched_opp.get("visits_target", 0)
            amount_raised = enriched_opp.get("amount_raised", 0)
            budget_goal = enriched_opp.get("budget_goal", 0)

            enriched_opp["visits_progress_pct"] = (
                min(100, int((visit_count / visits_target) * 100)) if visits_target > 0 else 0
            )
            enriched_opp["funding_progress_pct"] = (
                min(100, int((amount_raised / budget_goal) * 100)) if budget_goal > 0 else 0
            )

            results.append(enriched_opp)

        return results

    def get_opportunity_counts_by_delivery_type(
        self,
        min_visits: int = 0,
    ) -> dict[str, dict]:
        """
        Get counts of opportunities grouped by delivery type.

        Delivery type is determined by:
        1. Program's delivery_type (primary - for opps with a program)
        2. Enrichment record (fallback - for legacy opps without program)

        Args:
            min_visits: Minimum visit threshold (default: 0)

        Returns:
            Dict mapping delivery_type_slug to counts:
            {
                "chc": {"active": 5, "completed": 3, "total": 8},
                "kmc": {"active": 2, "completed": 1, "total": 3},
            }
        """
        # Fetch opportunities and program data from prod
        opportunities, _, program_delivery_type_map = self.get_opp_org_program_data()

        # Fetch enrichment data for legacy fallback
        enrichment_record = self.get_enrichment_record()

        # Count by delivery type
        counts: dict[str, dict] = {}

        for opp in opportunities:
            visit_count = opp.get("visit_count", 0)

            # Apply min_visits filter
            if visit_count < min_visits:
                continue

            # Get delivery type (from program or enrichment fallback)
            delivery_type_slug = self._get_opp_delivery_type(opp, program_delivery_type_map, enrichment_record)
            if not delivery_type_slug:
                continue

            # Initialize counts for this delivery type
            if delivery_type_slug not in counts:
                counts[delivery_type_slug] = {"active": 0, "completed": 0, "total": 0}

            # Increment counts
            counts[delivery_type_slug]["total"] += 1
            if opp.get("is_active", False):
                counts[delivery_type_slug]["active"] += 1
            else:
                counts[delivery_type_slug]["completed"] += 1

        return counts

    # =========================================================================
    # Public Solicitation Methods
    # =========================================================================

    def get_public_solicitations(
        self,
        status: str | None = "active",
        delivery_type_slug: str | None = None,
    ) -> list[SolicitationRecord]:
        """
        Get publicly listed solicitations (no scope required).

        Args:
            status: Filter by status (default: 'active')
            delivery_type_slug: Filter by delivery type slug

        Returns:
            List of SolicitationRecord instances
        """
        kwargs = {}
        if status:
            kwargs["status"] = status
        # Note: We don't filter by is_publicly_listed here because:
        # 1. public=True on the API call already ensures we get publicly queryable records
        # 2. The production API has a bug where boolean query params become strings
        #    (e.g., data__is_publicly_listed=true becomes string "true", not boolean true)
        if delivery_type_slug:
            kwargs["delivery_type_slug"] = delivery_type_slug

        return self.labs_api.get_records(
            experiment="solicitations",
            type="Solicitation",
            public=True,
            model_class=SolicitationRecord,
            **kwargs,
        )

    def get_solicitations_by_delivery_type(
        self,
        delivery_type_slug: str,
        status: str | None = "active",
    ) -> list[SolicitationRecord]:
        """
        Get solicitations filtered by delivery type.

        Args:
            delivery_type_slug: Delivery type slug to filter by
            status: Filter by status (default: 'active')

        Returns:
            List of SolicitationRecord instances
        """
        return self.get_public_solicitations(
            status=status,
            delivery_type_slug=delivery_type_slug,
        )

    # =========================================================================
    # Solicitation CRUD Methods
    # =========================================================================

    def get_solicitations(
        self,
        program_id: int | None = None,
        status: str | None = None,
        solicitation_type: str | None = None,
        is_publicly_listed: bool | None = None,
        username: str | None = None,
    ) -> list[SolicitationRecord]:
        """
        Query for solicitation records with optional filters.

        Args:
            program_id: Filter by production program ID
            status: Filter by status ('active', 'closed', 'draft')
            solicitation_type: Filter by type ('eoi', 'rfp')
            is_publicly_listed: Filter by public listing status
            username: Filter by username who created the solicitation (client-side filter)

        Returns:
            List of SolicitationRecord instances
        """
        # Build kwargs for data field filters
        kwargs = {}
        if status:
            kwargs["status"] = status
        if solicitation_type:
            kwargs["solicitation_type"] = solicitation_type
        if is_publicly_listed is not None:
            kwargs["is_publicly_listed"] = is_publicly_listed

        # Get records from API (don't send username - production doesn't support it)
        records = self.labs_api.get_records(
            experiment="solicitations",
            type="Solicitation",
            program_id=program_id,
            model_class=SolicitationRecord,
            **kwargs,
        )

        # Filter by username client-side if specified
        if username:
            records = [r for r in records if r.username == username]

        return records

    def get_solicitation_by_id(self, solicitation_id: int) -> SolicitationRecord | None:
        """
        Get a single solicitation record by ID.

        Args:
            solicitation_id: ID of the solicitation

        Returns:
            SolicitationRecord instance or None
        """
        return self.labs_api.get_record_by_id(
            record_id=solicitation_id, experiment="solicitations", type="Solicitation", model_class=SolicitationRecord
        )

    def create_solicitation(self, program_id: int, username: str, data_dict: dict) -> SolicitationRecord:
        """
        Create a new solicitation via production API.

        Args:
            program_id: Production program ID
            username: Username who created this
            data_dict: Dictionary containing solicitation data

        Returns:
            SolicitationRecord instance
        """
        # Set public=True if solicitation is publicly listed
        is_public = data_dict.get("is_publicly_listed", False)

        return self.labs_api.create_record(
            experiment="solicitations",
            type="Solicitation",
            data=data_dict,
            program_id=program_id,
            username=username,
            public=is_public,
        )

    def get_responses_for_solicitation(
        self, solicitation_record: SolicitationRecord, status: str | None = None
    ) -> list[ResponseRecord]:
        """
        Get all responses for a solicitation.

        Args:
            solicitation_record: Solicitation to find responses for
            status: Optional status filter ('draft', 'submitted')

        Returns:
            List of ResponseRecord instances
        """
        kwargs = {}
        if status:
            kwargs["status"] = status

        return self.labs_api.get_records(
            experiment="solicitations",
            type="SolicitationResponse",
            labs_record_id=solicitation_record.id,
            model_class=ResponseRecord,
            **kwargs,
        )

    def get_response_for_solicitation(
        self,
        solicitation_record: SolicitationRecord,
        organization_id: str,
        username: str | None = None,
        status: str | None = None,
    ) -> ResponseRecord | None:
        """
        Find a response by a specific organization for a solicitation.

        Args:
            solicitation_record: Solicitation to find response for
            organization_id: Organization slug/ID that submitted the response
            username: Optional username filter
            status: Optional status filter ('draft', 'submitted')

        Returns:
            ResponseRecord instance or None
        """
        kwargs = {}
        if status:
            kwargs["status"] = status

        records = self.labs_api.get_records(
            experiment="solicitations",
            type="SolicitationResponse",
            labs_record_id=solicitation_record.id,
            organization_id=organization_id,
            username=username,
            model_class=ResponseRecord,
            **kwargs,
        )

        return records[0] if records else None

    def get_response_by_id(self, response_id: int) -> ResponseRecord | None:
        """
        Get a single response record by ID.

        Args:
            response_id: ID of the response

        Returns:
            ResponseRecord instance or None
        """
        return self.labs_api.get_record_by_id(
            record_id=response_id, experiment="solicitations", type="SolicitationResponse", model_class=ResponseRecord
        )

    def create_response(
        self,
        solicitation_record: SolicitationRecord,
        username: str,
        data_dict: dict,
        organization_id: str | None = None,
    ) -> ResponseRecord:
        """
        Create a new response via production API.

        Args:
            solicitation_record: Solicitation being responded to
            username: Username submitting the response
            data_dict: Dictionary containing response data
            organization_id: Organization slug submitting the response (stored in data)

        Returns:
            ResponseRecord instance
        """
        # Store organization_id in data dict for tracking
        if organization_id:
            data_dict["organization_id"] = organization_id

        record = self.labs_api.create_record(
            experiment="solicitations",
            type="SolicitationResponse",
            data=data_dict,
            labs_record_id=solicitation_record.id,
            username=username,
            program_id=solicitation_record.program_id,
        )
        # Cast to ResponseRecord for proper typing
        return ResponseRecord(record.to_api_dict() if hasattr(record, "to_api_dict") else record.__dict__)

    def update_solicitation(
        self, record_id: int, data_dict: dict, program_id: int | None = None
    ) -> SolicitationRecord:
        """
        Update an existing solicitation via production API.

        Args:
            record_id: ID of the solicitation record to update
            data_dict: Dictionary containing updated solicitation data
            program_id: Program ID (optional, uses existing if not provided)

        Returns:
            Updated SolicitationRecord instance
        """
        record = self.labs_api.update_record(
            record_id=record_id,
            experiment="solicitations",
            type="Solicitation",
            data=data_dict,
            program_id=program_id,
        )
        return SolicitationRecord(record.to_api_dict() if hasattr(record, "to_api_dict") else record.__dict__)

    def update_response(self, record_id: int, data_dict: dict, organization_id: str | None = None) -> ResponseRecord:
        """
        Update an existing response via production API.

        Args:
            record_id: ID of the response record to update
            data_dict: Dictionary containing updated response data
            organization_id: Organization slug (stored in data for tracking)

        Returns:
            Updated ResponseRecord instance
        """
        # Store organization_id in data dict for tracking
        if organization_id:
            data_dict["organization_id"] = organization_id

        record = self.labs_api.update_record(
            record_id=record_id,
            experiment="solicitations",
            type="SolicitationResponse",
            data=data_dict,
        )
        return ResponseRecord(record.to_api_dict() if hasattr(record, "to_api_dict") else record.__dict__)

    def update_review(self, record_id: int, data_dict: dict) -> ReviewRecord:
        """
        Update an existing review via production API.

        Args:
            record_id: ID of the review record to update
            data_dict: Dictionary containing updated review data

        Returns:
            Updated ReviewRecord instance
        """
        record = self.labs_api.update_record(
            record_id=record_id,
            experiment="solicitations",
            type="SolicitationReview",
            data=data_dict,
        )
        return ReviewRecord(record.to_api_dict() if hasattr(record, "to_api_dict") else record.__dict__)

    def get_review_by_user(self, response_record: ResponseRecord, username: str) -> ReviewRecord | None:
        """
        Get a specific user's review of a response.

        Args:
            response_record: Response to find review for
            username: Username who created the review

        Returns:
            ReviewRecord instance or None
        """
        records = self.labs_api.get_records(
            experiment="solicitations",
            type="SolicitationReview",
            labs_record_id=response_record.id,
            username=username,
            model_class=ReviewRecord,
        )

        return records[0] if records else None

    def create_review(self, response_record: ResponseRecord, reviewer_username: str, data_dict: dict) -> ReviewRecord:
        """
        Create a new review via production API.

        Args:
            response_record: Response being reviewed
            reviewer_username: Username of reviewer
            data_dict: Dictionary containing review data

        Returns:
            ReviewRecord instance
        """
        return self.labs_api.create_record(
            experiment="solicitations",
            type="SolicitationReview",
            data=data_dict,
            labs_record_id=response_record.id,
            username=reviewer_username,
            program_id=response_record.program_id,
        )

    def get_responses_for_organization(self, organization_id: str, status: str | None = None) -> list[ResponseRecord]:
        """
        Get all responses submitted by an organization.

        Args:
            organization_id: Organization slug/ID that submitted responses
            status: Optional status filter ('draft', 'submitted')

        Returns:
            List of ResponseRecord instances
        """
        kwargs = {}
        if status:
            kwargs["status"] = status

        # Don't pass organization_id if it's a slug (string), only if it's an actual ID (int)
        # The client is already scoped by program_id or opportunity_id
        org_id_param = {}
        if organization_id and isinstance(organization_id, int):
            org_id_param["organization_id"] = organization_id

        return self.labs_api.get_records(
            experiment="solicitations",
            type="SolicitationResponse",
            model_class=ResponseRecord,
            **org_id_param,
            **kwargs,
        )
