"""
Result container models for analysis framework.

Provides dataclasses for storing analysis results.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class AnalysisResult:
    """
    Base container for analysis results.

    Attributes:
        opportunity_id: Opportunity ID for this analysis
        opportunity_name: Opportunity name
        rows: List of result rows (dicts or dataclass instances)
        metadata: Additional metadata about the analysis
        computed_at: When this analysis was computed
        row_count: Number of rows in results
    """

    opportunity_id: int | None = None
    opportunity_name: str | None = None
    rows: list[dict | Any] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    computed_at: datetime = field(default_factory=datetime.now)

    @property
    def row_count(self) -> int:
        """Number of rows in the result."""
        return len(self.rows)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "opportunity_id": self.opportunity_id,
            "opportunity_name": self.opportunity_name,
            "rows": [row if isinstance(row, dict) else row.__dict__ for row in self.rows],
            "metadata": self.metadata,
            "computed_at": self.computed_at.isoformat(),
            "row_count": self.row_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AnalysisResult":
        """Create from dictionary."""
        return cls(
            opportunity_id=data.get("opportunity_id"),
            opportunity_name=data.get("opportunity_name"),
            rows=data.get("rows", []),
            metadata=data.get("metadata", {}),
            computed_at=datetime.fromisoformat(data["computed_at"]) if "computed_at" in data else datetime.now(),
        )


@dataclass
class FLWRow:
    """
    Analysis row for FLW-level analysis (one row per worker).

    Standard fields included for all FLW analyses:
    - Identification: username, user_id, flw_name
    - Visit counts: total_visits, approved_visits, pending_visits, rejected_visits
    - Date tracking: first_visit_date, last_visit_date, dates_active
    - Custom fields: Any additional fields from FieldComputations

    Custom fields are stored in the custom_fields dict and can be accessed via getattr.
    """

    # Core identification
    username: str
    user_id: int | None = None
    flw_name: str | None = None

    # Visit counts
    total_visits: int = 0
    approved_visits: int = 0
    pending_visits: int = 0
    rejected_visits: int = 0
    flagged_visits: int = 0

    # Date tracking
    first_visit_date: date | None = None
    last_visit_date: date | None = None
    dates_active: list[date] = field(default_factory=list)

    # Custom computed fields from config
    custom_fields: dict[str, Any] = field(default_factory=dict)

    @property
    def days_active(self) -> int:
        """Number of unique days this FLW was active."""
        return len(self.dates_active)

    @property
    def date_range_days(self) -> int | None:
        """Number of days between first and last visit."""
        if not self.first_visit_date or not self.last_visit_date:
            return None
        return (self.last_visit_date - self.first_visit_date).days

    @property
    def approval_rate(self) -> float:
        """Percentage of visits that were approved."""
        if self.total_visits == 0:
            return 0.0
        return (self.approved_visits / self.total_visits) * 100

    def __getattr__(self, name: str) -> Any:
        """Allow accessing custom fields as attributes."""
        if name == "custom_fields":
            # Avoid recursion
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        return self.custom_fields.get(name)

    def __setattr__(self, name: str, value: Any) -> None:
        """Store unknown attributes in custom_fields."""
        # Check if this is a known field
        if name in self.__dataclass_fields__:
            object.__setattr__(self, name, value)
        else:
            # Store in custom_fields
            if not hasattr(self, "custom_fields"):
                object.__setattr__(self, "custom_fields", {})
            self.custom_fields[name] = value

    def to_dict(self) -> dict:
        """Convert to dictionary, merging custom fields."""
        result = {
            "username": self.username,
            "user_id": self.user_id,
            "flw_name": self.flw_name,
            "total_visits": self.total_visits,
            "approved_visits": self.approved_visits,
            "pending_visits": self.pending_visits,
            "rejected_visits": self.rejected_visits,
            "flagged_visits": self.flagged_visits,
            "first_visit_date": self.first_visit_date.isoformat() if self.first_visit_date else None,
            "last_visit_date": self.last_visit_date.isoformat() if self.last_visit_date else None,
            "dates_active": [d.isoformat() for d in self.dates_active],
            "days_active": self.days_active,
            "date_range_days": self.date_range_days,
            "approval_rate": self.approval_rate,
        }
        # Merge custom fields
        result.update(self.custom_fields)
        return result


@dataclass
class FLWAnalysisResult(AnalysisResult):
    """
    Specialized result container for FLW analysis.

    Rows are guaranteed to be FLWRow instances.
    """

    rows: list[FLWRow] = field(default_factory=list)

    def get_flw(self, username: str) -> FLWRow | None:
        """Get FLW row by username."""
        for row in self.rows:
            if row.username == username:
                return row
        return None

    def get_top_performers(self, n: int = 10, metric: str = "total_visits") -> list[FLWRow]:
        """
        Get top N FLWs by metric.

        Args:
            n: Number of top performers to return
            metric: Metric to sort by (default: "total_visits")

        Returns:
            List of top N FLWRow instances
        """
        return sorted(self.rows, key=lambda row: getattr(row, metric, 0), reverse=True)[:n]

    def get_summary_stats(self) -> dict[str, Any]:
        """Get summary statistics across all FLWs."""
        if not self.rows:
            return {}

        total_flws = len(self.rows)
        total_visits = sum(row.total_visits for row in self.rows)
        avg_visits_per_flw = total_visits / total_flws if total_flws > 0 else 0

        return {
            "total_flws": total_flws,
            "total_visits": total_visits,
            "avg_visits_per_flw": round(avg_visits_per_flw, 2),
            "max_visits": max((row.total_visits for row in self.rows), default=0),
            "min_visits": min((row.total_visits for row in self.rows), default=0),
            "total_approved": sum(row.approved_visits for row in self.rows),
            "total_pending": sum(row.pending_visits for row in self.rows),
            "total_rejected": sum(row.rejected_visits for row in self.rows),
        }


@dataclass
class VisitRow:
    """
    Analysis row for visit-level analysis (one row per visit).

    Contains base visit properties plus computed fields from config.
    Unlike FLWRow which aggregates, this preserves individual visit data.
    """

    # Core identification
    id: str
    user_id: int | None = None
    username: str = ""

    # Visit metadata
    visit_date: datetime | None = None
    status: str = ""
    flagged: bool = False

    # GPS coordinates
    latitude: float | None = None
    longitude: float | None = None
    accuracy_in_m: float | None = None

    # Entity/DU info
    deliver_unit_id: int | None = None
    deliver_unit_name: str = ""
    entity_id: str = ""
    entity_name: str = ""

    # Coverage context (can be enriched by subclasses)
    service_area_id: str = ""

    # Computed fields from config
    computed: dict[str, Any] = field(default_factory=dict)

    @property
    def has_gps(self) -> bool:
        """Check if visit has valid GPS coordinates."""
        return self.latitude is not None and self.longitude is not None

    def to_dict(self) -> dict:
        """Convert to dictionary, merging computed fields."""
        result = {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.username,
            "visit_date": self.visit_date.isoformat() if self.visit_date else None,
            "status": self.status,
            "flagged": self.flagged,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "accuracy_in_m": self.accuracy_in_m,
            "deliver_unit_id": self.deliver_unit_id,
            "deliver_unit_name": self.deliver_unit_name,
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "service_area_id": self.service_area_id,
            "has_gps": self.has_gps,
        }
        # Merge computed fields
        result.update(self.computed)
        return result

    def to_geojson_properties(self) -> dict:
        """Convert to GeoJSON properties dict for map visualization."""
        props = {
            "id": self.id,
            "username": self.username,
            "status": self.status,
            "flagged": self.flagged,
            "date": self.visit_date.isoformat() if self.visit_date else "",
            "accuracy": self.accuracy_in_m,
            "du_name": self.deliver_unit_name,
            "du_id": self.deliver_unit_id,
            "service_area_id": self.service_area_id,
        }
        # Add all computed fields
        props.update(self.computed)
        return props


@dataclass
class VisitAnalysisResult(AnalysisResult):
    """
    Specialized result container for visit-level analysis.

    Rows are VisitRow instances (one per visit, not aggregated).
    """

    rows: list[VisitRow] = field(default_factory=list)
    field_metadata: list[dict] = field(default_factory=list)

    def get_visit(self, visit_id: str) -> VisitRow | None:
        """Get visit row by ID."""
        for row in self.rows:
            if row.id == visit_id:
                return row
        return None

    def filter_by_username(self, username: str) -> list[VisitRow]:
        """Get all visits for a specific user."""
        return [row for row in self.rows if row.username == username]

    def filter_by_status(self, status: str) -> list[VisitRow]:
        """Get all visits with a specific status."""
        return [row for row in self.rows if row.status == status]

    def filter_with_gps(self) -> list[VisitRow]:
        """Get all visits that have GPS coordinates."""
        return [row for row in self.rows if row.has_gps]

    def get_summary_stats(self) -> dict[str, Any]:
        """Get summary statistics across all visits."""
        if not self.rows:
            return {}

        total_visits = len(self.rows)
        with_gps = sum(1 for row in self.rows if row.has_gps)
        unique_users = len({row.username for row in self.rows if row.username})

        status_counts = {}
        for row in self.rows:
            status_counts[row.status] = status_counts.get(row.status, 0) + 1

        return {
            "total_visits": total_visits,
            "visits_with_gps": with_gps,
            "gps_percentage": round((with_gps / total_visits) * 100, 1) if total_visits > 0 else 0,
            "unique_users": unique_users,
            "status_counts": status_counts,
            "computed_fields": [f["name"] for f in self.field_metadata],
        }
