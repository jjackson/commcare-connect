from django.urls import path

from . import views

app_name = "workflow"

urlpatterns = [
    # List all workflow definitions
    path("", views.WorkflowListView.as_view(), name="list"),
    # Create example workflow
    path("create-example/", views.create_example_workflow, name="create_example"),
    # View workflow definition details
    path("<int:definition_id>/", views.WorkflowDefinitionView.as_view(), name="detail"),
    # Run/execute a workflow (main UI)
    path("<int:definition_id>/run/", views.WorkflowRunView.as_view(), name="run"),
    # View specific workflow instance
    path("instance/<int:instance_id>/", views.WorkflowInstanceView.as_view(), name="instance"),
    # API endpoints
    path("api/workers/", views.get_workers_api, name="api_workers"),
    path("api/instance/<int:instance_id>/state/", views.update_state_api, name="api_update_state"),
    path("api/instance/<int:instance_id>/", views.get_instance_api, name="api_get_instance"),
]
