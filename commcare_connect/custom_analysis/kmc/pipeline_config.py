"""
KMC pipeline configuration for extracting visit-level data.

Uses the labs analysis pipeline to extract weight, photos, and other metrics
from KMC visits at the visit level (not child level - aggregation happens in views).
"""

from commcare_connect.labs.analysis import AnalysisPipelineConfig, CacheStage, FieldComputation


def _is_valid_weight(x) -> bool:
    """Check if value is a valid weight (numeric)."""
    if not x:
        return False
    s = str(x).strip()
    return s.replace(".", "").replace("-", "").isdigit()


KMC_PIPELINE_CONFIG = AnalysisPipelineConfig(
    grouping_key="username",
    experiment="kmc_timeline",
    terminal_stage=CacheStage.VISIT_LEVEL,  # Visit-level, not aggregated
    fields=[
        # Child identifier for linking
        FieldComputation(
            name="child_case_id",
            path="form.case.@case_id",
            paths=[
                "form.case.@case_id",  # Registration visit
                "form.kmc_beneficiary_case_id",  # Follow-up visits
            ],
            aggregation="first",
            description="KMC beneficiary case ID",
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
        # Weight measurements
        FieldComputation(
            name="weight_grams",
            path="form.anthropometric.child_weight_visit",
            paths=[
                "form.anthropometric.child_weight_visit",
                "form.child_details.birth_weight_reg.child_weight_reg",
            ],
            aggregation="first",
            transform=lambda x: int(x) if _is_valid_weight(x) else None,
            description="Weight in grams",
        ),
        # Visit date
        FieldComputation(
            name="visit_date",
            path="form.grp_kmc_visit.visit_date",
            paths=[
                "form.grp_kmc_visit.visit_date",
                "form.reg_date",
            ],
            aggregation="first",
            description="Visit date",
        ),
        # Visit number
        FieldComputation(
            name="visit_number",
            path="form.grp_kmc_visit.visit_number",
            aggregation="first",
            description="Visit number",
        ),
        # Photo
        FieldComputation(
            name="photo_filename",
            path="form.anthropometric.upload_weight_image",
            paths=[
                "form.anthropometric.upload_weight_image",
                "form.child_details.upload_weight_image",
            ],
            aggregation="first",
            description="Photo filename",
        ),
    ],
    histograms=[],
    filters={},
)
