from django.urls import path

from .views import (
    LabsHomeView,
    ManageSolicitationsListView,
    MyResponsesListView,
    SolicitationCreateOrUpdate,
    SolicitationDetailView,
    SolicitationListView,
    SolicitationResponseCreateOrUpdate,
    SolicitationResponseDetailView,
    SolicitationResponseReviewCreateOrUpdate,
    SolicitationResponsesListView,
)

app_name = "solicitations"

urlpatterns = [
    # Labs Home - NEW
    path("", LabsHomeView.as_view(), name="home"),
    # Program Manager URLs - NEW
    path("manage/", ManageSolicitationsListView.as_view(), name="manage_list"),
    path("create/", SolicitationCreateOrUpdate.as_view(), name="create"),
    path("solicitation/<int:pk>/edit/", SolicitationCreateOrUpdate.as_view(), name="edit"),
    path(
        "solicitation/<int:solicitation_pk>/responses/",
        SolicitationResponsesListView.as_view(),
        name="solicitation_responses",
    ),
    # Public browsing URLs - NEW
    path("opportunities/", SolicitationListView.as_view(), name="list"),
    path("opportunities/eoi/", SolicitationListView.as_view(), {"type": "eoi"}, name="eoi_list"),
    path("opportunities/rfp/", SolicitationListView.as_view(), {"type": "rfp"}, name="rfp_list"),
    path("opportunities/<int:pk>/", SolicitationDetailView.as_view(), name="detail"),
    # Organization response URLs - NEW
    path("responses/", MyResponsesListView.as_view(), name="my_responses"),
    path("opportunities/<int:solicitation_pk>/respond/", SolicitationResponseCreateOrUpdate.as_view(), name="respond"),
    path("response/<int:pk>/", SolicitationResponseDetailView.as_view(), name="response_detail"),
    path("response/<int:pk>/edit/", SolicitationResponseCreateOrUpdate.as_view(), name="response_edit"),
    # Review URLs - NEW
    path(
        "response/<int:response_pk>/review/", SolicitationResponseReviewCreateOrUpdate.as_view(), name="review_create"
    ),
    # Helper URLs (AJAX, file management) - Disabled for now
    # path("s/<int:pk>/save-draft/", save_draft_ajax, name="save_draft"),
    # path("s/<int:pk>/upload-attachment/", upload_attachment, name="upload_attachment"),
    # path("s/<int:pk>/delete-attachment/<int:attachment_id>/", delete_attachment, name="delete_attachment"),
]
