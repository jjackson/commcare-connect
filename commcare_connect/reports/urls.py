from django.urls import path

from commcare_connect.reports import views

app_name = "reports"

urlpatterns = [
    path("delivery_stats", view=views.DeliveryStatsReportView.as_view(), name="delivery_stats_report"),
    path("api/visit_map_data/", views.visit_map_data, name="visit_map_data"),
    path("api/dashboard_stats/", views.dashboard_stats_api, name="dashboard_stats_api"),
    path("api/dashboard_charts/", views.dashboard_charts_api, name="dashboard_charts_api"),
]
