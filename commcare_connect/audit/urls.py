from django.urls import path

from commcare_connect.audit import experiment_views, views

app_name = "audit"

urlpatterns = [
    # Experiment-based audit routes (NEW implementation)
    path("", experiment_views.ExperimentAuditListView.as_view(), name="session_list"),
    path("create/", experiment_views.ExperimentAuditCreateView.as_view(), name="creation_wizard"),
    path("<int:pk>/", experiment_views.ExperimentAuditDetailView.as_view(), name="session_detail"),
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
        "api/<int:session_id>/assessment/update/",
        experiment_views.ExperimentAssessmentUpdateView.as_view(),
        name="audit_assessment_update",
    ),
    path(
        "api/<int:session_id>/complete/",
        experiment_views.ExperimentAuditCompleteView.as_view(),
        name="audit_complete",
    ),
    path("image/<str:blob_id>/", experiment_views.ExperimentAuditImageView.as_view(), name="audit_image"),
    # Legacy audit management routes (keep for existing session viewing)
    path("sessions/<int:pk>/", views.AuditDetailView.as_view(), name="legacy_session_detail"),
    path("sessions/<int:pk>/export/", views.AuditExportView.as_view(), name="session_export"),
    path("sessions/<int:pk>/bulk-assessment/", views.BulkAssessmentView.as_view(), name="bulk_assessment"),
    path("export-all/", views.AuditExportAllView.as_view(), name="export_all"),
    # AJAX endpoints (keep for session interaction)
    path("api/results/<int:session_id>/update/", views.AuditResultUpdateView.as_view(), name="result_update"),
    path("api/assessment/<int:assessment_id>/update/", views.AssessmentUpdateView.as_view(), name="assessment_update"),
    path("api/visit/<int:visit_id>/result/", views.VisitResultUpdateView.as_view(), name="visit_result_update"),
    path(
        "api/sessions/<int:session_id>/apply-results/",
        views.ApplyAssessmentResultsView.as_view(),
        name="apply_assessment_results",
    ),
    path("api/sessions/<int:session_id>/complete/", views.AuditCompleteView.as_view(), name="session_complete"),
    path(
        "api/sessions/<int:session_id>/uncomplete/",
        views.AuditUncompleteView.as_view(),
        name="session_uncomplete",
    ),
    path("api/sessions/<int:session_id>/visit-data/", views.AuditVisitDataView.as_view(), name="visit_data"),
    # Database management
    path("api/database/stats/", views.DatabaseStatsAPIView.as_view(), name="database_stats"),
    path("api/database/reset/", views.DatabaseResetAPIView.as_view(), name="reset_database"),
    path(
        "api/database/download-missing-attachments/",
        views.DownloadMissingAttachmentsAPIView.as_view(),
        name="download_missing_attachments",
    ),
    # Audit template import/export
    path(
        "api/template/<int:definition_id>/export/",
        views.AuditTemplateExportView.as_view(),
        name="definition_export",
    ),
    path("api/template/import/", views.AuditTemplateImportView.as_view(), name="definition_import"),
    # Image serving
    path("image/<str:blob_id>/", views.AuditImageView.as_view(), name="image"),
]
