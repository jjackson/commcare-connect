from django.urls import path

from .views import (
    AdminSolicitationOverview,
    PublicEOIListView,
    PublicRFPListView,
    PublicSolicitationDetailView,
    PublicSolicitationListView,
    ResponseSuccessView,
    SolicitationResponseCreateView,
    UserDraftListView,
    delete_attachment,
    save_draft_ajax,
    upload_attachment,
)

app_name = "solicitations"

urlpatterns = [
    # Public URLs (no authentication required)
    path("", PublicSolicitationListView.as_view(), name="list"),
    path("eoi/", PublicEOIListView.as_view(), name="eoi_list"),
    path("rfp/", PublicRFPListView.as_view(), name="rfp_list"),
    path("<int:pk>/", PublicSolicitationDetailView.as_view(), name="detail"),
    # Authenticated response submission
    path("<int:pk>/respond/", SolicitationResponseCreateView.as_view(), name="respond"),
    path("response/<int:pk>/success/", ResponseSuccessView.as_view(), name="response_success"),
    # Draft management
    path("drafts/", UserDraftListView.as_view(), name="draft_list"),
    path("<int:pk>/save-draft/", save_draft_ajax, name="save_draft"),
    # File management
    path("<int:pk>/upload-attachment/", upload_attachment, name="upload_attachment"),
    path("<int:pk>/delete-attachment/<int:attachment_id>/", delete_attachment, name="delete_attachment"),
    # Admin overview
    path("admin-overview/", AdminSolicitationOverview.as_view(), name="admin_overview"),
]
