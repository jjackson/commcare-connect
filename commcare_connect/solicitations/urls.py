from django.urls import path

from .views import (
    AdminSolicitationOverview,
    ProgramSolicitationDashboard,
    PublicSolicitationDetailView,
    PublicSolicitationListView,
    SolicitationCreateOrUpdate,
    SolicitationCreateView,
    SolicitationReponseDraftListView,
    SolicitationResponseCreateView,
    SolicitationResponseDetailView,
    SolicitationResponseEditView,
    SolicitationResponseFormView,
    SolicitationResponseReview,
    SolicitationResponseSuccessView,
    SolicitationResponseTableView,
    SolicitationUpdateView,
    delete_attachment,
    save_draft_ajax,
    upload_attachment,
)

app_name = "solicitations"

urlpatterns = [
    # Public URLs (no authentication required)
    path("", PublicSolicitationListView.as_view(), name="list"),
    path("eoi/", PublicSolicitationListView.as_view(), {"type": "eoi"}, name="eoi_list"),
    path("rfp/", PublicSolicitationListView.as_view(), {"type": "rfp"}, name="rfp_list"),
    path("s/<int:pk>/", PublicSolicitationDetailView.as_view(), name="detail"),
    # Authenticated response submission - NEW CONSOLIDATED VIEWS
    path("s/<int:solicitation_pk>/respond/", SolicitationResponseFormView.as_view(), name="respond_new"),
    path("response/<int:pk>/edit/", SolicitationResponseFormView.as_view(), name="user_response_edit_new"),
    # Authenticated response submission - OLD VIEWS (temporary for testing)
    path("s/<int:pk>/respond-old/", SolicitationResponseCreateView.as_view(), name="respond"),
    path("response/<int:pk>/success/", SolicitationResponseSuccessView.as_view(), name="response_success"),
    # User response management
    path("response/<int:pk>/", SolicitationResponseDetailView.as_view(), name="user_response_detail"),
    path("response/<int:pk>/edit-old/", SolicitationResponseEditView.as_view(), name="user_response_edit"),
    # Draft management
    path("drafts/", SolicitationReponseDraftListView.as_view(), name="draft_list"),
    path("s/<int:pk>/save-draft/", save_draft_ajax, name="save_draft"),
    # File management
    path("s/<int:pk>/upload-attachment/", upload_attachment, name="upload_attachment"),
    path("s/<int:pk>/delete-attachment/<int:attachment_id>/", delete_attachment, name="delete_attachment"),
    # Admin overview
    path("admin-overview/", AdminSolicitationOverview.as_view(), name="admin_overview"),
    # Program management URLs (moved from program app)
    path("program/<int:pk>/", ProgramSolicitationDashboard.as_view(), name="program_dashboard"),
    path(
        "program/<int:pk>/solicitations/<int:solicitation_pk>/responses/",
        SolicitationResponseTableView.as_view(),
        name="program_response_list",
    ),
    path(
        "program/<int:pk>/solicitations/response/<int:response_pk>/review/",
        SolicitationResponseReview.as_view(),
        name="program_response_review",
    ),
    # NEW CONSOLIDATED VIEWS
    path(
        "program/<int:program_pk>/solicitations/create/",
        SolicitationCreateOrUpdate.as_view(),
        name="program_solicitation_create_new",
    ),
    path(
        "program/<int:program_pk>/solicitations/<int:pk>/edit/",
        SolicitationCreateOrUpdate.as_view(),
        name="program_solicitation_edit_new",
    ),
    # OLD SEPARATE VIEWS (temporary for testing)
    path(
        "program/<int:program_pk>/solicitations/create-old/",
        SolicitationCreateView.as_view(),
        name="program_solicitation_create",
    ),
    path(
        "program/<int:program_pk>/solicitations/<int:pk>/edit-old/",
        SolicitationUpdateView.as_view(),
        name="program_solicitation_edit",
    ),
]
