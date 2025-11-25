"""
CommCare HQ API Client.

Provides access to CommCare Case API v2 for fetching case data.
"""

import logging

import httpx
from django.conf import settings
from django.http import HttpRequest

logger = logging.getLogger(__name__)


class CommCareDataAccess:
    """
    Fetch cases from CommCare Case API v2 using session OAuth.

    Uses the CommCare OAuth token stored in request.session["commcare_oauth"].
    """

    def __init__(self, request: HttpRequest, domain: str):
        """
        Initialize CommCare data access.

        Args:
            request: HttpRequest with commcare_oauth in session
            domain: CommCare domain to query
        """
        self.request = request
        self.domain = domain

        # Get CommCare OAuth token from session
        self.commcare_oauth = request.session.get("commcare_oauth", {})
        self.access_token = self.commcare_oauth.get("access_token")
        self.base_url = getattr(settings, "COMMCARE_HQ_URL", "https://www.commcarehq.org")

        if not self.access_token:
            logger.warning("No CommCare OAuth token found in session")

    def check_token_valid(self) -> bool:
        """
        Check if CommCare OAuth token is configured and not expired.

        Returns:
            True if token is valid, False otherwise
        """
        from django.utils import timezone

        if not self.access_token:
            return False

        # Check expiration
        expires_at = self.commcare_oauth.get("expires_at", 0)
        if timezone.now().timestamp() >= expires_at:
            logger.warning(f"CommCare OAuth token expired at {expires_at}")
            return False

        return True

    def fetch_cases(
        self,
        case_type: str,
        limit: int = 1000,
        additional_params: dict | None = None,
    ) -> list[dict]:
        """
        Fetch cases from CommCare Case API v2 with pagination.

        Args:
            case_type: Case type to fetch (e.g., 'deliver-unit')
            limit: Maximum cases per page (default 1000)
            additional_params: Optional additional query parameters

        Returns:
            List of case dictionaries from CommCare API

        Raises:
            ValueError: If OAuth token is not configured or expired
            httpx.HTTPError: If API request fails
        """
        if not self.check_token_valid():
            raise ValueError(
                "CommCare OAuth not configured or expired. "
                "Please authorize CommCare access at /labs/commcare/initiate/"
            )

        endpoint = f"{self.base_url}/a/{self.domain}/api/case/v2/"

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        params = {"case_type": case_type, "limit": limit}
        if additional_params:
            params.update(additional_params)

        all_cases = []
        next_url = endpoint

        logger.info(f"Fetching {case_type} cases from CommCare: {endpoint}")

        # Paginate through results
        page = 0
        while next_url:
            page += 1
            logger.info(f"Fetching page {page} from {next_url}")

            response = httpx.get(
                next_url,
                params=params if next_url == endpoint else None,
                headers=headers,
                timeout=60.0,
            )
            response.raise_for_status()

            data = response.json()
            cases = data.get("cases", [])
            all_cases.extend(cases)

            logger.info(f"Retrieved {len(cases)} cases (total so far: {len(all_cases)})")

            next_url = data.get("next")
            params = None  # Don't send params for next page URLs

        logger.info(f"Fetched total of {len(all_cases)} {case_type} cases from CommCare")
        return all_cases

    def fetch_case_by_id(self, case_id: str) -> dict | None:
        """
        Fetch a single case by ID.

        Args:
            case_id: CommCare case ID

        Returns:
            Case dictionary or None if not found
        """
        if not self.check_token_valid():
            raise ValueError("CommCare OAuth not configured or expired.")

        endpoint = f"{self.base_url}/a/{self.domain}/api/case/v2/{case_id}/"

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        try:
            response = httpx.get(endpoint, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
