from django.urls import path

from commcare_connect.audit import experiment_views

app_name = "audit"

urlpatterns = [
    # Experiment-based audit routes (ExperimentRecord implementation)
    path("", experiment_views.ExperimentAuditListView.as_view(), name="session_list"),
    path("create/", experiment_views.ExperimentAuditCreateView.as_view(), name="creation_wizard"),
    path("<int:pk>/", experiment_views.ExperimentAuditDetailView.as_view(), name="session_detail"),
    path("<int:pk>/bulk/", experiment_views.ExperimentBulkAssessmentView.as_view(), name="bulk_assessment"),
    # API endpoints
    path(
        "api/opportunities/search/",
        experiment_views.ExperimentOpportunitySearchAPIView.as_view(),
        name="program_search",
    ),
    path("api/audit/create/", experiment_views.ExperimentAuditCreateAPIView.as_view(), name="create_session"),
    path("api/audit/preview/", experiment_views.ExperimentAuditPreviewAPIView.as_view(), name="preview_audit"),
    path("api/audit/progress/", experiment_views.ExperimentAuditProgressAPIView.as_view(), name="audit_progress"),
    # API endpoints for session interaction during auditing
    path(
        "api/<int:session_id>/result/update/",
        experiment_views.ExperimentAuditResultUpdateView.as_view(),
        name="audit_result_update",
    ),
    path(
        "api/<int:session_id>/visit-data/",
        experiment_views.ExperimentAuditVisitDataView.as_view(),
        name="visit_data",
    ),
    path(
        "api/<int:session_id>/assessment/update/",
        experiment_views.ExperimentAssessmentUpdateView.as_view(),
        name="audit_assessment_update",
    ),
    path(
        "api/<int:session_id>/complete/",
        experiment_views.ExperimentAuditCompleteView.as_view(),
        name="audit_complete",
    ),
    path(
        "api/<int:session_id>/uncomplete/",
        experiment_views.ExperimentAuditUncompleteView.as_view(),
        name="audit_uncomplete",
    ),
    path(
        "api/<int:session_id>/apply-results/",
        experiment_views.ExperimentApplyAssessmentResultsView.as_view(),
        name="apply_assessment_results",
    ),
    path(
        "api/<int:session_id>/bulk-data/",
        experiment_views.ExperimentBulkAssessmentDataView.as_view(),
        name="bulk_assessment_data",
    ),
    path("image/<str:blob_id>/", experiment_views.ExperimentAuditImageView.as_view(), name="audit_image"),
]
