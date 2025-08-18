from django.urls import path

from .ajax_views import (
    solicitation_question_create,
    solicitation_question_delete,
    solicitation_question_reorder,
    solicitation_question_update,
)
from .views import (
    AdminSolicitationOverview,
    ProgramSolicitationDashboard,
    PublicEOIListView,
    PublicRFPListView,
    PublicSolicitationDetailView,
    PublicSolicitationListView,
    ResponseSuccessView,
    SolicitationCreateView,
    SolicitationResponseCreateView,
    SolicitationResponseReview,
    SolicitationResponseTableView,
    SolicitationUpdateView,
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
    path("s/<int:pk>/", PublicSolicitationDetailView.as_view(), name="detail"),
    # Authenticated response submission
    path("s/<int:pk>/respond/", SolicitationResponseCreateView.as_view(), name="respond"),
    path("response/<int:pk>/success/", ResponseSuccessView.as_view(), name="response_success"),
    # Draft management
    path("drafts/", UserDraftListView.as_view(), name="draft_list"),
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
    path(
        "program/<int:program_pk>/solicitations/create/",
        SolicitationCreateView.as_view(),
        name="program_solicitation_create",
    ),
    path(
        "program/<int:program_pk>/solicitations/<int:pk>/edit/",
        SolicitationUpdateView.as_view(),
        name="program_solicitation_edit",
    ),
    # AJAX endpoints for question management
    path(
        "program/<int:program_pk>/solicitations/<int:solicitation_pk>/questions/create/",
        solicitation_question_create,
        name="program_solicitation_question_create",
    ),
    path(
        "program/<int:program_pk>/solicitations/<int:solicitation_pk>/questions/<int:question_pk>/update/",
        solicitation_question_update,
        name="program_solicitation_question_update",
    ),
    path(
        "program/<int:program_pk>/solicitations/<int:solicitation_pk>/questions/<int:question_pk>/delete/",
        solicitation_question_delete,
        name="program_solicitation_question_delete",
    ),
    path(
        "program/<int:program_pk>/solicitations/<int:solicitation_pk>/questions/reorder/",
        solicitation_question_reorder,
        name="program_solicitation_question_reorder",
    ),
]
