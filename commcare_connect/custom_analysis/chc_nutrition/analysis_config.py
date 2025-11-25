"""
Analysis configuration for CHC Nutrition project.

Based on SQL query for opportunity 575 - extracts nutrition and health metrics
from UserVisit form_json and aggregates at FLW level.
"""

from commcare_connect.labs.analysis import AnalysisConfig, FieldComputation, HistogramComputation, MapFilter

CHC_NUTRITION_CONFIG = AnalysisConfig(
    grouping_key="username",
    fields=[
        # Delivery Unit - REQUIRED for coverage enrichment
        # NOTE: Named "du_name" not "deliver_unit_name" to avoid shadowing VisitRow field
        FieldComputation(
            name="du_name",
            path="form.case.update.du_name",  # CommCare DU name (alphanumeric like 'AG015FB')
            aggregation="first",
            description="CommCare delivery unit name (from form JSON)",
        ),
        FieldComputation(
            name="commcare_userid",
            path="form.meta.userID",
            aggregation="first",
            description="CommCare user ID from form metadata",
        ),
        # Core Demographics (first occurrence per FLW)
        FieldComputation(
            name="child_age_months",
            path="form.additional_case_info.childs_age_in_month",
            aggregation="first",
            description="Child age in months (first visit)",
        ),
        FieldComputation(
            name="child_gender",
            path="form.additional_case_info.childs_gender",
            aggregation="first",
            description="Child gender (first visit)",
        ),
        # Gender counts for calculating gender split
        FieldComputation(
            name="male_count",
            path="form.additional_case_info.childs_gender",
            aggregation="count",
            transform=lambda x: 1 if str(x).lower() in ["male", "m", "boy", "male_child"] else None,
            description="Number of male children",
        ),
        FieldComputation(
            name="female_count",
            path="form.additional_case_info.childs_gender",
            aggregation="count",
            transform=lambda x: 1 if str(x).lower() in ["female", "f", "girl", "female_child"] else None,
            description="Number of female children",
        ),
        FieldComputation(
            name="phone_number",
            path="form.additional_case_info.household_phone",
            aggregation="first",
            description="Household phone number (first visit)",
        ),
        # MUAC Measurements - Counts and aggregations
        FieldComputation(
            name="muac_consent_count",
            path="form.case.update.muac_consent",  # lowercase muac_consent
            aggregation="count",
            transform=lambda x: 1 if str(x).lower() in ["yes", "1", "true"] else None,
            description="Number of MUAC consents obtained",
        ),
        FieldComputation(
            name="muac_measurements_count",
            path="form.case.update.soliciter_muac_cm",
            aggregation="count",
            description="Number of MUAC measurements taken",
        ),
        FieldComputation(
            name="avg_muac_cm",
            path="form.case.update.soliciter_muac_cm",
            aggregation="avg",
            transform=lambda x: float(x) if x and str(x).replace(".", "").isdigit() else None,
            description="Average MUAC measurement in cm",
        ),
        # SAM: Severe Acute Malnutrition (MUAC < 11.5 cm)
        FieldComputation(
            name="sam_count",
            path="form.case.update.soliciter_muac_cm",
            aggregation="count",
            transform=lambda x: 1
            if x and str(x).replace(".", "").replace("-", "").isdigit() and float(x) < 11.5
            else None,
            description="Number of visits with SAM (MUAC < 11.5 cm)",
        ),
        # MAM: Moderate Acute Malnutrition (MUAC >= 11.5 and < 12.5 cm)
        FieldComputation(
            name="mam_count",
            path="form.case.update.soliciter_muac_cm",
            aggregation="count",
            transform=lambda x: 1
            if x and str(x).replace(".", "").replace("-", "").isdigit() and 11.5 <= float(x) < 12.5
            else None,
            description="Number of visits with MAM (MUAC >= 11.5 and < 12.5 cm)",
        ),
        FieldComputation(
            name="muac_colors_observed",
            path="form.case.update.muac_colour",
            aggregation="list",
            description="List of unique MUAC colors observed (red/yellow/green)",
        ),
        # Health Status Indicators - Counts
        FieldComputation(
            name="children_unwell_count",
            path="form.case.update.va_child_unwell_today",  # in case.update, not form root
            aggregation="count",
            transform=lambda x: 1 if str(x).lower() in ["yes", "1", "true"] else None,
            description="Number of visits where child was unwell",
        ),
        FieldComputation(
            name="malnutrition_diagnosed_count",
            path="form.case.update.diagnosed_with_mal_past_3_months",
            aggregation="count",
            transform=lambda x: 1 if str(x).lower() in ["yes", "1", "true"] else None,
            description="Number of children diagnosed with malnutrition in past 3 months",
        ),
        FieldComputation(
            name="under_malnutrition_treatment_count",
            path="form.case.update.under_treatment_for_mal",
            aggregation="count",
            transform=lambda x: 1 if str(x).lower() in ["yes", "1", "true"] else None,
            description="Number of children under malnutrition treatment",
        ),
        # Diligence Fields - Vitamin A
        FieldComputation(
            name="received_va_dose_before_count",
            path="form.case.update.received_va_dose_before",  # in case.update
            aggregation="count",
            transform=lambda x: 1 if str(x).lower() in ["yes", "1", "true"] else None,
            description="Number of children who received VA dose before",
        ),
        # NOTE: recent_va_dose and va_consent fields don't exist in opp 814 form structure
        # Removed: recent_va_dose_count, va_consent_count
        FieldComputation(
            name="va_confirm_shared_knowledge_count",
            path="form.case.update.va_confirm_shared_knowledge",  # in case.update
            aggregation="count",
            # This field contains text like "va_benefits VA_side_effects", count non-empty values
            transform=lambda x: 1 if x and str(x).strip() else None,
            description="Number of times VA knowledge was shared and confirmed",
        ),
        # Diligence Fields - ORS (Oral Rehydration Solution)
        FieldComputation(
            name="ors_child_recovered_count",
            path="form.ors_group.did_the_child_recover",
            aggregation="count",
            transform=lambda x: 1 if str(x).lower() in ["yes", "1", "true"] else None,
            description="Number of children who recovered with ORS",
        ),
        FieldComputation(
            name="ors_still_facing_symptoms_count",
            path="form.ors_group.still_facing_symptoms",
            aggregation="count",
            transform=lambda x: 1 if str(x).lower() in ["yes", "1", "true"] else None,
            description="Number still facing symptoms after ORS",
        ),
        # Diligence Fields - Immunization/Vaccination
        FieldComputation(
            name="received_any_vaccine_count",
            path="form.pictures.received_any_vaccine",
            aggregation="count",
            transform=lambda x: 1 if str(x).lower() in ["yes", "1", "true"] else None,
            description="Number who received any vaccine",
        ),
        FieldComputation(
            name="immunization_no_capture_reasons",
            path="form.immunization_photo_group.immunization_no_capture_reason",
            aggregation="list",
            description="Reasons for not capturing immunization photo",
        ),
        FieldComputation(
            name="vaccine_not_provided_reasons",
            path="form.pictures.vaccine_not_provided_reason",
            aggregation="list",
            description="Reasons vaccine was not provided",
        ),
        # Diligence Fields - Other
        FieldComputation(
            name="have_glasses_count",
            path="form.case.update.have_glasses",  # in case.update
            aggregation="count",
            transform=lambda x: 1 if str(x).lower() in ["yes", "1", "true"] else None,
            description="Number of children who have glasses",
        ),
        FieldComputation(
            name="hh_have_children_count",
            path="form.additional_case_info.hh_have_children",
            aggregation="count",
            transform=lambda x: 1 if str(x).lower() in ["yes", "1", "true"] else None,
            description="Number of households with children",
        ),
    ],
    histograms=[
        # MUAC distribution histogram with sparkline
        # Bins: 9.5-10.5, 10.5-11.5, ..., 20.5-21.5 (12 bins of width 1.0)
        HistogramComputation(
            name="muac_distribution",
            path="form.case.update.soliciter_muac_cm",
            lower_bound=9.5,
            upper_bound=21.5,
            num_bins=12,
            bin_name_prefix="muac",
            transform=lambda x: float(x) if x and str(x).replace(".", "").replace("-", "").isdigit() else None,
            description="MUAC measurement distribution across bins (9.5-21.5 cm)",
        ),
    ],
    filters={},  # Include all visits regardless of status
    map_filters=[
        # SAM: Severe Acute Malnutrition (MUAC < 11.5 cm)
        MapFilter(
            name="has_sam",
            label="SAM Cases (MUAC < 11.5cm)",
            filter_type="boolean",
            path="form.case.update.soliciter_muac_cm",
            condition=lambda x: (
                float(x) < 11.5 if (x and str(x).replace(".", "").replace("-", "").isdigit()) else False
            ),
            description="Severe Acute Malnutrition cases (MUAC < 11.5 cm)",
        ),
        # MAM: Moderate Acute Malnutrition (MUAC >= 11.5 and < 12.5 cm)
        MapFilter(
            name="has_mam",
            label="MAM Cases (MUAC 11.5-12.5cm)",
            filter_type="boolean",
            path="form.case.update.soliciter_muac_cm",
            condition=lambda x: (
                11.5 <= float(x) < 12.5 if (x and str(x).replace(".", "").replace("-", "").isdigit()) else False
            ),
            description="Moderate Acute Malnutrition cases (MUAC 11.5-12.5 cm)",
        ),
        # Child unwell today
        MapFilter(
            name="child_unwell",
            label="Child Unwell Today",
            filter_type="boolean",
            path="form.case.update.va_child_unwell_today",
            condition=lambda x: str(x).lower() in ["yes", "1", "true"] if x else False,
            description="Child was unwell at time of visit",
        ),
    ],
)
