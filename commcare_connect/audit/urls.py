from django.urls import path

from commcare_connect.audit import views

app_name = "audit"

urlpatterns = [
    # Audit session management
    path("", views.AuditSessionListView.as_view(), name="session_list"),
    path("sessions/create/", views.AuditSessionCreateView.as_view(), name="session_create"),
    path("sessions/<int:pk>/", views.AuditSessionDetailView.as_view(), name="session_detail"),
    path("sessions/<int:pk>/export/", views.AuditExportView.as_view(), name="session_export"),
    # Audit creation wizard
    path("wizard/", views.AuditCreationWizardView.as_view(), name="creation_wizard"),
    # AJAX endpoints
    path("api/results/<int:session_id>/update/", views.AuditResultUpdateView.as_view(), name="result_update"),
    path("api/sessions/<int:session_id>/complete/", views.AuditSessionCompleteView.as_view(), name="session_complete"),
    path("api/sessions/<int:session_id>/visit-data/", views.AuditVisitDataView.as_view(), name="visit_data"),
    # Audit creation API endpoints
    path("api/programs/search/", views.ProgramSearchAPIView.as_view(), name="program_search"),
    path(
        "api/programs/<int:program_id>/opportunities/",
        views.ProgramOpportunitiesAPIView.as_view(),
        name="program_opportunities",
    ),
    path("api/audit/preview/", views.AuditPreviewAPIView.as_view(), name="preview_audit"),
    path("api/audit/create/", views.AuditSessionCreateAPIView.as_view(), name="create_session"),
    # Image serving
    path("image/<str:blob_id>/", views.AuditImageView.as_view(), name="image"),
]
