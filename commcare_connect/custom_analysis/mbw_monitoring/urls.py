from django.urls import path

from commcare_connect.custom_analysis.mbw_monitoring import views

app_name = "mbw"

urlpatterns = [
    # Main dashboard (Overview tab is default)
    path("", views.MBWMonitoringDashboardView.as_view(), name="dashboard"),
    # Tab aliases (render same dashboard with tab param)
    path("gps/", views.MBWMonitoringDashboardView.as_view(), {"default_tab": "gps"}, name="gps"),
    path("followup/", views.MBWMonitoringDashboardView.as_view(), {"default_tab": "followup"}, name="followup"),
    # SSE streaming endpoint for data loading
    path("stream/", views.MBWMonitoringStreamView.as_view(), name="stream"),
    # JSON API endpoints for drill-down
    path("api/gps/<str:username>/", views.MBWGPSDetailView.as_view(), name="gps_detail"),
    # Action endpoints
    path("api/suspend-user/", views.MBWSuspendUserView.as_view(), name="suspend_user"),
]
