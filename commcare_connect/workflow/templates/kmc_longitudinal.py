"""
KMC Longitudinal Tracking Workflow Template.

Dashboard-first view for Kangaroo Mother Care programs. Tracks children
across multiple visits with actionable KPI cards, filterable child list,
and interactive per-child timeline with weight charts and maps.

All data is extracted visit-level and grouped by beneficiary_case_id
client-side in the React component.
"""

DEFINITION = {
    "name": "KMC Longitudinal Tracking",
    "description": "Track KMC children across visits with outcomes dashboard, child list, and timeline",
    "version": 1,
    "templateType": "kmc_longitudinal",
    "statuses": [
        {"id": "active", "label": "Active", "color": "green"},
        {"id": "discharged", "label": "Discharged", "color": "blue"},
        {"id": "lost_to_followup", "label": "Lost to Follow-up", "color": "red"},
    ],
    "config": {
        "showSummaryCards": False,
        "showFilters": False,
    },
    "pipeline_sources": [],
}

PIPELINE_SCHEMAS = [
    {
        "alias": "visits",
        "name": "KMC Visit Data",
        "description": "Visit-level data for KMC beneficiaries, grouped by beneficiary_case_id",
        "schema": {
            "data_source": {"type": "connect_csv"},
            "grouping_key": "username",
            "terminal_stage": "visit_level",
            "linking_field": "beneficiary_case_id",
            "fields": [
                # --- Identity & Linking ---
                {
                    "name": "beneficiary_case_id",
                    "paths": ["form.case.@case_id", "form.kmc_beneficiary_case_id"],
                    "aggregation": "first",
                },
                {
                    "name": "child_name",
                    "paths": ["form.child_details.child_name", "form.svn_name"],
                    "aggregation": "first",
                },
                {
                    "name": "mother_name",
                    "paths": ["form.mothers_details.mother_name", "form.kmc_beneficiary_name"],
                    "aggregation": "first",
                },
                {
                    "name": "mother_phone",
                    "paths": [
                        "form.mothers_details.mothers_phone_number",
                        "form.deduplication_block.mothers_phone_number",
                    ],
                    "aggregation": "first",
                },
                # --- Clinical Outcomes ---
                {
                    "name": "weight",
                    "paths": [
                        "form.anthropometric.child_weight_visit",
                        "form.child_details.birth_weight_reg.child_weight_reg",
                    ],
                    "aggregation": "first",
                    "transform": "kg_to_g",
                },
                {
                    "name": "birth_weight",
                    "paths": [
                        "form.child_details.birth_weight_group.child_weight_birth",
                        "form.child_weight_birth",
                    ],
                    "aggregation": "first",
                    "transform": "kg_to_g",
                },
                {
                    "name": "height",
                    "path": "form.anthropometric.child_height",
                    "aggregation": "first",
                    "transform": "float",
                },
                # --- Visit Metadata ---
                {
                    "name": "visit_date",
                    "paths": ["form.grp_kmc_visit.visit_date", "form.reg_date"],
                    "aggregation": "first",
                    "transform": "date",
                },
                {
                    "name": "visit_number",
                    "path": "form.grp_kmc_visit.visit_number",
                    "aggregation": "first",
                },
                {
                    "name": "visit_type",
                    "path": "form.grp_kmc_visit.visit_type",
                    "aggregation": "first",
                },
                {
                    "name": "form_name",
                    "path": "form.@name",
                    "aggregation": "first",
                },
                {
                    "name": "time_end",
                    "path": "form.meta.timeEnd",
                    "aggregation": "first",
                },
                # --- Location ---
                {
                    "name": "gps",
                    "paths": ["form.visit_gps_manual", "form.reg_gps", "metadata.location"],
                    "aggregation": "first",
                },
                {
                    "name": "village",
                    "path": "form.mothers_details.village",
                    "aggregation": "first",
                },
                {
                    "name": "subcounty",
                    "paths": ["form.mothers_details.subcounty", "form.subcounty"],
                    "aggregation": "first",
                },
                # --- KMC Practice ---
                {
                    "name": "kmc_hours",
                    "path": "form.KMC_24-Hour_Recall.kmc_hours",
                    "aggregation": "first",
                },
                {
                    "name": "kmc_providers",
                    "path": "form.KMC_24-Hour_Recall.kmc_providers",
                    "aggregation": "first",
                },
                {
                    "name": "baby_position",
                    "path": "form.kmc_positioning_checklist.baby_position",
                    "aggregation": "first",
                },
                # --- Feeding ---
                {
                    "name": "feeding_provided",
                    "path": "form.KMC_24-Hour_Recall.feeding_provided",
                    "aggregation": "first",
                },
                {
                    "name": "successful_feeds",
                    "path": "form.danger_signs_checklist.successful_feeds_in_last_24_hours",
                    "aggregation": "first",
                },
                # --- Vital Signs ---
                {
                    "name": "temperature",
                    "path": "form.danger_signs_checklist.svn_temperature",
                    "aggregation": "first",
                    "transform": "float",
                },
                {
                    "name": "breath_count",
                    "path": "form.danger_signs_checklist.child_breath_count",
                    "aggregation": "first",
                },
                {
                    "name": "danger_signs",
                    "path": "form.danger_signs_checklist.danger_sign_list",
                    "aggregation": "first",
                },
                # --- Status ---
                {
                    "name": "kmc_status",
                    "paths": ["form.grp_kmc_beneficiary.kmc_status", "form.kmc_status"],
                    "aggregation": "first",
                },
                {
                    "name": "visit_location",
                    "paths": ["form.visit_location", "form.reg_location"],
                    "aggregation": "first",
                },
                {
                    "name": "visit_timeliness",
                    "path": "form.grp_kmc_visit.visit_timeliness",
                    "aggregation": "first",
                },
                # --- Demographics (header) ---
                {
                    "name": "child_dob",
                    "paths": ["form.child_DOB", "form.child_details.child_DOB"],
                    "aggregation": "first",
                    "transform": "date",
                },
                {
                    "name": "child_gender",
                    "path": "form.child_details.child_gender",
                    "aggregation": "first",
                },
                {
                    "name": "mother_age",
                    "paths": ["form.mothers_details.mother_age", "form.mother_age"],
                    "aggregation": "first",
                },
                {
                    "name": "reg_date",
                    "path": "form.reg_date",
                    "aggregation": "first",
                    "transform": "date",
                },
                # --- FLW ---
                {
                    "name": "flw_username",
                    "path": "form.meta.username",
                    "aggregation": "first",
                },
            ],
        },
    },
]

# Render code placeholder — will be replaced with full React component in Task 3
RENDER_CODE = """function WorkflowUI({ definition, instance, workers, pipelines, links, actions, onUpdateState }) {
    return React.createElement('div', {className: 'p-4 text-gray-600'},
        'KMC Longitudinal Tracking — loading pipeline data...'
    );
}"""

TEMPLATE = {
    "key": "kmc_longitudinal",
    "name": "KMC Longitudinal Tracking",
    "description": "Track KMC children across visits with outcomes dashboard, child list, and timeline",
    "icon": "fa-baby",
    "color": "teal",
    "definition": DEFINITION,
    "render_code": RENDER_CODE,
    "pipeline_schemas": PIPELINE_SCHEMAS,
}
