"""
Field and histogram computations for analysis framework.

Provides functions to extract values from form_json and compute aggregations.
"""

import logging
from typing import Any

import pandas as pd

from commcare_connect.labs.analysis.base import LocalUserVisit
from commcare_connect.labs.analysis.config import SPARKLINE_CHARS, FieldComputation, HistogramComputation
from commcare_connect.labs.analysis.utils import extract_json_path, extract_json_path_multi

logger = logging.getLogger(__name__)


def _extract_field_value(form_json: dict, field_comp: FieldComputation) -> Any:
    """Extract value from form_json using field computation paths.

    Note: This does NOT handle custom extractors - those need the full visit dict.
    Use _extract_field_value_from_visit for fields that may have extractors.
    """
    paths = field_comp.get_paths()
    if len(paths) > 1:
        return extract_json_path_multi(form_json, paths)
    elif paths:
        return extract_json_path(form_json, paths[0])
    return None


def _extract_field_value_from_visit(visit: LocalUserVisit, field_comp: FieldComputation) -> Any:
    """
    Extract value from visit using field computation.

    Handles both path-based extraction and custom extractors.

    Args:
        visit: LocalUserVisit object (has form_json, images, etc.)
        field_comp: Field computation configuration

    Returns:
        Extracted value (before transform)
    """
    # Custom extractor takes precedence - receives full visit data dict
    if field_comp.uses_extractor and field_comp.extractor:
        return field_comp.extractor(visit._data)

    # Path-based extraction from form_json
    return _extract_field_value(visit.form_json, field_comp)


def _extract_histogram_value(form_json: dict, hist_comp) -> Any:
    """Extract value from form_json using histogram computation paths."""
    paths = hist_comp.get_paths()
    if len(paths) > 1:
        return extract_json_path_multi(form_json, paths)
    elif paths:
        return extract_json_path(form_json, paths[0])
    return None


def compute_fields_batch(visits: list[LocalUserVisit], field_comps: list[FieldComputation]) -> dict[str, Any]:
    """
    Compute all fields for a list of visits at once using pandas.

    This is much faster than looping through each field and each visit separately.
    Supports both path-based extraction and custom extractors.

    Args:
        visits: List of visits for one FLW
        field_comps: List of field computations to apply

    Returns:
        Dictionary of field_name -> computed_value
    """
    results = {}

    # Process each field computation
    for field_comp in field_comps:
        try:
            # Extract values - use appropriate method based on field type
            if field_comp.uses_extractor:
                # Custom extractor needs full visit data
                values = [_extract_field_value_from_visit(v, field_comp) for v in visits]
            else:
                # Path-based extraction from form_json
                form_jsons = [v.form_json for v in visits]
                values = [_extract_field_value(fj, field_comp) for fj in form_jsons]

                # Apply transform if provided (extractors do their own transformation)
                if field_comp.transform:
                    transformed = []
                    for v in values:
                        try:
                            transformed.append(field_comp.transform(v) if v is not None else None)
                        except Exception:
                            transformed.append(None)
                    values = transformed

            # Filter out None values for aggregation
            non_none_values = [v for v in values if v is not None]

            # Compute aggregation using pandas for better performance
            if not non_none_values:
                result = field_comp.default
            elif field_comp.aggregation == "count":
                result = len(non_none_values)
            elif field_comp.aggregation == "count_unique":
                # Handle unhashable types (like lists/dicts)
                try:
                    result = len(set(non_none_values))
                except TypeError:
                    result = len(non_none_values)
            elif field_comp.aggregation == "first":
                result = non_none_values[0]
            elif field_comp.aggregation == "last":
                result = non_none_values[-1]
            elif field_comp.aggregation == "list":
                # For list aggregation, just return the list (may contain complex objects)
                result = non_none_values
            elif field_comp.aggregation in ["sum", "avg", "min", "max"]:
                # Use pandas Series for numeric aggregations
                try:
                    series = pd.Series(non_none_values, dtype=float)
                    if field_comp.aggregation == "sum":
                        result = float(series.sum())
                    elif field_comp.aggregation == "avg":
                        result = float(series.mean())
                    elif field_comp.aggregation == "min":
                        result = float(series.min())
                    elif field_comp.aggregation == "max":
                        result = float(series.max())
                except (ValueError, TypeError):
                    result = field_comp.default
            else:
                result = field_comp.default

            # Use default if result is None or NaN
            if result is None or (isinstance(result, float) and pd.isna(result)):
                result = field_comp.default

            results[field_comp.name] = result

        except Exception as e:
            logger.warning(f"Failed to compute field {field_comp.name}: {e}")
            results[field_comp.name] = field_comp.default

    return results


