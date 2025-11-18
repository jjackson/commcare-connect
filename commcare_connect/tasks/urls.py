from django.urls import path

from . import views

app_name = "tasks"

urlpatterns = [
    # Main views
    path("", views.TaskListView.as_view(), name="list"),
    path("create/", views.TaskCreationWizardView.as_view(), name="create"),
    path("bulk-create/", views.task_bulk_create, name="bulk_create"),
    path("<int:task_id>/", views.TaskDetailView.as_view(), name="detail"),
    # AI Assistant API
    path("<int:task_id>/ai/initiate/", views.task_initiate_ai, name="ai_initiate"),
    path("<int:task_id>/ai/sessions/", views.task_ai_sessions, name="ai_sessions"),
    path("<int:task_id>/ai/add-session/", views.task_add_ai_session, name="add_ai_session"),
    path("<int:task_id>/ai/transcript/", views.task_ai_transcript, name="ai_transcript"),
    # Opportunity API (used by creation wizard)
    path("opportunities/search/", views.OpportunitySearchAPIView.as_view(), name="opportunity_search"),
    path(
        "opportunities/<int:opportunity_id>/workers/",
        views.OpportunityWorkersAPIView.as_view(),
        name="opportunity_workers",
    ),
    # Database management API
    path("api/database/stats/", views.DatabaseStatsAPIView.as_view(), name="database_stats"),
    path("api/database/reset/", views.DatabaseResetAPIView.as_view(), name="reset_database"),
]
