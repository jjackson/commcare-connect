"""
URL patterns for Custom Pipelines.
"""

from django.urls import path

from . import views

app_name = "custom_pipelines"

urlpatterns = [
    # List all pipelines
    path("", views.PipelineListView.as_view(), name="list"),
    # Run/view a pipeline
    path("<int:definition_id>/run/", views.PipelineRunView.as_view(), name="run"),
    # SSE data stream
    path("<int:definition_id>/stream/", views.PipelineDataStreamView.as_view(), name="data_stream"),
    # API endpoints
    path("api/create/", views.api_create_pipeline, name="api_create"),
    path("api/<int:definition_id>/save/", views.api_save_definition, name="api_save_definition"),
    path("api/<int:definition_id>/render-code/", views.api_save_render_code, name="api_save_render_code"),
    path("api/<int:definition_id>/sql-preview/", views.api_sql_preview, name="api_sql_preview"),
    path("api/<int:definition_id>/chat/history/", views.api_chat_history, name="api_chat_history"),
    path("api/<int:definition_id>/chat/clear/", views.api_clear_chat_history, name="api_clear_chat_history"),
    # Preview SQL from schema (without saving)
    path("api/sql-preview/", views.api_sql_preview_from_schema, name="api_sql_preview_from_schema"),
]