def compute_visit_fields(
    visits: list[LocalUserVisit],
    field_comps: list[FieldComputation],
    hist_comps: list[HistogramComputation] | None = None,
) -> list[dict[str, Any]]:
    """
    Compute field values for each visit individually (no aggregation).

    Unlike compute_fields_batch which aggregates values across visits,
    this returns one result dict per visit with the extracted/transformed values.

    Supports both path-based extraction and custom extractors.
    Custom extractors receive the full visit data dict, enabling complex
    extractions like combining images array with form_json data.

    Also extracts histogram raw values (prefixed with _hist_) so they can be
    aggregated into histogram bins at the FLW level.

    Args:
        visits: List of visits to process
        field_comps: List of field computations (aggregation is ignored for visit-level)
        hist_comps: Optional list of histogram computations to extract values for

    Returns:
        List of dicts, one per visit: [{visit_id, field1, field2, ..., _hist_name, ...}, ...]
    """
    results = []

    for visit in visits:
        visit_result = {"visit_id": visit.id}
        form_json = visit.form_json

        for field_comp in field_comps:
            try:
                # Extract value - handles both path-based and custom extractors
                value = _extract_field_value_from_visit(visit, field_comp)

                # Apply transform if provided (for path-based extraction)
                # Note: extractors typically do their own transformation
                if value is not None and field_comp.transform and not field_comp.uses_extractor:
                    try:
                        value = field_comp.transform(value)
                    except Exception:
                        value = None

                # Use default if None
                if value is None:
                    value = field_comp.default

                visit_result[field_comp.name] = value

            except Exception as e:
                logger.warning(f"Failed to compute field {field_comp.name} for visit {visit.id}: {e}")
                visit_result[field_comp.name] = field_comp.default

        # Extract histogram raw values (for later aggregation)
        if hist_comps:
            for hist_comp in hist_comps:
                try:
                    value = _extract_histogram_value(form_json, hist_comp)

                    # Apply transform if provided
                    if value is not None and hist_comp.transform:
                        try:
                            value = hist_comp.transform(value)
                        except Exception:
                            value = None

                    # Convert to float if possible
                    if value is not None:
                        try:
                            value = float(value)
                        except (ValueError, TypeError):
                            value = None

                    # Store with _hist_ prefix to indicate it's a histogram raw value
                    visit_result[f"_hist_{hist_comp.name}"] = value

                except Exception as e:
                    logger.warning(f"Failed to extract histogram value {hist_comp.name} for visit {visit.id}: {e}")
                    visit_result[f"_hist_{hist_comp.name}"] = None

        results.append(visit_result)

    return results


