"""
Data models for coverage visualization.

These are in-memory proxy classes wrapping API responses (no database storage).
Follows the LocalLabsRecord pattern from labs/models.py.
"""

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd
from shapely import wkt
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry


class LocalUserVisit:
    """Proxy wrapper for UserVisit API data (follows LocalLabsRecord pattern)"""

    def __init__(self, data: dict):
        self._data = data
        self._latitude = None
        self._longitude = None
        self._accuracy = None
        self._parsed_gps = False

    def _parse_gps(self):
        """Lazy parse GPS from form_json.metadata.location"""
        if not self._parsed_gps:
            form_json = self._data.get("form_json", {})
            if isinstance(form_json, str):
                import json

                form_json = json.loads(form_json)

            location_str = form_json.get("metadata", {}).get("location", "")
            parts = location_str.split()

            self._latitude = float(parts[0]) if len(parts) > 0 else 0.0
            self._longitude = float(parts[1]) if len(parts) > 1 else 0.0
            self._accuracy = float(parts[3]) if len(parts) > 3 else None
            self._parsed_gps = True

    @property
    def id(self) -> str:
        return str(self._data.get("xform_id", ""))

    @property
    def user_id(self) -> str:
        return str(self._data.get("user_id", ""))

    @property
    def username(self) -> str:
        return self._data.get("username", "")

    @property
    def deliver_unit_name(self) -> str:
        # Handle both direct field and nested object
        du = self._data.get("deliver_unit")
        if isinstance(du, dict):
            return du.get("name", "")
        return str(du) if du else ""

    @property
    def deliver_unit_id(self) -> str:
        du = self._data.get("deliver_unit")
        if isinstance(du, dict):
            return str(du.get("id", ""))
        return str(self._data.get("deliver_unit_id", ""))

    @property
    def status(self) -> str:
        return self._data.get("status", "")

    @property
    def visit_date(self) -> datetime:
        date_str = self._data.get("visit_date")
        if date_str:
            return pd.to_datetime(date_str)
        return None

    @property
    def flagged(self) -> bool:
        return bool(self._data.get("flagged", False))

    @property
    def latitude(self) -> float:
        self._parse_gps()
        return self._latitude

    @property
    def longitude(self) -> float:
        self._parse_gps()
        return self._longitude

    @property
    def accuracy_in_m(self) -> float | None:
        self._parse_gps()
        return self._accuracy

    @property
    def geometry(self) -> Point:
        return Point(self.longitude, self.latitude)


@dataclass
class DeliveryUnit:
    """DU case from CommCare (NOT Connect's DeliverUnit model)"""

    id: str  # case_id
    du_name: str
    service_area_id: str  # Format: "oa_id-sa_id"
    flw_commcare_id: str
    status: str | None  # completed, visited, None (unvisited)
    wkt: str  # WKT polygon geometry
    buildings: int = 0
    surface_area: float = 0.0
    delivery_count: int = 0
    delivery_target: int = 0
    checked_in_date: str | None = None
    checked_out_date: str | None = None
    last_modified_date: datetime | None = None
    service_points: list[LocalUserVisit] = field(default_factory=list)

    @property
    def geometry(self) -> BaseGeometry:
        """Convert WKT to Shapely geometry"""
        if not self.wkt or self.wkt == "":
            raise ValueError(f"Empty WKT string for delivery unit {self.id}")
        return wkt.loads(self.wkt)

    @property
    def centroid(self) -> tuple:
        """Get centroid as (lat, lon)"""
        geom = self.geometry
        return (geom.centroid.y, geom.centroid.x)

    @classmethod
    def from_commcare_case(cls, case_data: dict):
        """Parse CommCare case API response"""
        properties = case_data.get("properties", {})

        return cls(
            id=case_data.get("case_id"),
            du_name=case_data.get("case_name", ""),
            service_area_id=properties.get("service_area_id", ""),
            flw_commcare_id=case_data.get("owner_id", ""),
            status=properties.get("du_status"),
            wkt=properties.get("WKT", ""),
            buildings=int(properties.get("buildings", 0) or 0),
            surface_area=float(properties.get("surface_area", 0) or 0),
            delivery_count=int(properties.get("delivery_count", 0) or 0),
            delivery_target=int(properties.get("delivery_target", 0) or 0),
            checked_in_date=properties.get("checked_in_date"),
            checked_out_date=properties.get("checked_out_date"),
            last_modified_date=pd.to_datetime(case_data.get("last_modified"))
            if case_data.get("last_modified")
            else None,
        )


@dataclass
class ServiceArea:
    """Collection of DUs grouped by service_area_id"""

    id: str
    delivery_units: list[DeliveryUnit] = field(default_factory=list)

    @property
    def total_buildings(self) -> int:
        return sum(du.buildings for du in self.delivery_units)

    @property
    def total_units(self) -> int:
        return len(self.delivery_units)

    @property
    def completed_units(self) -> int:
        return sum(1 for du in self.delivery_units if du.status == "completed")

    @property
    def completion_percentage(self) -> float:
        if not self.delivery_units:
            return 0.0
        return (self.completed_units / len(self.delivery_units)) * 100


@dataclass
class FLW:
    """Field Level Worker stats"""

    id: str  # CommCare user ID
    name: str
    service_areas: list[str] = field(default_factory=list)
    assigned_units: int = 0
    completed_units: int = 0
    total_visits: int = 0
    dates_active: list[datetime] = field(default_factory=list)
    service_points: list[LocalUserVisit] = field(default_factory=list)
    delivery_units: list[DeliveryUnit] = field(default_factory=list)

    @property
    def completion_rate(self) -> float:
        if self.assigned_units == 0:
            return 0.0
        return (self.completed_units / self.assigned_units) * 100


class CoverageData:
    """Main container - mirrors coverage project structure"""

    def __init__(self):
        self.opportunity_id: int | None = None
        self.opportunity_name: str | None = None
        self.commcare_domain: str | None = None

        self.service_areas: dict[str, ServiceArea] = {}
        self.delivery_units: dict[str, DeliveryUnit] = {}
        self.service_points: list[LocalUserVisit] = []
        self.flws: dict[str, FLW] = {}

        # Cached metadata
        self.total_buildings: int = 0
        self.total_completed_dus: int = 0
        self.total_visited_dus: int = 0
        self.completion_percentage: float = 0.0

    def _compute_metadata(self):
        """Pre-compute stats (mirrors coverage project)"""
        # Link visits to DUs
        for point in self.service_points:
            du_name = point.deliver_unit_name
            if du_name and du_name in self.delivery_units:
                self.delivery_units[du_name].service_points.append(point)

        # Compute aggregates
        self.total_buildings = sum(du.buildings for du in self.delivery_units.values())
        self.total_completed_dus = sum(1 for du in self.delivery_units.values() if du.status == "completed")
        self.total_visited_dus = sum(
            1 for du in self.delivery_units.values() if du.status in ["visited", "in_progress"]
        )

        if self.delivery_units:
            self.completion_percentage = (self.total_completed_dus / len(self.delivery_units)) * 100
