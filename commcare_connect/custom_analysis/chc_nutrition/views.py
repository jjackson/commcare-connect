"""
Views for CHC Nutrition analysis.

Provides FLW-level analysis of nutrition metrics using the labs analysis framework.

Uses the pipeline pattern:
1. compute_visit_analysis() - cached visit-level data
2. FLWAnalyzer.from_visit_result() - aggregate to FLW level

The visit_result is kept in context for potential drill-down views.
"""

import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from commcare_connect.custom_analysis.chc_nutrition.analysis_config import CHC_NUTRITION_CONFIG
from commcare_connect.labs.analysis import FLWAnalyzer, compute_visit_analysis
from commcare_connect.labs.analysis.base import get_flw_names_for_opportunity

logger = logging.getLogger(__name__)


class CHCNutritionAnalysisView(LoginRequiredMixin, TemplateView):
    """
    Main analysis view for CHC Nutrition project.

    Displays one row per FLW with aggregated nutrition and health metrics.
    The visit-level result is also available for drill-down views.
    """

    template_name = "custom_analysis/chc_nutrition/analysis.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Check labs context
        labs_context = getattr(self.request, "labs_context", {})
        opportunity_id = labs_context.get("opportunity_id")

        context["opportunity_id"] = opportunity_id
        context["opportunity_name"] = labs_context.get("opportunity_name")
        context["has_context"] = bool(opportunity_id)

        if not opportunity_id:
            context["error"] = "No opportunity selected. Please select an opportunity from the labs context."
            return context

        try:
            # Pipeline: Get visit-level analysis (cached)
            logger.info(f"Getting visit analysis for opportunity {opportunity_id}")
            visit_result = compute_visit_analysis(request=self.request, config=CHC_NUTRITION_CONFIG, use_cache=True)

            # Pipeline: Aggregate to FLW level
            logger.info(f"Aggregating {len(visit_result.rows)} visits to FLW level")
            analyzer = FLWAnalyzer(self.request, CHC_NUTRITION_CONFIG)
            flw_result = analyzer.from_visit_result(visit_result)

            logger.info(
                f"Analysis complete: {len(flw_result.rows)} FLWs, "
                f"{flw_result.metadata.get('total_visits', 0)} visits"
            )

            # Get FLW display names from CommCare
            try:
                flw_names = get_flw_names_for_opportunity(self.request)
                logger.info(f"Loaded display names for {len(flw_names)} FLWs")
            except Exception as e:
                logger.warning(f"Failed to fetch FLW names: {e}")
                flw_names = {}

            # FLW-level results for summary table
            context["result"] = flw_result
            context["summary"] = flw_result.get_summary_stats()
            context["from_cache"] = not self.request.GET.get("refresh")

            # Add display names to FLW rows
            for flw in flw_result.rows:
                flw.display_name = flw_names.get(flw.username, flw.username)

            context["flws"] = flw_result.rows

            # Visit-level results for potential drill-down
            context["visit_result"] = visit_result
            context["total_visits"] = len(visit_result.rows)

            # Additional nutrition-specific summaries
            context["nutrition_summary"] = self._get_nutrition_summary(flw_result)

        except Exception as e:
            logger.error(f"Failed to compute CHC Nutrition analysis: {e}", exc_info=True)
            context["error"] = f"Analysis failed: {str(e)}"

        return context

    def _get_nutrition_summary(self, result) -> dict:
        """
        Calculate nutrition-specific summary statistics.

        Args:
            result: FLWAnalysisResult

        Returns:
            Dictionary of nutrition-specific metrics
        """
        if not result.rows:
            return {}

        # Aggregate across all FLWs (handle None values explicitly)
        total_muac_measurements = sum(row.custom_fields.get("muac_measurements_count") or 0 for row in result.rows)

        total_muac_consents = sum(row.custom_fields.get("muac_consent_count") or 0 for row in result.rows)

        total_children_unwell = sum(row.custom_fields.get("children_unwell_count") or 0 for row in result.rows)

        total_malnutrition_diagnosed = sum(
            row.custom_fields.get("malnutrition_diagnosed_count") or 0 for row in result.rows
        )

        total_under_treatment = sum(
            row.custom_fields.get("under_malnutrition_treatment_count") or 0 for row in result.rows
        )

        total_va_doses = sum(row.custom_fields.get("received_va_dose_before_count") or 0 for row in result.rows)

        # SAM and MAM counts
        total_sam = sum(row.custom_fields.get("sam_count") or 0 for row in result.rows)

        total_mam = sum(row.custom_fields.get("mam_count") or 0 for row in result.rows)

        # Calculate averages
        avg_muac_measurements_per_flw = total_muac_measurements / len(result.rows) if result.rows else 0

        # MUAC consent rate
        muac_consent_rate = (total_muac_consents / total_muac_measurements * 100) if total_muac_measurements > 0 else 0

        # SAM and MAM rates
        sam_rate = (total_sam / total_muac_measurements * 100) if total_muac_measurements > 0 else 0
        mam_rate = (total_mam / total_muac_measurements * 100) if total_muac_measurements > 0 else 0

        return {
            "total_muac_measurements": total_muac_measurements,
            "total_muac_consents": total_muac_consents,
            "muac_consent_rate": round(muac_consent_rate, 1),
            "avg_muac_measurements_per_flw": round(avg_muac_measurements_per_flw, 2),
            "total_children_unwell": total_children_unwell,
            "total_malnutrition_diagnosed": total_malnutrition_diagnosed,
            "total_under_treatment": total_under_treatment,
            "total_va_doses": total_va_doses,
            "total_sam": total_sam,
            "sam_rate": round(sam_rate, 1),
            "total_mam": total_mam,
            "mam_rate": round(mam_rate, 1),
        }
