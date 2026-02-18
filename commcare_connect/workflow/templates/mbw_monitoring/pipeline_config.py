"""
MBW pipeline configuration for GPS analysis.

Extracts GPS coordinates and case linking information for distance analysis.
"""

from commcare_connect.labs.analysis import AnalysisPipelineConfig, CacheStage, FieldComputation


def extract_gps_location(visit_data: dict) -> str | None:
    """
    Extract GPS location string from visit data.

    GPS can be in multiple locations:
    - metadata.location (top-level, already parsed)
    - form.meta.location.#text (nested in form)

    Args:
        visit_data: Full visit dict with form_json

    Returns:
        GPS string "lat lon altitude accuracy" or None
    """
    # First try top-level metadata.location (already extracted by pipeline)
    form_json = visit_data.get("form_json", {})

    # Try form.meta.location.#text path
    meta = form_json.get("form", {}).get("meta", {})
    location = meta.get("location", {})

    if isinstance(location, dict):
        return location.get("#text")
    elif isinstance(location, str):
        return location

    return None


def extract_visit_datetime(visit_data: dict) -> str | None:
    """
    Extract visit datetime from form metadata.

    Args:
        visit_data: Full visit dict with form_json

    Returns:
        ISO datetime string or None
    """
    form_json = visit_data.get("form_json", {})
    meta = form_json.get("form", {}).get("meta", {})
    return meta.get("timeEnd")


MBW_GPS_PIPELINE_CONFIG = AnalysisPipelineConfig(
    grouping_key="username",
    experiment="mbw_gps",
    terminal_stage=CacheStage.VISIT_LEVEL,  # Visit-level for GPS analysis
    linking_field="entity_id",  # Use entity_id for linking visits
    fields=[
        # GPS location - extract from form metadata
        FieldComputation(
            name="gps_location",
            path="__gps__",  # Special marker for custom extraction
            aggregation="first",
            transform=extract_gps_location,
            description="GPS location string (lat lon altitude accuracy)",
        ),
        # Case ID - the visit's direct case
        FieldComputation(
            name="case_id",
            path="form.case.@case_id",
            aggregation="first",
            description="Direct case ID for this visit",
        ),
        # Parent/Mother case ID - for linking related visits
        FieldComputation(
            name="mother_case_id",
            path="form.parents.parent.case.@case_id",
            aggregation="first",
            description="Parent/mother case ID for linking",
        ),
        # Form name - to identify visit type
        FieldComputation(
            name="form_name",
            path="form.@name",
            aggregation="first",
            description="Form name (visit type)",
        ),
        # Visit datetime - for ordering and daily grouping
        FieldComputation(
            name="visit_datetime",
            path="__datetime__",
            aggregation="first",
            transform=extract_visit_datetime,
            description="Visit datetime for ordering",
        ),
        # Entity ID from deliver unit
        FieldComputation(
            name="entity_id_deliver",
            paths=[
                "form.mbw_visit.deliver.entity_id",
                "form.visit_completion.mbw_visit.deliver.entity_id",
            ],
            aggregation="first",
            description="Entity ID from deliver unit",
        ),
        # Entity name from deliver unit
        FieldComputation(
            name="entity_name",
            paths=[
                "form.mbw_visit.deliver.entity_name",
                "form.visit_completion.mbw_visit.deliver.entity_name",
            ],
            aggregation="first",
            description="Entity name (mother name + phone)",
        ),
    ],
    histograms=[],
    filters={},
)
