"""
Configuration classes for declarative analysis setup.

Supports complex JSON path extraction like:
    form_json -> 'form' -> 'additional_case_info' ->> 'childs_age_in_month'

Becomes:
    FieldComputation(
        name="child_age_months",
        path="form.additional_case_info.childs_age_in_month",
        aggregation="first"  # or "avg", "sum", etc.
    )
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

AggregationType = Literal["sum", "avg", "count", "min", "max", "list", "first", "last", "count_unique"]

# ASCII characters for sparkline rendering (avoid unicode for Windows compatibility)
SPARKLINE_CHARS = " _.-=oO#"  # 8 levels from empty to full


@dataclass
class FieldComputation:
    """
    Configuration for extracting and aggregating a field from UserVisit form_json.

    Examples:
        # Simple sum of numeric field
        FieldComputation(
            name="buildings_visited",
            path="form.building_count",
            aggregation="sum",
            default=0
        )

        # Extract nested field and take first value
        FieldComputation(
            name="child_age_months",
            path="form.additional_case_info.childs_age_in_month",
            aggregation="first"
        )

        # Complex transformation
        FieldComputation(
            name="avg_accuracy",
            path="metadata.location",
            aggregation="avg",
            transform=lambda loc: float(loc.split()[3]) if loc and len(loc.split()) > 3 else None
        )

        # Count non-null values
        FieldComputation(
            name="consent_count",
            path="form.case.update.MUAC_consent",
            aggregation="count"
        )
    """

    name: str
    path: str
    aggregation: AggregationType
    default: Any = None
    transform: Callable[[Any], Any] | None = None
    description: str = ""

    def __post_init__(self):
        """Validate configuration."""
        if not self.name:
            raise ValueError("Field name is required")
        if not self.path:
            raise ValueError("Field path is required")
        if self.aggregation not in [
            "sum",
            "avg",
            "count",
            "min",
            "max",
            "list",
            "first",
            "last",
            "count_unique",
        ]:
            raise ValueError(f"Invalid aggregation type: {self.aggregation}")


@dataclass
class HistogramComputation:
    """
    Configuration for creating a histogram/sparkline from numeric values.

    Bins values from a numeric field and produces:
    - Individual bin counts as separate fields (e.g., muac_9_5_10_5_visits)
    - A sparkline string showing the distribution
    - Summary statistics (mean, std, etc.)

    Example:
        HistogramComputation(
            name="muac_distribution",
            path="form.case.update.soliciter_muac_cm",
            lower_bound=9.5,
            upper_bound=21.5,
            num_bins=12,
            bin_name_prefix="muac",
        )

        Produces fields like:
        - muac_distribution_chart: "_.--==##=-.._" (sparkline)
        - muac_9_5_10_5_visits: 5
        - muac_10_5_11_5_visits: 12
        - ... etc for each bin
    """

    name: str
    path: str
    lower_bound: float
    upper_bound: float
    num_bins: int
    bin_name_prefix: str = ""
    transform: Callable[[Any], Any] | None = None
    description: str = ""
    include_out_of_range: bool = True  # Count values outside bounds in first/last bin

    def __post_init__(self):
        """Validate configuration."""
        if not self.name:
            raise ValueError("Histogram name is required")
        if not self.path:
            raise ValueError("Field path is required")
        if self.lower_bound >= self.upper_bound:
            raise ValueError("lower_bound must be less than upper_bound")
        if self.num_bins < 1:
            raise ValueError("num_bins must be at least 1")

    @property
    def bin_width(self) -> float:
        """Calculate the width of each bin."""
        return (self.upper_bound - self.lower_bound) / self.num_bins

    def get_bin_edges(self) -> list[float]:
        """Get the edges of all bins."""
        width = self.bin_width
        return [self.lower_bound + i * width for i in range(self.num_bins + 1)]

    def get_bin_names(self) -> list[str]:
        """Generate field names for each bin."""
        edges = self.get_bin_edges()
        prefix = self.bin_name_prefix or self.name
        names = []
        for i in range(self.num_bins):
            low = edges[i]
            high = edges[i + 1]
            # Format as prefix_X_Y_visits (replacing . with _)
            low_str = str(low).replace(".", "_")
            high_str = str(high).replace(".", "_")
            names.append(f"{prefix}_{low_str}_{high_str}_visits")
        return names

    def value_to_bin_index(self, value: float) -> int | None:
        """
        Get the bin index for a value.

        Returns None if value is out of range and include_out_of_range is False.
        """
        if value < self.lower_bound:
            return 0 if self.include_out_of_range else None
        if value >= self.upper_bound:
            return self.num_bins - 1 if self.include_out_of_range else None

        # Calculate bin index
        index = int((value - self.lower_bound) / self.bin_width)
        # Handle edge case where value == upper_bound exactly
        return min(index, self.num_bins - 1)


@dataclass
class AnalysisConfig:
    """
    Configuration for an analysis computation.

    Defines what fields to extract, how to aggregate them, and how to group visits.

    Attributes:
        grouping_key: Field to group by (e.g., "username", "user_id", "deliver_unit_id")
        fields: List of FieldComputations to apply
        histograms: List of HistogramComputations to apply
        filters: Optional dict of filters to apply to visits
        date_field: Field name for date filtering (default: "visit_date")

    Example:
        config = AnalysisConfig(
            grouping_key="username",
            fields=[
                FieldComputation(
                    name="total_muac_measurements",
                    path="form.case.update.soliciter_muac_cm",
                    aggregation="count"
                ),
                FieldComputation(
                    name="avg_child_age",
                    path="form.additional_case_info.childs_age_in_month",
                    aggregation="avg",
                    transform=lambda x: int(x) if x else None
                ),
            ],
            histograms=[
                HistogramComputation(
                    name="muac_distribution",
                    path="form.case.update.soliciter_muac_cm",
                    lower_bound=9.5,
                    upper_bound=21.5,
                    num_bins=12,
                    bin_name_prefix="muac",
                )
            ],
            filters={"status": ["approved"]}
        )
    """

    grouping_key: str
    fields: list[FieldComputation] = field(default_factory=list)
    histograms: list[HistogramComputation] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    date_field: str = "visit_date"

    def __post_init__(self):
        """Validate configuration."""
        if not self.grouping_key:
            raise ValueError("Grouping key is required")
        # Note: Empty fields/histograms is valid for basic caching scenarios

    def add_field(self, field_comp: FieldComputation) -> None:
        """Add a field computation to the config."""
        self.fields.append(field_comp)

    def add_histogram(self, hist_comp: HistogramComputation) -> None:
        """Add a histogram computation to the config."""
        self.histograms.append(hist_comp)

    def get_field(self, name: str) -> FieldComputation | None:
        """Get a field computation by name."""
        for field_comp in self.fields:
            if field_comp.name == name:
                return field_comp
        return None

    def get_histogram(self, name: str) -> HistogramComputation | None:
        """Get a histogram computation by name."""
        for hist_comp in self.histograms:
            if hist_comp.name == name:
                return hist_comp
        return None
