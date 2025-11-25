"""
URL configuration for coverage app.
"""

from django.urls import path

from . import views

app_name = "coverage"

urlpatterns = [
    path("", views.CoverageIndexView.as_view(), name="index"),
    path("map/", views.CoverageMapView.as_view(), name="map"),
    path("debug/", views.CoverageDebugView.as_view(), name="debug"),
    path("token-status/", views.CoverageTokenStatusView.as_view(), name="token_status"),
]
