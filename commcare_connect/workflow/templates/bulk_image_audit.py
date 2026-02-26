"""
Bulk Image Audit Workflow Template.

Multi-opportunity image review with per-FLW pass/fail summary.
Supports Scale Photo, ORS Photo, and MUAC Photo image types.
"""

DEFINITION = {
    "name": "Bulk Image Audit",
    "description": "Review photos across multiple opportunities with per-FLW pass/fail tracking",
    "version": 1,
    "templateType": "bulk_image_audit",
    "statuses": [
        {"id": "config", "label": "Configuring", "color": "gray"},
        {"id": "creating", "label": "Creating Review", "color": "blue"},
        {"id": "reviewing", "label": "In Review", "color": "yellow"},
        {"id": "completed", "label": "Completed", "color": "green"},
        {"id": "failed", "label": "Failed", "color": "red"},
    ],
    "config": {
        "showSummaryCards": True,
    },
    "pipeline_sources": [],
}

RENDER_CODE = """function WorkflowUI({ definition, instance, workers, pipelines, links, actions, onUpdateState }) {
    return <div className="p-6"><p className="text-gray-500">Loading...</p></div>;
}"""

TEMPLATE = {
    "key": "bulk_image_audit",
    "name": "Bulk Image Audit",
    "description": "Review photos across multiple opportunities with per-FLW pass/fail tracking",
    "icon": "fa-images",
    "color": "blue",
    "definition": DEFINITION,
    "render_code": RENDER_CODE,
    "pipeline_schema": None,
}
