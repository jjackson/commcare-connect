"""Minimal URL configuration for URL resolution tests.

This avoids loading the full project urlconf which requires
optional dependencies like django_weasyprint.
"""
from django.urls import include, path

urlpatterns = [
    path("solicitations_new/", include("commcare_connect.solicitations_new.urls", namespace="solicitations_new")),
]
