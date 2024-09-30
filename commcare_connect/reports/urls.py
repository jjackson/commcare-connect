from django.urls import path

from commcare_connect.reports import views

app_name = "reports"

urlpatterns = [
    path("delivery_stats", views.delivery_stats_report, name="delivery_stats_report"),
    path("program_dashboard", views.program_dashboard_report, name="program_dashboard_report"),
    path("api/visit-map-data/", views.visit_map_data, name="visit_map_data"),
]
