"""CommCare HQ MCP Server.

Provides CommCare application structure context for Claude Code sessions.
Tools let you explore app modules, form questions, and JSON field paths
for building workflow pipeline schemas.

Usage (stdio, for Claude Code):
    python tools/commcare_mcp/server.py

Configuration via env vars:
    COMMCARE_HQ_DOMAIN     - Default CommCare domain
    COMMCARE_HQ_API_KEY    - API key as "user@email.com:apikey"
    COMMCARE_HQ_URL        - HQ base URL (default: https://www.commcarehq.org)
"""

from __future__ import annotations

import logging
from pathlib import Path

from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RESOURCES_DIR = Path(__file__).parent / "resources"

mcp = FastMCP(
    "commcare-hq",
    instructions=(
        "CommCare HQ application structure server. Use these tools to understand "
        "CommCare app form structure, question types, and JSON field paths. "
        "This is especially useful when building or debugging workflow pipeline "
        "schemas (PIPELINE_SCHEMAS) that map form fields to data extraction paths."
    ),
)


# --- Resources ---


@mcp.resource("commcare://app-schema")
def app_schema_resource() -> str:
    """CommCare app structure reference — question types, case properties, validation rules."""
    return (RESOURCES_DIR / "app_schema.md").read_text(encoding="utf-8")


@mcp.resource("commcare://xml-reference")
def xml_reference_resource() -> str:
    """CommCare XForm/Suite/Case XML structure reference."""
    return (RESOURCES_DIR / "xml_reference.md").read_text(encoding="utf-8")


@mcp.resource("commcare://data-patterns")
def data_patterns_resource() -> str:
    """How CommCare form submission JSON is structured — path mapping rules and pitfalls."""
    return (RESOURCES_DIR / "data_patterns.md").read_text(encoding="utf-8")


# --- Tools ---


@mcp.tool()
async def list_apps(domain: str = "") -> dict:
    """List all CommCare applications for a domain.

    Returns app names, IDs, module counts, and form counts.
    Use this to find the app_id needed for other tools.

    Args:
        domain: CommCare domain name (optional, uses COMMCARE_HQ_DOMAIN env var if not set)
    """
    from hq_client import list_apps as _list_apps

    try:
        apps = await _list_apps(domain or None)
        return {"apps": apps, "count": len(apps)}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_app_structure(app_id: str, domain: str = "") -> dict:
    """Get the module/form/case-type structure of a CommCare application.

    Shows the full app tree: modules → forms (with xmlns) → case types.
    Use this to understand how an app is organized before drilling into specific forms.

    Args:
        app_id: The CommCare application ID (from list_apps)
        domain: CommCare domain name (optional, uses env var default)
    """
    from extractors import extract_app_structure
    from hq_client import get_app

    try:
        app = await get_app(domain or None, app_id)
        return extract_app_structure(app)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_form_questions(app_id: str, xmlns: str, domain: str = "") -> dict:
    """Get the full question tree for a specific form.

    Shows all questions with their types, labels, constraints, skip logic,
    and nesting (groups/repeats). Use this to understand what data a form collects.

    Args:
        app_id: The CommCare application ID
        xmlns: The form's xmlns identifier (from get_app_structure)
        domain: CommCare domain name (optional)
    """
    from extractors import extract_form_questions
    from hq_client import get_app

    try:
        app = await get_app(domain or None, app_id)
        result = extract_form_questions(app, xmlns)
        if result is None:
            return {"error": f"Form with xmlns '{xmlns}' not found in app {app_id}"}
        return result
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_form_json_paths(app_id: str, xmlns: str, domain: str = "") -> dict:
    """Map form questions to their JSON submission paths for pipeline schemas.

    THIS IS THE KEY TOOL for building PIPELINE_SCHEMAS. It shows exactly what
    path each form question will have in submitted form JSON.

    Example output:
        {"json_path": "form.weight", "type": "Int", "label": "Weight (grams)"}
        {"json_path": "form.child_info.birth_weight", "type": "Decimal", "label": "Birth Weight"}

    Use the json_path values directly in PIPELINE_SCHEMAS field definitions:
        {"name": "weight", "path": "form.weight", "transform": "float"}

    Args:
        app_id: The CommCare application ID
        xmlns: The form's xmlns identifier (from get_app_structure)
        domain: CommCare domain name (optional)
    """
    from extractors import extract_form_json_paths
    from hq_client import get_app

    try:
        app = await get_app(domain or None, app_id)
        result = extract_form_json_paths(app, xmlns)
        if result is None:
            return {"error": f"Form with xmlns '{xmlns}' not found in app {app_id}"}
        return result
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    mcp.run(transport="stdio")
