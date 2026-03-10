"""Utilities for extracting structured data from CommCare HQ app definitions.

Key function: extract_image_questions — finds all Image-type questions in an app,
filters out always-hidden ones (ancestors with trivially-false `relevant` conditions),
and auto-detects associated HQ URL fields.
"""
from __future__ import annotations

# Trivially-false XPath relevant expressions (whitespace-normalized, lower-cased).
_ALWAYS_FALSE_PATTERNS = frozenset(["1=2", "0=1", "false()"])


def _is_always_false(relevant: str | None) -> bool:
    """Return True if the relevant expression is trivially always-false."""
    if not relevant:
        return False
    normalized = "".join(relevant.lower().split())
    return normalized in _ALWAYS_FALSE_PATTERNS


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
    1. Collect all questions into a path→question index.
    2. Find Image-type questions.
    3. Filter out questions where the question itself OR any ancestor group
       has a trivially-always-false `relevant` condition.
    4. Auto-detect `hq_url_path` by finding a sibling DataBindOnly question
       whose `calculate` field ends with the image question's XForm path.

    Args:
        app: Raw CommCare HQ application definition dict.

    Returns:
        List of dicts: [{id, label, path, hq_url_path, form_name}]
    """
    results = []

    for module in app.get("modules", []):
        for form in module.get("forms", []):
            form_name = _get_name(form)
            questions = form.get("questions", [])

            # Build path → question index for ancestor lookups
            path_index: dict[str, dict] = {q["value"]: q for q in questions if q.get("value")}

            for q in questions:
                if q.get("type") != "Image":
                    continue

                xform_path = q.get("value", "")
                if not xform_path:
                    continue

                # Check self and all ancestor paths for always-false relevant
                if _has_always_false_ancestor(xform_path, path_index):
                    continue

                image_path = _xform_path_to_image_path(xform_path)
                label = _get_label(q)

                # Auto-detect hq_url_path
                hq_url_path = _detect_hq_url_path(xform_path, questions)

                results.append(
                    {
                        "id": _question_id(xform_path),
                        "label": label,
                        "path": image_path,
                        "hq_url_path": hq_url_path,
                        "form_name": form_name,
                    }
                )

    return results


def _has_always_false_ancestor(xform_path: str, path_index: dict[str, dict]) -> bool:
    """Return True if the question or any ancestor group is always-false."""
    # Check the question itself
    self_q = path_index.get(xform_path)
    if self_q and _is_always_false(self_q.get("relevant")):
        return True

    # Walk up the path hierarchy, skipping index 1 (/data) — the XForm root
    # is never a filterable question in path_index.
    parts = xform_path.strip("/").split("/")
    for i in range(2, len(parts)):
        ancestor_path = "/" + "/".join(parts[:i])
        ancestor = path_index.get(ancestor_path)
        if ancestor and _is_always_false(ancestor.get("relevant")):
            return True

    return False


def _detect_hq_url_path(image_xform_path: str, questions: list[dict]) -> str:
    """Find a DataBindOnly sibling whose calculate ends with the image's XForm path.

    Pattern: concat('https://.../', /data/group/image_field)
    Returns the form JSON path (stripped of /data/) of the matching field, or "".
    """
    for q in questions:
        if q.get("type") != "DataBindOnly":
            continue
        calculate = q.get("calculate", "")
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
