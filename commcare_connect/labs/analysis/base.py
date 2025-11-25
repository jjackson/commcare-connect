"""
Base classes for analysis framework.

Provides core data access and computation abstractions.
"""

import logging
from io import StringIO
from typing import Any

import httpx
import pandas as pd
from django.conf import settings
from django.http import HttpRequest

from commcare_connect.labs.analysis.config import AnalysisConfig, FieldComputation
from commcare_connect.labs.analysis.models import AnalysisResult
from commcare_connect.labs.analysis.utils import apply_aggregation, extract_json_path

logger = logging.getLogger(__name__)


class LocalUserVisit:
    """
    Proxy wrapper for UserVisit data from API.

    Provides property-based access to visit fields including form_json.
    Includes lazy-parsed GPS coordinates from form_json.metadata.location.
    """

    def __init__(self, data: dict):
        """
        Initialize from CSV row or dict.

        Args:
            data: Dictionary of visit data from API
        """
        self._data = data
        # GPS fields (lazy parsed)
        self._latitude: float | None = None
        self._longitude: float | None = None
        self._accuracy: float | None = None
        self._gps_parsed: bool = False

    @property
    def id(self) -> str:
        return str(self._data.get("id", ""))

    @property
    def user_id(self) -> int | None:
        user_id = self._data.get("user_id")
        return int(user_id) if user_id else None

    @property
    def username(self) -> str:
        return self._data.get("username", "")

    @property
    def commcare_userid(self) -> str:
        """CommCare user ID from form.meta.userID in form_json."""
        form_json = self.form_json
        return form_json.get("form", {}).get("meta", {}).get("userID", "")

    @property
    def deliver_unit_id(self) -> int | None:
        du_id = self._data.get("deliver_unit_id")
        return int(du_id) if du_id else None

    @property
    def deliver_unit_name(self) -> str:
        return self._data.get("deliver_unit", "")

    @property
    def entity_id(self) -> str:
        return str(self._data.get("entity_id", ""))

    @property
    def entity_name(self) -> str:
        return self._data.get("entity_name", "")

    @property
    def visit_date(self) -> pd.Timestamp | None:
        date_str = self._data.get("visit_date")
        if date_str:
            return pd.to_datetime(date_str)
        return None

    @property
    def status(self) -> str:
        return self._data.get("status", "")

    @property
    def flagged(self) -> bool:
        return bool(self._data.get("flagged", False))

    def _parse_gps(self) -> None:
        """
        Lazy parse GPS coordinates from form_json.metadata.location.

        Location format: "latitude longitude altitude accuracy"
        Example: "12.9716 77.5946 0.0 10.0"
        """
        if self._gps_parsed:
            return

        self._gps_parsed = True

        try:
            form_json = self.form_json
            location_str = form_json.get("metadata", {}).get("location", "")

            if location_str:
                parts = location_str.split()
                self._latitude = float(parts[0]) if len(parts) > 0 else None
                self._longitude = float(parts[1]) if len(parts) > 1 else None
                self._accuracy = float(parts[3]) if len(parts) > 3 else None
        except (ValueError, TypeError, AttributeError) as e:
            logger.debug(f"Failed to parse GPS for visit {self.id}: {e}")

    @property
    def latitude(self) -> float | None:
        """Latitude from form_json.metadata.location (lazy parsed)."""
        self._parse_gps()
        return self._latitude

    @property
    def longitude(self) -> float | None:
        """Longitude from form_json.metadata.location (lazy parsed)."""
        self._parse_gps()
        return self._longitude

    @property
    def accuracy_in_m(self) -> float | None:
        """GPS accuracy in meters from form_json.metadata.location (lazy parsed)."""
        self._parse_gps()
        return self._accuracy

    @property
    def has_gps(self) -> bool:
        """Check if visit has valid GPS coordinates."""
        self._parse_gps()
        return self._latitude is not None and self._longitude is not None

    @property
    def form_json(self) -> dict:
        """
        Get parsed form_json.

        Handles both dict (already parsed) and string (needs parsing).
        NOTE: API may return Python repr format (single quotes) instead of JSON.
        """
        form_json = self._data.get("form_json", {})
        if isinstance(form_json, str):
            import ast
            import json

            # First try json.loads for valid JSON
            try:
                form_json = json.loads(form_json)
            except json.JSONDecodeError:
                # Fall back to ast.literal_eval for Python dict repr format
                try:
                    form_json = ast.literal_eval(form_json)
                except (ValueError, SyntaxError):
                    logger.warning(f"Failed to parse form_json for visit {self.id}")
                    form_json = {}
        return form_json

    def extract_field(self, path: str) -> Any:
        """
        Extract field from form_json using dot notation path.

        Args:
            path: Dot-separated path (e.g., "form.building_count")

        Returns:
            Extracted value or None
        """
        return extract_json_path(self.form_json, path)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.username,
            "deliver_unit_id": self.deliver_unit_id,
            "deliver_unit_name": self.deliver_unit_name,
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "visit_date": self.visit_date.isoformat() if self.visit_date else None,
            "status": self.status,
            "flagged": self.flagged,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "accuracy_in_m": self.accuracy_in_m,
            "form_json": self.form_json,
        }


