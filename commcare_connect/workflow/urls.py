from django.urls import path

from . import views

app_name = "workflow"

urlpatterns = [
    # List all workflow definitions
    path("", views.WorkflowListView.as_view(), name="list"),
    # Create workflow from template
    path("create/", views.create_workflow_from_template_view, name="create_from_template"),
    # Legacy: Create example workflow (redirects to create_from_template)
    path("create-example/", views.create_example_workflow, name="create_example"),
    # View workflow definition details (JSON view)
    path("<int:definition_id>/", views.WorkflowDefinitionView.as_view(), name="detail"),
    # Run/execute a workflow (main UI) - also handles edit mode via ?edit=true
    path("<int:definition_id>/run/", views.WorkflowRunView.as_view(), name="run"),
    # View specific workflow run
    path("run/<int:run_id>/", views.WorkflowRunDetailView.as_view(), name="run_detail"),
    # API endpoints - Workers
    path("api/workers/", views.get_workers_api, name="api_workers"),
    # API endpoints - Workflow runs
    path("api/run/<int:run_id>/state/", views.update_state_api, name="api_update_state"),
    path("api/run/<int:run_id>/", views.get_run_api, name="api_get_run"),
    # API endpoints - Chat history
    path("api/<int:definition_id>/chat/history/", views.get_chat_history_api, name="api_chat_history"),
    path("api/<int:definition_id>/chat/message/", views.add_chat_message_api, name="api_chat_message"),
    path("api/<int:definition_id>/chat/clear/", views.clear_chat_history_api, name="api_chat_clear"),
    # API endpoints - Render code
    path("api/<int:definition_id>/render-code/", views.save_render_code_api, name="api_save_render_code"),
    # API endpoints - OCS integration
    path("api/ocs/status/", views.ocs_status_api, name="api_ocs_status"),
    path("api/ocs/bots/", views.ocs_bots_api, name="api_ocs_bots"),
    # API endpoints - Pipeline data
    path("api/<int:definition_id>/pipeline-data/", views.get_pipeline_data_api, name="api_pipeline_data"),
    path(
        "api/<int:definition_id>/pipeline-sources/add/", views.add_pipeline_source_api, name="api_add_pipeline_source"
    ),
    path(
        "api/<int:definition_id>/pipeline-sources/remove/",
        views.remove_pipeline_source_api,
        name="api_remove_pipeline_source",
    ),
    path("api/available-pipelines/", views.list_available_pipelines_api, name="api_available_pipelines"),
    # API endpoints - Sharing
    path("api/<int:definition_id>/share/", views.share_workflow_api, name="api_share"),
    path("api/<int:definition_id>/unshare/", views.unshare_workflow_api, name="api_unshare"),
    path("api/shared/", views.list_shared_workflows_api, name="api_list_shared"),
]
