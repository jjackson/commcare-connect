"""
URL configuration for CHC Nutrition analysis.
"""

from django.urls import path

from commcare_connect.custom_analysis.chc_nutrition import views

app_name = "chc_nutrition"

urlpatterns = [
    path("", views.CHCNutritionAnalysisView.as_view(), name="analysis"),
]
