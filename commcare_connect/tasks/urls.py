from django.urls import path

from . import views

app_name = "tasks"

urlpatterns = [
    # Main views
    path("", views.TaskListView.as_view(), name="list"),
    path("create/", views.TaskCreationWizardView.as_view(), name="create"),
    path("<int:task_id>/", views.TaskDetailView.as_view(), name="detail"),
    # Task operations
    path("api/<int:task_id>/update/", views.TaskUpdateAPIView.as_view(), name="update"),
    path("api/<int:task_id>/comment/", views.task_add_comment, name="add_comment"),
    # AI assistant
    path("api/<int:task_id>/ai/initiate/", views.task_initiate_ai, name="ai_initiate"),
    path("api/<int:task_id>/ai/sessions/", views.task_ai_sessions, name="ai_sessions"),
    path("api/<int:task_id>/ai/transcript/", views.task_ai_transcript, name="ai_transcript"),
    # Connect API integration
    path("api/opportunities/search/", views.OpportunitySearchAPIView.as_view(), name="opportunity_search"),
    path(
        "api/opportunities/<int:opportunity_id>/field-workers/",
        views.OpportunityFieldWorkersAPIView.as_view(),
        name="opportunity_field_workers",
    ),
    path("api/tasks/bulk-create/", views.TaskCreateAPIView.as_view(), name="bulk_create"),
    # Database management
    path("api/database/stats/", views.DatabaseStatsAPIView.as_view(), name="database_stats"),
    path("api/database/reset/", views.DatabaseResetAPIView.as_view(), name="reset_database"),
]
