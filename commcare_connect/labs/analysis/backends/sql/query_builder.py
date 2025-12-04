"""
SQL query builder for translating AnalysisPipelineConfig to SQL.

Translates field computations to PostgreSQL queries that:
1. Extract values from JSONB form_json
2. Apply transforms using SQL CASE statements
3. Aggregate using GROUP BY
4. Compute histograms
"""

import logging

from django.db import connection

from commcare_connect.labs.analysis.config import AnalysisPipelineConfig, FieldComputation, HistogramComputation

logger = logging.getLogger(__name__)


def _jsonb_path_to_sql(path: str, column: str = "form_json") -> str:
    """
    Convert a dot-notation path to PostgreSQL JSONB extraction.

    Example: "form.case.update.muac_cm" -> "form_json->'form'->'case'->'update'->>'muac_cm"
    """
    parts = path.split(".")
    if not parts:
        return "NULL"

    sql_parts = [column]
    for i, part in enumerate(parts):
        if i == len(parts) - 1:
            sql_parts.append(f"->>'{part}'")
        else:
            sql_parts.append(f"->'{part}'")

    return "".join(sql_parts)


def _paths_to_coalesce_sql(paths: list[str], column: str = "form_json") -> str:
    """Convert multiple paths to a COALESCE expression."""
    if not paths:
        return "NULL"

    sql_paths = [_jsonb_path_to_sql(p, column) for p in paths]
    return f"COALESCE({', '.join(sql_paths)})"


def _get_transform_pattern(field: FieldComputation | HistogramComputation) -> str | None:
    """Identify the transform pattern from the field."""
    if field.transform is None:
        return None

    import inspect

    try:
        source = inspect.getsource(field.transform)
    except (OSError, TypeError):
        source = ""

    name = field.name.lower()

    if "yes" in source and "true" in source:
        return "yes_no_to_1"

    if "_is_valid_muac" in source:
        # Check specific patterns FIRST before generic ones
        # Order matters: check SAM/MAM before generic float conversion
        # Note: MAM uses "11.5 <=" not ">= 11.5" (Python chained comparison)
        if "< 11.5" in source and "11.5 <=" not in source:
            return "muac_sam"
        elif ("11.5 <=" in source or ">= 11.5" in source) and "< 12.5" in source:
            return "muac_mam"
        elif "float(x)" in source:
            return "is_valid_muac_to_float"
        else:
            return "is_valid_muac_to_1"

    if "male" in source.lower():
        if "female" in name or "'female'" in source.lower():
            return "gender_female"
        else:
            return "gender_male"

    if "strip()" in source or "and str(x)" in source:
        return "non_empty_to_1"

    return None


def _transform_to_sql(field: FieldComputation | HistogramComputation, value_expr: str) -> str:
    """Convert a field's transform to SQL CASE statement."""
    if field.transform is None:
        return value_expr

    transform_src = _get_transform_pattern(field)

    if transform_src == "yes_no_to_1":
        return f"""CASE WHEN LOWER({value_expr}) IN ('yes', '1', 'true') THEN 1 ELSE NULL END"""

    elif transform_src == "is_valid_muac_to_1":
        return f"""CASE WHEN {value_expr} ~ '^-?[0-9]*\\.?[0-9]+$' THEN 1 ELSE NULL END"""

    elif transform_src == "is_valid_muac_to_float":
        return f"""CASE WHEN {value_expr} ~ '^-?[0-9]*\\.?[0-9]+$' THEN ({value_expr})::FLOAT ELSE NULL END"""

    elif transform_src == "muac_sam":
        return (
            f"""CASE WHEN {value_expr} ~ '^-?[0-9]*\\.?[0-9]+$' """
            f"""AND ({value_expr})::FLOAT < 11.5 THEN 1 ELSE NULL END"""
        )

    elif transform_src == "muac_mam":
        return (
            f"""CASE WHEN {value_expr} ~ '^-?[0-9]*\\.?[0-9]+$' """
            f"""AND ({value_expr})::FLOAT >= 11.5 AND ({value_expr})::FLOAT < 12.5 THEN 1 ELSE NULL END"""
        )

    elif transform_src == "gender_male":
        return f"""CASE WHEN LOWER({value_expr}) IN ('male', 'm', 'boy', 'male_child') THEN 1 ELSE NULL END"""

    elif transform_src == "gender_female":
        return f"""CASE WHEN LOWER({value_expr}) IN ('female', 'f', 'girl', 'female_child') THEN 1 ELSE NULL END"""

    elif transform_src == "non_empty_to_1":
        return f"""CASE WHEN {value_expr} IS NOT NULL AND TRIM({value_expr}) != '' THEN 1 ELSE NULL END"""

    else:
        logger.warning(f"Unknown transform for field {field.name}, using passthrough")
        return value_expr


def _aggregation_to_sql(agg: str, value_expr: str, field_name: str) -> str:
    """Convert aggregation type to SQL aggregate function."""
    if agg == "count":
        return f"COUNT({value_expr})"
    elif agg == "sum":
        return f"SUM({value_expr})"
    elif agg == "avg":
        return f"AVG({value_expr})"
    elif agg == "first":
        # Use subquery to get value from row with earliest visit_date
        # This properly implements "first" semantics
        return f"""(
            SELECT sub.val FROM (
                SELECT {value_expr} as val, visit_date
                FROM labs_raw_visit_cache sub
                WHERE sub.opportunity_id = labs_raw_visit_cache.opportunity_id
                  AND sub.username = labs_raw_visit_cache.username
                  AND {value_expr} IS NOT NULL
                ORDER BY visit_date ASC
                LIMIT 1
            ) sub
        )"""
    elif agg == "list":
        # Aggregate as array, will be converted to Python list
        return f"ARRAY_AGG({value_expr}) FILTER (WHERE {value_expr} IS NOT NULL)"
    else:
        return f"MIN({value_expr})"