def compute_histogram(visits: list[LocalUserVisit], hist_comp: HistogramComputation) -> dict[str, Any]:
    """
    Compute histogram bins and sparkline for a numeric field.

    Args:
        visits: List of visits for one FLW
        hist_comp: Histogram computation configuration

    Returns:
        Dictionary with:
        - {name}_chart: sparkline string
        - {name}_mean: mean value
        - {name}_count: total valid values
        - Individual bin counts: {prefix}_{low}_{high}_visits
    """
    results = {}

    # Extract all form_json at once
    form_jsons = [v.form_json for v in visits]

    try:
        # Extract all values for this path (supports multi-path fallback)
        values = [_extract_histogram_value(fj, hist_comp) for fj in form_jsons]

        # Apply transform if provided
        if hist_comp.transform:
            transformed = []
            for v in values:
                try:
                    transformed.append(hist_comp.transform(v) if v is not None else None)
                except Exception:
                    transformed.append(None)
            values = transformed

        # Convert to numeric, filtering out None and invalid values
        numeric_values = []
        for v in values:
            if v is not None:
                try:
                    numeric_values.append(float(v))
                except (ValueError, TypeError):
                    pass

        # Initialize bin counts
        bin_names = hist_comp.get_bin_names()
        bin_counts = [0] * hist_comp.num_bins

        # Count values in each bin
        for val in numeric_values:
            bin_idx = hist_comp.value_to_bin_index(val)
            if bin_idx is not None:
                bin_counts[bin_idx] += 1

        # Store individual bin counts
        for i, bin_name in enumerate(bin_names):
            results[bin_name] = bin_counts[i]

        # Generate sparkline
        sparkline = generate_sparkline(bin_counts)
        results[f"{hist_comp.name}_chart"] = sparkline

        # Summary statistics
        if numeric_values:
            series = pd.Series(numeric_values)
            results[f"{hist_comp.name}_mean"] = round(float(series.mean()), 2)
            results[f"{hist_comp.name}_count"] = len(numeric_values)
        else:
            results[f"{hist_comp.name}_mean"] = None
            results[f"{hist_comp.name}_count"] = 0

    except Exception as e:
        logger.warning(f"Failed to compute histogram {hist_comp.name}: {e}")
        # Still populate bin names with zeros
        for bin_name in hist_comp.get_bin_names():
            results[bin_name] = 0
        results[f"{hist_comp.name}_chart"] = ""
        results[f"{hist_comp.name}_mean"] = None
        results[f"{hist_comp.name}_count"] = 0

    return results


def generate_sparkline(counts: list[int]) -> str:
    """
    Generate an ASCII sparkline string from bin counts.

    Uses characters: " _.-=oO#" for 8 levels of height.

    Args:
        counts: List of bin counts

    Returns:
        Sparkline string with one character per bin
    """
    if not counts or max(counts) == 0:
        return "_" * len(counts)

    max_count = max(counts)
    num_levels = len(SPARKLINE_CHARS) - 1  # Exclude space for zero

    sparkline = []
    for count in counts:
        if count == 0:
            sparkline.append("_")
        else:
            # Scale to 1-7 range (using indices 1-7 of SPARKLINE_CHARS)
            level = int((count / max_count) * num_levels)
            level = max(1, min(level, num_levels))  # Clamp to 1-7
            sparkline.append(SPARKLINE_CHARS[level])

    return "".join(sparkline)


def compute_histograms_batch(visits: list[LocalUserVisit], hist_comps: list[HistogramComputation]) -> dict[str, Any]:
    """
    Compute all histograms for a list of visits.

    Args:
        visits: List of visits for one FLW
        hist_comps: List of histogram computations to apply

    Returns:
        Dictionary of all histogram fields
    """
    results = {}
    for hist_comp in hist_comps:
        hist_results = compute_histogram(visits, hist_comp)
        results.update(hist_results)
    return results


def aggregate_histogram_from_values(values: list[float | None], hist_comp: HistogramComputation) -> dict[str, Any]:
    """
    Aggregate pre-extracted histogram values into bins.

    Used when aggregating VisitRows that have pre-computed histogram values
    stored in their `computed` dict with the _hist_ prefix.

    Args:
        values: List of numeric values (may include None)
        hist_comp: Histogram configuration

    Returns:
        Dictionary with bin counts, sparkline, mean, and count
    """
    results = {}

    # Filter out None values
    numeric_values = [v for v in values if v is not None]

    # Initialize bin counts
    bin_names = hist_comp.get_bin_names()
    bin_counts = [0] * hist_comp.num_bins

    # Count values in each bin
    for val in numeric_values:
        bin_idx = hist_comp.value_to_bin_index(val)
        if bin_idx is not None:
            bin_counts[bin_idx] += 1

    # Store individual bin counts
    for i, bin_name in enumerate(bin_names):
        results[bin_name] = bin_counts[i]

    # Generate sparkline
    sparkline = generate_sparkline(bin_counts)
    results[f"{hist_comp.name}_chart"] = sparkline

    # Summary statistics
    if numeric_values:
        series = pd.Series(numeric_values)
        results[f"{hist_comp.name}_mean"] = round(float(series.mean()), 2)
        results[f"{hist_comp.name}_count"] = len(numeric_values)
    else:
        results[f"{hist_comp.name}_mean"] = None
        results[f"{hist_comp.name}_count"] = 0

    return results
