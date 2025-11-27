"""
Analysis configuration for Audit.

Defines the FieldComputation for extracting images with question IDs
from visit form_json data.
"""

from commcare_connect.labs.analysis import AnalysisPipelineConfig, FieldComputation


def _search_form_for_filename(data: dict, target: str, path: str = "") -> str | None:
    """Recursively search form_json for a filename, returning the question path."""
    if not isinstance(data, dict):
        return None

    for key, value in data.items():
        if key in ("@xmlns", "@name", "@uiVersion", "@version", "meta", "#type", "attachments"):
            continue

        current_path = f"{path}/{key}" if path else key

        if isinstance(value, str) and value == target:
            return current_path

        if isinstance(value, dict):
            result = _search_form_for_filename(value, target, current_path)
            if result:
                return result

    return None


def extract_images_with_question_ids(visit_data: dict) -> list[dict]:
    """
    Extract images with question IDs from a visit.

    This is a custom extractor for FieldComputation - receives the full visit dict
    and extracts the images array enriched with question_ids from form_json.

    Args:
        visit_data: Full visit dict with 'form_json' and 'images' fields

    Returns:
        List of image dicts with blob_id, name, question_id, and visit metadata
    """
    form_json = visit_data.get("form_json", {})
    images = visit_data.get("images", [])

    if not images:
        return []

    # Extract visit-level metadata
    username = visit_data.get("username") or ""
    visit_date = visit_data.get("visit_date") or ""
    entity_name = visit_data.get("entity_name") or "No Entity"

    # Search form_json for question IDs
    form_data = form_json.get("form", form_json)

    result = []
    for image in images:
        if not isinstance(image, dict):
            continue

        filename = image.get("name", "")
        question_id = _search_form_for_filename(form_data, filename) if filename else None

        result.append(
            {
                "blob_id": image.get("blob_id", ""),
                "name": filename,
                "question_id": question_id,
                "username": username,
                "visit_date": visit_date,
                "entity_name": entity_name,
            }
        )

    return result


# Field computation for extracting images with question_ids
AUDIT_IMAGES_FIELD = FieldComputation(
    name="images_with_questions",
    extractor=extract_images_with_question_ids,
    aggregation="first",
    description="Images with question IDs extracted from form_json",
)

# Config for audit image extraction
AUDIT_EXTRACTION_CONFIG = AnalysisPipelineConfig(
    grouping_key="username",
    experiment="audit",
    fields=[AUDIT_IMAGES_FIELD],
)
