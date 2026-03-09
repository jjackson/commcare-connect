"""
KMC Project Metrics Dashboard Workflow Template.

Program-level M&E dashboard for KMC (Kangaroo Mother Care) projects.
Aggregates visit data across all FLWs and SVNs to show overall project
performance against M&E indicator targets.

Three views:
1. Overview — Top-line KPI cards + enrollment/visit charts
2. Outcomes & Outputs — Detailed metrics with charts by M&E category
3. Indicators Table — All computable indicators with status and trend

Uses the same visit-level pipeline as kmc_longitudinal, with client-side
aggregation in React for project-wide metrics.
"""

DEFINITION = {
    "name": "KMC Project Metrics",
    "description": "Program-level M&E dashboard showing enrollment, health outcomes, KMC practice, and visit quality indicators",
    "version": 1,
    "templateType": "kmc_project_metrics",
    "statuses": [
        {"id": "active", "label": "Active", "color": "green"},
        {"id": "review", "label": "Under Review", "color": "yellow"},
        {"id": "closed", "label": "Closed", "color": "gray"},
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
        "name": "KMC Project Metrics Data",
        "description": "Visit-level data for computing program-wide M&E indicators",
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
                    "paths": [
                        "form.grp_kmc_beneficiary.child_name",
                        "form.grp_beneficiary_details.child_name",
                        "form.svn_name",
                        "form.mothers_details.child_name",
                    ],
                    "aggregation": "first",
                },
                {
                    "name": "flw_username",
                    "path": "form.meta.username",
                    "aggregation": "first",
                },
                # --- Visit Metadata ---
                {
                    "name": "visit_number",
                    "path": "form.grp_kmc_visit.visit_number",
                    "aggregation": "first",
                    "transform": "int",
                },
                {
                    "name": "visit_date",
                    "paths": ["form.grp_kmc_visit.visit_date", "form.reg_date"],
                    "aggregation": "first",
                    "transform": "date",
                },
                {
                    "name": "visit_timeliness",
                    "path": "form.grp_kmc_visit.visit_timeliness",
                    "aggregation": "first",
                },
                {
                    "name": "visit_type",
                    "path": "form.grp_kmc_visit.visit_type",
                    "aggregation": "first",
                },
                {
                    "name": "first_visit_date",
                    "path": "form.grp_kmc_visit.first_visit_date",
                    "aggregation": "first",
                    "transform": "date",
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
                # --- Clinical ---
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
                # --- KMC Practice ---
                {
                    "name": "kmc_hours",
                    "path": "form.kmc_24-hour_recall.kmc_hours",
                    "aggregation": "first",
                    "transform": "float",
                },
                {
                    "name": "kmc_hours_secondary",
                    "path": "form.kmc_24-hour_recall.kmc_hours_secondary",
                    "aggregation": "first",
                    "transform": "float",
                },
                {
                    "name": "total_kmc_hours",
                    "path": "form.kmc_24-hour_recall.total_kmc_hours",
                    "aggregation": "first",
                    "transform": "float",
                },
                {
                    "name": "baby_position",
                    "path": "form.kmc_positioning_checklist.baby_position",
                    "aggregation": "first",
                },
                # --- Feeding ---
                {
                    "name": "feeding_provided",
                    "path": "form.kmc_24-hour_recall.feeding_provided",
                    "aggregation": "first",
                },
                {
                    "name": "successful_feeds",
                    "path": "form.danger_signs_checklist.successful_feeds_in_last_24_hours",
                    "aggregation": "first",
                    "transform": "int",
                },
                # --- Danger Signs & Referrals ---
                {
                    "name": "danger_sign_positive",
                    "path": "form.danger_signs_checklist.danger_sign_positive",
                    "aggregation": "first",
                },
                {
                    "name": "danger_sign_list",
                    "path": "form.danger_signs_checklist.danger_sign_list",
                    "aggregation": "first",
                },
                {
                    "name": "child_referred",
                    "path": "form.danger_signs_checklist.child_referred",
                    "aggregation": "first",
                },
                {
                    "name": "child_taken_to_hospital",
                    "path": "form.referral_check.child_taken_to_the_hospital",
                    "aggregation": "first",
                },
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
                    "transform": "int",
                },
                # --- Status & Discharge ---
                {
                    "name": "child_alive",
                    "path": "form.child_alive",
                    "aggregation": "first",
                },
                {
                    "name": "kmc_status",
                    "paths": ["form.grp_kmc_beneficiary.kmc_status", "form.kmc_status"],
                    "aggregation": "first",
                },
                {
                    "name": "kmc_status_discharged",
                    "path": "form.kmc_discontinuation.kmc_status_discharged",
                    "aggregation": "first",
                },
                # --- Registration & Timeline ---
                {
                    "name": "reg_date",
                    "paths": [
                        "form.grp_kmc_beneficiary.reg_date",
                        "form.reg_date",
                    ],
                    "aggregation": "first",
                    "transform": "date",
                },
                {
                    "name": "days_since_reg",
                    "path": "form.days_since_reg",
                    "aggregation": "first",
                    "transform": "int",
                },
                {
                    "name": "child_dob",
                    "paths": [
                        "form.mothers_details.child_DOB",
                        "form.child_DOB",
                    ],
                    "aggregation": "first",
                    "transform": "date",
                },
                # --- Location ---
                {
                    "name": "gps",
                    "paths": ["form.visit_gps_manual", "form.reg_gps", "metadata.location"],
                    "aggregation": "first",
                },
                {
                    "name": "village",
                    "paths": [
                        "form.grp_kmc_beneficiary.village",
                        "form.address_change_grp.location.village",
                        "form.village",
                    ],
                    "aggregation": "first",
                },
                {
                    "name": "subcounty",
                    "paths": ["form.sub_country", "form.subcounty"],
                    "aggregation": "first",
                },
                # --- Payment ---
                {
                    "name": "visit_pay",
                    "path": "form.grp_kmc_visit.visit_pay_yes_no",
                    "aggregation": "first",
                },
            ],
        },
    },
]
