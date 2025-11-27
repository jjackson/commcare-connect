from django.urls import path

from commcare_connect.audit import views

app_name = "audit"

urlpatterns = [
    # Experiment-based audit routes (ExperimentRecord implementation)
    path("", views.ExperimentAuditListView.as_view(), name="session_list"),
    path("create/", views.ExperimentAuditCreateView.as_view(), name="creation_wizard"),
    path("<int:pk>/", views.ExperimentAuditDetailView.as_view(), name="session_detail"),
    path("<int:pk>/bulk/", views.ExperimentBulkAssessmentView.as_view(), name="bulk_assessment"),
    # API endpoints
    path(
        "api/opportunities/search/",
        views.ExperimentOpportunitySearchAPIView.as_view(),
        name="program_search",
    ),
    path("api/audit/create/", views.ExperimentAuditCreateAPIView.as_view(), name="create_session"),
    path("api/audit/preview/", views.ExperimentAuditPreviewAPIView.as_view(), name="preview_audit"),
    path("api/audit/progress/", views.ExperimentAuditProgressAPIView.as_view(), name="audit_progress"),
    # API endpoints for session interaction during auditing
    path(
        "api/<int:session_id>/visit-data/",
        views.ExperimentAuditVisitDataView.as_view(),
        name="visit_data",
    ),
    path(
        "api/<int:session_id>/save/",
        views.ExperimentSaveAuditView.as_view(),
        name="audit_save",
    ),
    path(
        "api/<int:session_id>/complete/",
        views.ExperimentAuditCompleteView.as_view(),
        name="audit_complete",
    ),
    path(
        "api/<int:session_id>/uncomplete/",
        views.ExperimentAuditUncompleteView.as_view(),
        name="audit_uncomplete",
    ),
    path(
        "api/<int:session_id>/apply-results/",
        views.ExperimentApplyAssessmentResultsView.as_view(),
        name="apply_assessment_results",
    ),
    path(
        "api/<int:session_id>/bulk-data/",
        views.ExperimentBulkAssessmentDataView.as_view(),
        name="bulk_assessment_data",
    ),
    path(
        "image/<int:opp_id>/<str:blob_id>/",
        views.ExperimentAuditImageConnectView.as_view(),
        name="audit_image_connect",
    ),
]
