from django.urls import path

from . import views

app_name = "tasks"

urlpatterns = [
    path("", views.TaskListView.as_view(), name="list"),
    path("create/", views.TaskCreateView.as_view(), name="create"),
    path("<int:task_id>/", views.TaskDetailView.as_view(), name="detail"),
    path("<int:task_id>/update/", views.TaskUpdateView.as_view(), name="update"),
    path("<int:task_id>/comment/", views.task_add_comment, name="add_comment"),
    path("<int:task_id>/quick-update/", views.task_quick_update, name="quick_update"),
    path("<int:task_id>/ai/initiate/", views.task_initiate_ai, name="ai_initiate"),
    path("<int:task_id>/ai/add-session/", views.task_add_ai_session, name="add_ai_session"),
    path("<int:task_id>/ai/transcript/", views.task_ai_transcript, name="ai_transcript"),
    # Database management API endpoints
    path("api/database/stats/", views.DatabaseStatsAPIView.as_view(), name="database_stats"),
    path("api/database/reset/", views.DatabaseResetAPIView.as_view(), name="reset_database"),
]