class AnalysisDataAccess:
    """
    Fetches UserVisit data from Connect API.

    Handles pagination, parsing, and returns list of LocalUserVisit proxies.
    """

    def __init__(self, request: HttpRequest):
        """
        Initialize data access with request context.

        Args:
            request: HttpRequest with labs_oauth and labs_context in session
        """
        self.request = request
        self.access_token = request.session.get("labs_oauth", {}).get("access_token")
        self.labs_context = getattr(request, "labs_context", {})
        self.opportunity_id = self.labs_context.get("opportunity_id")

        if not self.access_token:
            raise ValueError("No labs OAuth token found in session")

        if not self.opportunity_id:
            raise ValueError("No opportunity selected in labs context")

    def fetch_user_visits(self) -> list[LocalUserVisit]:
        """
        Fetch all UserVisits for the opportunity from Connect API.

        Returns:
            List of LocalUserVisit proxies

        Raises:
            httpx.HTTPStatusError: If API request fails
        """
        url = f"{settings.CONNECT_PRODUCTION_URL}/export/opportunity/{self.opportunity_id}/user_visits/"

        logger.info(f"Fetching user visits from {url}")

        try:
            response = httpx.get(url, headers={"Authorization": f"Bearer {self.access_token}"}, timeout=120.0)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to fetch user visits: {e}")
            raise

        # Parse CSV response
        df = pd.read_csv(StringIO(response.text))

        logger.info(f"Fetched {len(df)} user visits from Connect")

        # Parse form_json if it's a string
        # NOTE: The API returns form_json as Python repr format (single quotes, Python literals)
        # not valid JSON (double quotes, null/true/false). We use ast.literal_eval() to parse it.
        if "form_json" in df.columns and len(df) > 0:
            import ast
            import json

            def parse_json(x):
                if isinstance(x, str) and x:
                    # First try json.loads for valid JSON
                    try:
                        return json.loads(x)
                    except json.JSONDecodeError:
                        pass
                    # Fall back to ast.literal_eval for Python dict repr format
                    try:
                        return ast.literal_eval(x)
                    except (ValueError, SyntaxError):
                        logger.warning(f"Failed to parse form_json: {x[:100]}...")
                        return {}
                return x if isinstance(x, dict) else {}

            df["form_json"] = df["form_json"].apply(parse_json)

        # Convert to LocalUserVisit proxies
        visits = [LocalUserVisit(row.to_dict()) for _, row in df.iterrows()]

        logger.info(f"Created {len(visits)} LocalUserVisit proxies")

        return visits

    def fetch_visit_count(self) -> int:
        """
        Get visit count for cache validation.

        Uses the visit_count from labs_context (already loaded from opp_org_program API)
        which is much faster than downloading the full visits CSV.

        Returns:
            Total visit count for the opportunity
        """
        # Try to get from labs_context first (fastest - already in memory)
        opportunity = self.labs_context.get("opportunity", {})
        if opportunity and "visit_count" in opportunity:
            count = opportunity.get("visit_count", 0)
            logger.info(f"Visit count from labs_context for opportunity {self.opportunity_id}: {count}")
            return count

        # Fallback: fetch from single opportunity endpoint (much lighter than full CSV)
        url = f"{settings.CONNECT_PRODUCTION_URL}/export/opportunity/{self.opportunity_id}/"

        logger.info(f"Fetching visit count from {url}")

        try:
            response = httpx.get(url, headers={"Authorization": f"Bearer {self.access_token}"}, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            count = data.get("visit_count", 0)
            logger.info(f"Visit count for opportunity {self.opportunity_id}: {count}")
            return count
        except Exception as e:
            logger.warning(f"Failed to fetch visit count from API: {e}")
            # Return 0 to force cache miss (safer than using stale cache)
            return 0


class Analyzer:
    """
    Base class for analyzing UserVisit data.

    Subclasses implement specific analysis patterns (FLW, visit, entity, time-series, etc.).
    """

    def __init__(self, request: HttpRequest, config: AnalysisConfig):
        """
        Initialize analyzer with request and config.

        Args:
            request: HttpRequest with labs context
            config: AnalysisConfig defining computations
        """
        self.request = request
        self.config = config
        self.data_access = AnalysisDataAccess(request)

    def fetch_visits(self) -> list[LocalUserVisit]:
        """Fetch user visits from API."""
        return self.data_access.fetch_user_visits()

    def filter_visits(self, visits: list[LocalUserVisit]) -> list[LocalUserVisit]:
        """
        Apply filters from config to visits.

        Args:
            visits: List of visits to filter

        Returns:
            Filtered list of visits
        """
        filtered = visits

        # Apply status filter
        if "status" in self.config.filters:
            statuses = self.config.filters["status"]
            if not isinstance(statuses, list):
                statuses = [statuses]
            filtered = [v for v in filtered if v.status in statuses]

        # Apply date range filter
        if "date_from" in self.config.filters:
            date_from = pd.to_datetime(self.config.filters["date_from"])
            filtered = [v for v in filtered if v.visit_date and v.visit_date >= date_from]

        if "date_to" in self.config.filters:
            date_to = pd.to_datetime(self.config.filters["date_to"])
            filtered = [v for v in filtered if v.visit_date and v.visit_date <= date_to]

        # Apply flagged filter
        if "flagged" in self.config.filters:
            flagged = self.config.filters["flagged"]
            filtered = [v for v in filtered if v.flagged == flagged]

        logger.info(f"Filtered {len(visits)} visits to {len(filtered)} visits")

        return filtered

    def group_visits(self, visits: list[LocalUserVisit]) -> dict[Any, list[LocalUserVisit]]:
        """
        Group visits by the configured grouping key.

        Args:
            visits: List of visits to group

        Returns:
            Dictionary mapping grouping key values to lists of visits
        """
        groups = {}

        for visit in visits:
            # Get grouping key value from visit
            key_value = getattr(visit, self.config.grouping_key, None)

            if key_value is None:
                logger.warning(f"Visit {visit.id} has no value for grouping key {self.config.grouping_key}")
                continue

            if key_value not in groups:
                groups[key_value] = []

            groups[key_value].append(visit)

        logger.info(f"Grouped {len(visits)} visits into {len(groups)} groups by {self.config.grouping_key}")

        return groups

    def compute_field(self, field_comp: FieldComputation, visits: list[LocalUserVisit]) -> Any:
        """
        Compute a single field from a list of visits.

        Args:
            field_comp: Field computation configuration
            visits: List of visits for this group

        Returns:
            Computed value
        """
        # Extract values from all visits
        values = []

        for visit in visits:
            value = extract_json_path(visit.form_json, field_comp.path)

            # Apply transform if provided
            if value is not None and field_comp.transform:
                try:
                    value = field_comp.transform(value)
                except Exception as e:
                    logger.warning(f"Transform failed for {field_comp.name}: {e}")
                    value = None

            values.append(value)

        # Apply aggregation
        try:
            result = apply_aggregation(field_comp.aggregation, values)
        except Exception as e:
            logger.warning(f"Aggregation failed for {field_comp.name}: {e}")
            result = field_comp.default

        # Use default if result is None
        if result is None and field_comp.default is not None:
            result = field_comp.default

        return result

    def compute(self) -> AnalysisResult:
        """
        Compute analysis results.

        This is the main entry point. Subclasses should override to provide
        specific analysis logic.

        Returns:
            AnalysisResult with computed rows
        """
        raise NotImplementedError("Subclasses must implement compute()")


def get_flw_names_for_opportunity(request: HttpRequest) -> dict[str, str]:
    """
    Get FLW display names for the opportunity in request context.

    Fetches username to display name mapping from Connect API and caches it.
    Uses the same caching backend as analysis results (Redis if available, file-based fallback).

    Args:
        request: HttpRequest with labs_oauth and labs_context in session

    Returns:
        Dictionary mapping username to display name
        Example: {"e5e685ae3f024fb6848d0d87138d526f": "John Doe"}

    Raises:
        ValueError: If no OAuth token or opportunity context found
    """
    from commcare_connect.labs.analysis.file_cache import _use_django_cache

    access_token = request.session.get("labs_oauth", {}).get("access_token")
    labs_context = getattr(request, "labs_context", {})
    opportunity_id = labs_context.get("opportunity_id")

    if not access_token:
        raise ValueError("No labs OAuth token found in session")

    if not opportunity_id:
        raise ValueError("No opportunity selected in labs context")

    # Try cache first
    cache_key = f"flw_names_{opportunity_id}"
    use_django = _use_django_cache()

    if use_django:
        from django.core.cache import cache

        try:
            cached = cache.get(cache_key)
            if cached is not None:
                logger.debug(f"FLW names loaded from Django cache for opp {opportunity_id}")
                return cached
        except Exception as e:
            logger.warning(f"Django cache get failed for {cache_key}: {e}")
    else:
        # File-based cache
        from commcare_connect.labs.analysis.file_cache import CACHE_DIR

        cache_file = CACHE_DIR / f"flw_names_{opportunity_id}.pkl"
        if cache_file.exists():
            try:
                import pickle

                with open(cache_file, "rb") as f:
                    cached = pickle.load(f)
                logger.debug(f"FLW names loaded from file cache for opp {opportunity_id}")
                return cached
            except Exception as e:
                logger.warning(f"File cache read failed for {cache_key}: {e}")

    # Fetch from API
    url = f"{settings.CONNECT_PRODUCTION_URL}/export/opportunity/{opportunity_id}/user_data/"
    logger.info(f"Fetching FLW names from {url}")

    try:
        response = httpx.get(url, headers={"Authorization": f"Bearer {access_token}"}, timeout=30.0)
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.error(f"Failed to fetch FLW names: {e}")
        raise

    # Parse CSV response
    df = pd.read_csv(StringIO(response.text))
    logger.info(f"Fetched {len(df)} FLWs from Connect")

    # Build mapping: username -> name (fallback to username if name is empty)
    flw_names = {}
    for _, row in df.iterrows():
        username = row.get("username")
        name = row.get("name")
        if username:
            flw_names[username] = name if name else username

    # Cache the result (1 hour TTL)
    if use_django:
        from django.core.cache import cache

        try:
            cache.set(cache_key, flw_names, 3600)
            logger.debug(f"FLW names cached in Django cache for opp {opportunity_id}")
        except Exception as e:
            logger.warning(f"Django cache set failed for {cache_key}: {e}")
    else:
        # File-based cache
        from commcare_connect.labs.analysis.file_cache import CACHE_DIR

        try:
            CACHE_DIR.mkdir(exist_ok=True)
            cache_file = CACHE_DIR / f"flw_names_{opportunity_id}.pkl"
            import pickle

            with open(cache_file, "wb") as f:
                pickle.dump(flw_names, f)
            logger.debug(f"FLW names cached in file cache for opp {opportunity_id}")
        except Exception as e:
            logger.warning(f"File cache write failed for {cache_key}: {e}")

    return flw_names
