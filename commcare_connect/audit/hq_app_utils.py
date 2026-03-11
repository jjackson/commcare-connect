"""Utilities for extracting structured data from CommCare HQ app definitions.

Key function: extract_image_questions — finds all Image-type questions in an app
and auto-detects associated HQ URL fields.
"""
from __future__ import annotations


def _xform_path_to_image_path(xform_path: str) -> str:
    """Strip /data/ prefix from XForm path to get the form JSON question path.

    /data/ors_group/ors_photo → ors_group/ors_photo
    """
    parts = xform_path.strip("/").split("/")
    if parts and parts[0] == "data":
        parts = parts[1:]
    return "/".join(parts)


def _question_id(xform_path: str) -> str:
    """Return the last segment of an XForm path (the question's own ID)."""
    return xform_path.rstrip("/").rsplit("/", 1)[-1]


def extract_image_questions(app: dict) -> list[dict]:
    """Extract visible Image-type questions from an HQ app definition.

    For each form in the app:
    1. Find Image-type questions.
    2. Auto-detect `hq_url_path` by finding a sibling DataBindOnly question
       whose `calculate` field ends with the image question's XForm path.

    Args:
        app: Raw CommCare HQ application definition dict.

    Returns:
        List of dicts: [{id, label, path, hq_url_path, form_name}]
    """
    results = []
    seen_ids: set[str] = set()

    for module in app.get("modules", []):
        for form in module.get("forms", []):
            form_name = _get_name(form)
            form_xmlns = form.get("xmlns", "")
            questions = form.get("questions", [])

            for q in questions:
                if q.get("type") != "Image":
                    continue

                xform_path = q.get("value", "")
                if not xform_path:
                    continue

                image_path = _xform_path_to_image_path(xform_path)
                label = _get_label(q)

                # Auto-detect hq_url_path
                hq_url_path = _detect_hq_url_path(xform_path, questions)

                # Use leaf ID when unique; fall back to full path, then xmlns-qualified path
                leaf_id = _question_id(xform_path)
                if leaf_id not in seen_ids:
                    question_id = leaf_id
                elif image_path not in seen_ids:
                    question_id = image_path
                else:
                    question_id = f"{form_xmlns}:{image_path}" if form_xmlns else image_path
                seen_ids.add(question_id)

                results.append(
                    {
                        "id": question_id,
                        "label": label,
                        "path": image_path,
                        "hq_url_path": hq_url_path,
                        "form_name": form_name,
                    }
                )

    return results


def _detect_hq_url_path(image_xform_path: str, questions: list[dict]) -> str:
    """Find a DataBindOnly sibling whose calculate ends with the image's XForm path.

    Pattern: concat('https://.../', /data/group/image_field)
    Returns the form JSON path (stripped of /data/) of the matching field, or "".
    """
    for q in questions:
        if q.get("type") != "DataBindOnly":
            continue
        calculate = q.get("calculate") or ""
        if calculate.rstrip(")").endswith(image_xform_path):
            return _xform_path_to_image_path(q.get("value", ""))
    return ""


def _get_name(obj: dict) -> str:
    name = obj.get("name", "")
    if isinstance(name, dict):
        return name.get("en", next(iter(name.values()), ""))
    return str(name)


def _get_label(obj: dict) -> str:
    label = obj.get("label", "")
    if isinstance(label, dict):
        return label.get("en", next(iter(label.values()), ""))
    return str(label)