def _build_histogram_fields(hist: HistogramComputation, opportunity_id: int) -> list[tuple[str, str]]:
    """
    Build SQL expressions for histogram bin counts.

    Returns list of (field_name, sql_expression) tuples.
    """
    paths = hist.paths if hist.paths else [hist.path]
    value_expr = _paths_to_coalesce_sql(paths)

    # Apply transform to get float value
    float_expr = _transform_to_sql(hist, value_expr)

    # Calculate bin width
    bin_width = (hist.upper_bound - hist.lower_bound) / hist.num_bins

    fields = []

    # Generate a field for each bin
    for i in range(hist.num_bins):
        bin_lower = hist.lower_bound + (i * bin_width)
        bin_upper = bin_lower + bin_width

        # Bin name like "muac_9_5_10_5_visits"
        lower_str = str(bin_lower).replace(".", "_")
        upper_str = str(bin_upper).replace(".", "_")
        bin_name = f"{hist.bin_name_prefix}_{lower_str}_{upper_str}_visits"

        # SQL: count values in this bin range
        # Note: include_out_of_range means values below lower_bound go to first bin,
        # values above upper_bound go to last bin
        if i == 0 and hist.include_out_of_range:
            # First bin: include values below lower_bound
            bin_sql = f"""COUNT(*) FILTER (WHERE {float_expr} < {bin_upper})"""
        elif i == hist.num_bins - 1 and hist.include_out_of_range:
            # Last bin: include values >= upper_bound
            bin_sql = f"""COUNT(*) FILTER (WHERE {float_expr} >= {bin_lower})"""
        elif i == hist.num_bins - 1:
            # Last bin includes upper bound (but not beyond)
            bin_sql = f"""COUNT(*) FILTER (WHERE {float_expr} >= {bin_lower} AND {float_expr} <= {bin_upper})"""
        else:
            bin_sql = f"""COUNT(*) FILTER (WHERE {float_expr} >= {bin_lower} AND {float_expr} < {bin_upper})"""

        fields.append((bin_name, bin_sql))

    # Add summary statistics (round mean to 2 decimal places for parity with Python)
    fields.append((f"{hist.name}_mean", f"ROUND(AVG({float_expr})::numeric, 2)"))
    fields.append((f"{hist.name}_count", f"COUNT({float_expr})"))

    return fields


def build_flw_aggregation_query(
    config: AnalysisPipelineConfig,
    opportunity_id: int,
) -> str:
    """
    Build SQL query to aggregate raw visits to FLW level.
    """
    select_parts = [
        "username",
        "COUNT(*) as total_visits",
        "COUNT(*) FILTER (WHERE status = 'approved') as approved_visits",
        "COUNT(*) FILTER (WHERE status = 'pending') as pending_visits",
        "COUNT(*) FILTER (WHERE status = 'rejected') as rejected_visits",
        "COUNT(*) FILTER (WHERE flagged = true) as flagged_visits",
        "MIN(visit_date) as first_visit_date",
        "MAX(visit_date) as last_visit_date",
    ]

    # Add custom fields from config
    for field in config.fields:
        paths = field.paths if field.paths else [field.path]
        value_expr = _paths_to_coalesce_sql(paths)
        transformed_expr = _transform_to_sql(field, value_expr)

        if field.aggregation == "first":
            # For "first", order by visit_id to match Python iteration order
            # (visits are typically processed in order they come from API, which is by ID)
            first_expr = f"""(
                ARRAY_AGG({transformed_expr} ORDER BY visit_id ASC) FILTER (WHERE {transformed_expr} IS NOT NULL)
            )[1]"""
            select_parts.append(f"{first_expr} as {field.name}")
        elif field.aggregation == "list":
            agg_expr = f"ARRAY_AGG({transformed_expr}) FILTER (WHERE {transformed_expr} IS NOT NULL)"
            select_parts.append(f"{agg_expr} as {field.name}")
        else:
            agg_expr = _aggregation_to_sql(field.aggregation, transformed_expr, field.name)
            select_parts.append(f"{agg_expr} as {field.name}")

    # Add histogram fields
    for hist in config.histograms:
        hist_fields = _build_histogram_fields(hist, opportunity_id)
        for field_name, field_sql in hist_fields:
            select_parts.append(f"{field_sql} as {field_name}")

    select_clause = ",\n    ".join(select_parts)

    query = f"""
        SELECT
            {select_clause}
        FROM labs_raw_visit_cache
        WHERE opportunity_id = {opportunity_id}
        GROUP BY username
        ORDER BY username
    """

    return query


def execute_flw_aggregation(
    config: AnalysisPipelineConfig,
    opportunity_id: int,
) -> list[dict]:
    """Execute FLW aggregation query and return results as list of dicts."""
    query = build_flw_aggregation_query(config, opportunity_id)

    logger.info(f"[SQL] Executing FLW aggregation query for opp {opportunity_id}")
    logger.debug(f"[SQL] Query:\n{query}")

    with connection.cursor() as cursor:
        cursor.execute(query)
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()

    results = []
    for row in rows:
        row_dict = {}
        for col, val in zip(columns, row):
            # Convert arrays to Python lists
            if isinstance(val, list):
                row_dict[col] = val
            else:
                row_dict[col] = val
        results.append(row_dict)

    logger.info(f"[SQL] Aggregated {len(results)} FLWs")
    return results
