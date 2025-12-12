"""
KMC pipeline configuration for extracting visit-level data.

Uses the labs analysis pipeline to extract weight, photos, and other metrics
from KMC visits at the visit level (not child level - aggregation happens in views).
"""

from commcare_connect.labs.analysis import AnalysisPipelineConfig, CacheStage, FieldComputation

# Keys to skip when traversing form_json (metadata, not question data)
SKIP_KEYS = frozenset({"@xmlns", "@name", "@uiVersion", "@version", "meta", "#type", "attachments"})


def _is_valid_weight(x) -> bool:
    """Check if value is a valid weight (numeric)."""
    if not x:
        return False
    s = str(x).strip()
    return s.replace(".", "").replace("-", "").isdigit()


def _build_filename_map(data: dict, path: str = "") -> dict[str, str]:
    """
    Build a map of all string values to their paths in a single traversal.

    Args:
        data: Form data dict to traverse
        path: Current path prefix (for recursion)

    Returns:
        Dict mapping string values (filenames) to their question paths
    """
    result = {}
    if not isinstance(data, dict):
        return result

    for key, value in data.items():
        if key in SKIP_KEYS:
            continue

        current_path = f"{path}/{key}" if path else key

        if isinstance(value, str):
            # Map this string value to its path
            result[value] = current_path
        elif isinstance(value, dict):
            # Recurse into nested dict
            result.update(_build_filename_map(value, current_path))

    return result


def extract_images_with_question_ids(visit_data: dict) -> list[dict]:
    """
    Extract images with question IDs from a visit.

    This is a custom extractor for FieldComputation - receives the full visit dict
    and extracts the images array enriched with question_ids from form_json.

    Args:
        visit_data: Full visit dict with 'form_json' and 'images' fields

    Returns:
        List of image dicts with blob_id, name, question_id
    """
    form_json = visit_data.get("form_json", {})
    images = visit_data.get("images", [])

    if not images:
        return []

    # Build filename->path map in a single traversal
    form_data = form_json.get("form", form_json)
    filename_map = _build_filename_map(form_data)

    # Map each image to its question ID
    result = []
    for image in images:
        if not isinstance(image, dict):
            continue

        filename = image.get("name", "")
        question_id = filename_map.get(filename) if filename else None

        result.append(
            {
                "blob_id": image.get("blob_id", ""),
                "name": filename,
                "question_id": question_id,
            }
        )

    return result


