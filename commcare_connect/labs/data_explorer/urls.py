"""
URL routing for Labs Data Explorer
"""

from django.urls import path

from . import views

app_name = "data-explorer"

urlpatterns = [
    # Main list view
    path("", views.RecordListView.as_view(), name="list"),
    # Edit record
    path("record/<int:record_id>/edit/", views.RecordEditView.as_view(), name="edit"),
    # Download records
    path("download/", views.RecordDownloadView.as_view(), name="download"),
    # Upload/import records
    path("upload/", views.RecordUploadView.as_view(), name="upload"),
]
