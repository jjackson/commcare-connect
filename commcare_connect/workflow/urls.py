from django.urls import path

from . import views

app_name = "workflow"

urlpatterns = [
    # List all workflow definitions
    path("", views.WorkflowListView.as_view(), name="list"),
    # Create workflow from template
    path("create/", views.create_workflow_from_template, name="create_from_template"),
    # Legacy: Create example workflow (redirects to create_from_template)
    path("create-example/", views.create_example_workflow, name="create_example"),
    # View workflow definition details (JSON view)
    path("<int:definition_id>/", views.WorkflowDefinitionView.as_view(), name="detail"),
    # Run/execute a workflow (main UI) - also handles edit mode via ?edit=true
    path("<int:definition_id>/run/", views.WorkflowRunView.as_view(), name="run"),
    # View specific workflow run
    path("run/<int:run_id>/", views.WorkflowRunDetailView.as_view(), name="run_detail"),
    # API endpoints
    path("api/workers/", views.get_workers_api, name="api_workers"),
    path("api/run/<int:run_id>/state/", views.update_state_api, name="api_update_state"),
    path("api/run/<int:run_id>/", views.get_run_api, name="api_get_run"),
    # Chat history API endpoints
    path("api/<int:definition_id>/chat/history/", views.get_chat_history_api, name="api_chat_history"),
    path("api/<int:definition_id>/chat/message/", views.add_chat_message_api, name="api_chat_message"),
    path("api/<int:definition_id>/chat/clear/", views.clear_chat_history_api, name="api_chat_clear"),
    # Render code API endpoint
    path("api/<int:definition_id>/render-code/", views.save_render_code_api, name="api_save_render_code"),
    # OCS integration API endpoints
    path("api/ocs/status/", views.ocs_status_api, name="api_ocs_status"),
    path("api/ocs/bots/", views.ocs_bots_api, name="api_ocs_bots"),
]
