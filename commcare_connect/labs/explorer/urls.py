"""
URL routing for Labs Explorer
"""

from django.urls import path

from . import views

app_name = "explorer"

urlpatterns = [
    path("", views.RecordListView.as_view(), name="list"),
    path("record/<int:pk>/edit/", views.RecordEditView.as_view(), name="edit"),
    path("download/", views.DownloadRecordsView.as_view(), name="download"),
    path("upload/", views.UploadRecordsView.as_view(), name="upload"),
    path("delete/", views.DeleteRecordsView.as_view(), name="delete"),
]
