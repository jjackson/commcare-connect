from django.urls import path

from commcare_connect.custom_analysis.mbw import views

app_name = "mbw"

urlpatterns = [
    # Main GPS analysis view
    path("gps/", views.MBWGPSAnalysisView.as_view(), name="gps_analysis"),
    # SSE streaming endpoint for progress
    path("gps/stream/", views.MBWGPSStreamView.as_view(), name="gps_stream"),
    # JSON API endpoint
    path("gps/api/", views.MBWGPSDataView.as_view(), name="gps_data"),
    # Visit detail endpoint for drill-down
    path("gps/api/<str:username>/", views.MBWGPSVisitDetailView.as_view(), name="gps_visit_detail"),
]
