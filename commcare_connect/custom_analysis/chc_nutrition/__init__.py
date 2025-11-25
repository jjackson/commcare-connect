"""
CHC Nutrition Analysis

Analyzes nutrition-related data from CHC (Community Health Center) programs.
Focuses on child health metrics, MUAC measurements, and diligence checks.
"""

from commcare_connect.coverage.config_registry import register_config
from commcare_connect.custom_analysis.chc_nutrition.analysis_config import CHC_NUTRITION_CONFIG

# Register config for coverage URL parameter lookup
register_config("chc_nutrition", CHC_NUTRITION_CONFIG)