KMC_PIPELINE_CONFIG = AnalysisPipelineConfig(
    grouping_key="username",
    experiment="kmc_timeline",
    terminal_stage=CacheStage.VISIT_LEVEL,  # Visit-level, not aggregated
    fields=[
        # Child identifier for linking - using entity_id (Connect's linking field)
        # Note: entity_id from deliver unit is what links visits in Connect
        FieldComputation(
            name="child_entity_id",
            path="form.new_registration_du.deliver.entity_id",
            paths=[
                "form.new_registration_du.deliver.entity_id",  # Registration visit
                "form.kmc_non_pay_visit_du.deliver.entity_id",  # Follow-up visits (non-pay)
                "form.kmc_pay_visit_du.deliver.entity_id",  # Follow-up visits (pay)
            ],
            aggregation="first",
            description="Child entity ID (Connect linking field)",
        ),
        # Child info
        FieldComputation(
            name="child_name",
            path="form.child_details.child_name",
            paths=[
                "form.child_details.child_name",
                "form.svn_name",
            ],
            aggregation="first",
            description="Child name",
        ),
        FieldComputation(
            name="child_dob",
            path="form.child_DOB",
            paths=[
                "form.child_DOB",
                "form.child_details.child_DOB",
            ],
            aggregation="first",
            description="Child date of birth",
        ),
        # Entity info (for display)
        FieldComputation(
            name="entity_name",
            path="form.new_registration_du.deliver.entity_name",
            paths=[
                "form.new_registration_du.deliver.entity_name",
                "form.kmc_non_pay_visit_du.deliver.entity_name",
                "form.kmc_pay_visit_du.deliver.entity_name",
            ],
            aggregation="first",
            description="Entity name from deliver unit",
        ),
        # Weight measurements (for widgets)
        FieldComputation(
            name="weight",  # Match widget field name
            path="form.anthropometric.child_weight_visit",
            paths=[
                "form.anthropometric.child_weight_visit",
                "form.child_details.birth_weight_reg.child_weight_reg",
            ],
            aggregation="first",
            transform=lambda x: int(x) if _is_valid_weight(x) else None,
            description="Weight in grams",
        ),
        # Visit date (for widgets)
        FieldComputation(
            name="date",  # Match widget field name for charts
            path="form.grp_kmc_visit.visit_date",
            paths=[
                "form.grp_kmc_visit.visit_date",
                "form.reg_date",
            ],
            aggregation="first",
            description="Visit date",
        ),
        # Visit number (for widgets)
        FieldComputation(
            name="visit_number",
            path="form.grp_kmc_visit.visit_number",
            aggregation="first",
            description="Visit number",
        ),
        # Photo (for widgets)
        FieldComputation(
            name="photo_url",  # Match widget field name
            path="form.anthropometric.upload_weight_image",
            paths=[
                "form.anthropometric.upload_weight_image",
                "form.child_details.upload_weight_image",
            ],
            aggregation="first",
            description="Photo filename",
        ),
        # Additional fields for timeline details
        FieldComputation(
            name="child_gender",
            path="form.child_details.child_gender",
            aggregation="first",
            description="Child's gender",
        ),
        FieldComputation(
            name="mother_name",
            path="form.mothers_details.mother_name",
            paths=[
                "form.mothers_details.mother_name",
                "form.kmc_beneficiary_name",
            ],
            aggregation="first",
            description="Mother's name",
        ),
        FieldComputation(
            name="mother_phone",
            path="form.mothers_details.mothers_phone_number",
            paths=[
                "form.mothers_details.mothers_phone_number",
                "form.deduplication_block.mothers_phone_number",
            ],
            aggregation="first",
            description="Mother's phone number",
        ),
        FieldComputation(
            name="village",
            path="form.mothers_details.village",
            aggregation="first",
            description="Village name",
        ),
        # GPS coordinates (for map widget)
        FieldComputation(
            name="gps",  # Match widget field name
            paths=["form.visit_gps_manual", "form.reg_gps", "form.meta.location.#text"],
            aggregation="first",
            description="GPS coordinates of the visit",
        ),
        # KMC Practice (for detail panel)
        FieldComputation(
            name="kmc_hours",
            paths=["form.KMC_24-Hour_Recall.kmc_hours"],
            aggregation="first",
            description="KMC hours in last 24 hours",
        ),
        FieldComputation(
            name="kmc_providers",
            paths=["form.KMC_24-Hour_Recall.kmc_providers"],
            aggregation="first",
            description="KMC providers",
        ),
        FieldComputation(
            name="baby_position",
            paths=["form.kmc_positioning_checklist.baby_position"],
            aggregation="first",
            description="Baby position during KMC",
        ),
        # Feeding (for detail panel)
        FieldComputation(
            name="feeding_provided",
            paths=["form.KMC_24-Hour_Recall.feeding_provided"],
            aggregation="first",
            description="Feeding provided",
        ),
        FieldComputation(
            name="successful_feeds",
            paths=["form.danger_signs_checklist.successful_feeds_in_last_24_hours"],
            aggregation="first",
            description="Successful feeds in last 24 hours",
        ),
        # Danger Signs (for detail panel)
        FieldComputation(
            name="temperature",
            paths=["form.danger_signs_checklist.svn_temperature"],
            aggregation="first",
            transform=lambda x: float(x) if x else None,
            description="Child's temperature",
        ),
        FieldComputation(
            name="breath_count",
            paths=["form.danger_signs_checklist.child_breath_count"],
            aggregation="first",
            description="Child's breath count",
        ),
        FieldComputation(
            name="danger_signs",
            paths=["form.danger_signs_checklist.danger_sign_list"],
            aggregation="first",
            description="Danger signs observed",
        ),
        # Visit Info (for detail panel)
        FieldComputation(
            name="visit_location",
            paths=["form.visit_location", "form.reg_location"],
            aggregation="first",
            description="Visit location description",
        ),
        FieldComputation(
            name="visit_timeliness",
            paths=["form.grp_kmc_visit.visit_timeliness"],
            aggregation="first",
            description="Visit timeliness",
        ),
        FieldComputation(
            name="kmc_status",
            paths=["form.grp_kmc_beneficiary.kmc_status", "form.kmc_status"],
            aggregation="first",
            description="KMC status of the child",
        ),
        # Additional anthropometric
        FieldComputation(
            name="height",
            paths=["form.anthropometric.child_height"],
            aggregation="first",
            transform=lambda x: float(x) if x else None,
            description="Child's height in cm",
        ),
        FieldComputation(
            name="birth_weight",
            paths=["form.child_weight_birth"],
            aggregation="first",
            transform=lambda x: int(x) if _is_valid_weight(x) else None,
            description="Birth weight in grams",
        ),
        # Images with question IDs (special transform that receives full visit_data)
        FieldComputation(
            name="images_with_questions",
            path="__images__",  # Special marker - will be computed from full visit context
            aggregation="first",
            transform=extract_images_with_question_ids,
            description="Images mapped to their question IDs in form",
        ),
    ],
    histograms=[],
    filters={},
)
