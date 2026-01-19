"""
Data Access Layer for Custom Pipelines.

This layer uses LabsRecordAPIClient to interact with production LabsRecord API.
It handles:
1. Managing pipeline definitions, render code, and chat history via production API
2. Converting JSON schema to AnalysisPipelineConfig for SQL execution

This is a pure API client with no local database storage.
"""

import logging
from typing import Any

from django.conf import settings
from django.http import HttpRequest

from commcare_connect.labs.analysis.config import (
    AnalysisPipelineConfig,
    CacheStage,
    FieldComputation,
    HistogramComputation,
)
from commcare_connect.labs.integrations.connect.api_client import LabsRecordAPIClient
from commcare_connect.labs.models import LocalLabsRecord

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Proxy Models for LabsRecords
# -----------------------------------------------------------------------------


class PipelineDefinitionRecord(LocalLabsRecord):
    """Proxy model for pipeline definition LabsRecords (JSON schema)."""

    @property
    def name(self):
        return self.data.get("name", "Untitled Pipeline")

    @property
    def description(self):
        return self.data.get("description", "")

    @property
    def version(self):
        return self.data.get("version", 1)

    @property
    def render_code_id(self):
        return self.data.get("render_code_id")

    @property
    def schema(self) -> dict:
        """Get the pipeline schema (fields, grouping, etc.)."""
        return self.data.get("schema", {})


class PipelineRenderCodeRecord(LocalLabsRecord):
    """Proxy model for pipeline render code LabsRecords (React/JSX)."""

    @property
    def definition_id(self):
        return self.data.get("definition_id")

    @property
    def component_code(self):
        return self.data.get("component_code", "")

    @property
    def version(self):
        return self.data.get("version", 1)


class PipelineChatHistoryRecord(LocalLabsRecord):
    """Proxy model for pipeline chat history LabsRecords."""

    @property
    def definition_id(self):
        return self.data.get("definition_id")

    @property
    def messages(self):
        return self.data.get("messages", [])

    @property
    def created_at(self):
        return self.data.get("created_at")

    @property
    def updated_at(self):
        return self.data.get("updated_at")


# -----------------------------------------------------------------------------
# Transform Registry - Maps transform names to functions
# -----------------------------------------------------------------------------

TRANSFORM_REGISTRY = {
    "kg_to_g": lambda x: int(float(x) * 1000) if x and str(x).replace(".", "").replace("-", "").isdigit() else None,
    "float": lambda x: float(x) if x else None,
    "int": lambda x: int(float(x)) if x else None,
    "date": None,  # No transform, keep as string
    "string": lambda x: str(x) if x else None,
}


def get_transform_function(transform_name: str | None):
    """Get transform function from registry by name."""
    if not transform_name:
        return None
    return TRANSFORM_REGISTRY.get(transform_name)


# -----------------------------------------------------------------------------
# JSON Schema to AnalysisPipelineConfig Converter
# -----------------------------------------------------------------------------


def json_to_pipeline_config(schema: dict, experiment: str = "custom_pipeline") -> AnalysisPipelineConfig:
    """
    Convert a JSON pipeline schema to an AnalysisPipelineConfig object.

    The JSON schema format:
    {
        "name": "Pipeline Name",
        "description": "What this pipeline does",
        "version": 1,
        "grouping_key": "username",
        "terminal_stage": "visit_level" | "aggregated",
        "linking_field": "entity_id",
        "fields": [
            {
                "name": "field_name",
                "path": "form.path.to.field",
                "paths": ["form.path1", "form.path2"],  # Optional fallbacks
                "aggregation": "first" | "sum" | "avg" | etc.,
                "transform": "kg_to_g" | "float" | "int" | "date" | null,
                "description": "Human readable description",
                "default": null
            }
        ],
        "histograms": [
            {
                "name": "histogram_name",
                "path": "form.path.to.numeric.field",
                "lower_bound": 0,
                "upper_bound": 100,
                "num_bins": 10,
                "bin_name_prefix": "prefix",
                "transform": "float",
                "description": "Description"
            }
        ],
        "filters": {}
    }

    Args:
        schema: JSON schema dict
        experiment: Experiment name for caching (default: "custom_pipeline")

    Returns:
        AnalysisPipelineConfig object
    """
    # Parse fields
    fields = []
    for field_def in schema.get("fields", []):
        # Get transform function from registry
        transform = get_transform_function(field_def.get("transform"))

        field_comp = FieldComputation(
            name=field_def["name"],
            path=field_def.get("path", ""),
            paths=field_def.get("paths"),
            aggregation=field_def.get("aggregation", "first"),
            transform=transform,
            description=field_def.get("description", ""),
            default=field_def.get("default"),
        )
        fields.append(field_comp)

    # Parse histograms
    histograms = []
    for hist_def in schema.get("histograms", []):
        transform = get_transform_function(hist_def.get("transform"))

        hist_comp = HistogramComputation(
            name=hist_def["name"],
            path=hist_def.get("path", ""),
            paths=hist_def.get("paths"),
            lower_bound=hist_def["lower_bound"],
            upper_bound=hist_def["upper_bound"],
            num_bins=hist_def["num_bins"],
            bin_name_prefix=hist_def.get("bin_name_prefix", ""),
            transform=transform,
            description=hist_def.get("description", ""),
            include_out_of_range=hist_def.get("include_out_of_range", True),
        )
        histograms.append(hist_comp)

    # Parse terminal stage
    terminal_stage_str = schema.get("terminal_stage", "visit_level")
    terminal_stage = CacheStage.VISIT_LEVEL if terminal_stage_str == "visit_level" else CacheStage.AGGREGATED

    return AnalysisPipelineConfig(
        grouping_key=schema.get("grouping_key", "username"),
        fields=fields,
        histograms=histograms,
        filters=schema.get("filters", {}),
        date_field=schema.get("date_field", "visit_date"),
        experiment=experiment,
        terminal_stage=terminal_stage,
        linking_field=schema.get("linking_field", "entity_id"),
    )


def pipeline_config_to_json(config: AnalysisPipelineConfig) -> dict:
    """
    Convert an AnalysisPipelineConfig back to JSON schema format.

    Note: Transform functions are converted back to their registry names where possible.

    Args:
        config: AnalysisPipelineConfig object

    Returns:
        JSON schema dict
    """
    # Reverse lookup for transform names
    transform_name_lookup = {v: k for k, v in TRANSFORM_REGISTRY.items() if v is not None}

    fields = []
    for field_comp in config.fields:
        field_dict: dict[str, Any] = {
            "name": field_comp.name,
            "aggregation": field_comp.aggregation,
            "description": field_comp.description,
        }

        if field_comp.path:
            field_dict["path"] = field_comp.path
        if field_comp.paths:
            field_dict["paths"] = field_comp.paths
        if field_comp.default is not None:
            field_dict["default"] = field_comp.default
        if field_comp.transform:
            # Try to find the transform name
            transform_name = transform_name_lookup.get(field_comp.transform)
            if transform_name:
                field_dict["transform"] = transform_name

        fields.append(field_dict)

    histograms = []
    for hist_comp in config.histograms:
        hist_dict: dict[str, Any] = {
            "name": hist_comp.name,
            "path": hist_comp.path,
            "lower_bound": hist_comp.lower_bound,
            "upper_bound": hist_comp.upper_bound,
            "num_bins": hist_comp.num_bins,
            "bin_name_prefix": hist_comp.bin_name_prefix,
            "description": hist_comp.description,
            "include_out_of_range": hist_comp.include_out_of_range,
        }

        if hist_comp.paths:
            hist_dict["paths"] = hist_comp.paths
        if hist_comp.transform:
            transform_name = transform_name_lookup.get(hist_comp.transform)
            if transform_name:
                hist_dict["transform"] = transform_name

        histograms.append(hist_dict)

    return {
        "grouping_key": config.grouping_key,
        "terminal_stage": config.terminal_stage.value,
        "linking_field": config.linking_field,
        "date_field": config.date_field,
        "fields": fields,
        "histograms": histograms,
        "filters": config.filters,
    }


# -----------------------------------------------------------------------------
# Data Access Class
# -----------------------------------------------------------------------------


class PipelineDataAccess:
    """
    Data access layer for custom pipelines that uses LabsRecordAPIClient for state.
    """

    EXPERIMENT = "custom_pipeline"

    def __init__(
        self,
        opportunity_id: int | None = None,
        organization_id: int | None = None,
        program_id: int | None = None,
        user=None,
        request: HttpRequest | None = None,
        access_token: str | None = None,
    ):
        """
        Initialize the pipeline data access layer.

        Args:
            opportunity_id: Optional opportunity ID for scoped API requests
            organization_id: Optional organization ID for scoped API requests
            program_id: Optional program ID for scoped API requests
            user: Django User object (for OAuth token extraction)
            request: HttpRequest object (for extracting token and org context in labs mode)
            access_token: OAuth token for Connect production APIs
        """
        self.opportunity_id = opportunity_id
        self.organization_id = organization_id
        self.program_id = program_id
        self.user = user
        self.request = request

        # Use labs_context from middleware if available (takes precedence)
        if request and hasattr(request, "labs_context"):
            labs_context = request.labs_context
            if not opportunity_id and "opportunity_id" in labs_context:
                self.opportunity_id = labs_context["opportunity_id"]
            if not program_id and "program_id" in labs_context:
                self.program_id = labs_context["program_id"]
            if not organization_id and "organization_id" in labs_context:
                self.organization_id = labs_context["organization_id"]

        # Get OAuth token
        if not access_token and request:
            # Try to get token from labs session or SocialAccount
            if hasattr(request, "session") and "labs_oauth" in request.session:
                access_token = request.session["labs_oauth"].get("access_token")
            elif user:
                from allauth.socialaccount.models import SocialAccount, SocialToken

                try:
                    social_account = SocialAccount.objects.get(user=user, provider="connect")
                    social_token = SocialToken.objects.get(account=social_account)
                    access_token = social_token.token
                except (SocialAccount.DoesNotExist, SocialToken.DoesNotExist):
                    pass

        if not access_token:
            raise ValueError("OAuth access token required for pipeline data access")

        self.access_token = access_token
        self.production_url = settings.CONNECT_PRODUCTION_URL.rstrip("/")

        # Initialize Labs API client for state management
        self.labs_api = LabsRecordAPIClient(
            access_token,
            opportunity_id=self.opportunity_id,
            organization_id=self.organization_id,
            program_id=self.program_id,
        )

    def close(self):
        """Close any resources."""
        pass

    # -------------------------------------------------------------------------
    # Pipeline Definition Methods
    # -------------------------------------------------------------------------

    def list_definitions(self) -> list[PipelineDefinitionRecord]:
        """List all pipeline definitions."""
        records = self.labs_api.get_records(
            experiment=self.EXPERIMENT,
            type="pipeline_definition",
            model_class=PipelineDefinitionRecord,
        )
        return records

    def get_definition(self, definition_id: int) -> PipelineDefinitionRecord | None:
        """Get a specific pipeline definition by ID."""
        record = self.labs_api.get_record_by_id(
            definition_id,
            experiment=self.EXPERIMENT,
            type="pipeline_definition",
            model_class=PipelineDefinitionRecord,
        )
        return record

    def create_definition(
        self,
        name: str,
        description: str,
        schema: dict,
        render_code: str = "",
    ) -> PipelineDefinitionRecord:
        """
        Create a new pipeline definition.

        Args:
            name: Pipeline name
            description: Pipeline description
            schema: Pipeline schema (fields, grouping_key, etc.)
            render_code: Optional initial render code

        Returns:
            Created PipelineDefinitionRecord
        """
        # Create the definition record
        definition_data = {
            "name": name,
            "description": description,
            "version": 1,
            "schema": schema,
        }

        result = self.labs_api.create_record(
            experiment=self.EXPERIMENT,
            type="pipeline_definition",
            data=definition_data,
        )

        definition_id = result.id

        # Create render code record if provided
        if render_code:
            render_result = self.labs_api.create_record(
                experiment=self.EXPERIMENT,
                type="pipeline_render_code",
                data={
                    "definition_id": definition_id,
                    "component_code": render_code,
                    "version": 1,
                },
            )

            # Update definition with render_code_id
            definition_data["render_code_id"] = render_result.id
            self.labs_api.update_record(
                definition_id,
                experiment=self.EXPERIMENT,
                type="pipeline_definition",
                data=definition_data,
            )

        # Return the created record - construct with dict as LocalLabsRecord expects
        return PipelineDefinitionRecord(
            {
                "id": definition_id,
                "experiment": self.EXPERIMENT,
                "type": "pipeline_definition",
                "data": definition_data,
                "opportunity_id": self.opportunity_id,
                "organization_id": self.organization_id,
                "program_id": self.program_id,
            }
        )

    def update_definition(
        self,
        definition_id: int,
        name: str | None = None,
        description: str | None = None,
        schema: dict | None = None,
    ) -> PipelineDefinitionRecord | None:
        """Update a pipeline definition."""
        existing = self.get_definition(definition_id)
        if not existing:
            return None

        data = existing.data.copy()

        if name is not None:
            data["name"] = name
        if description is not None:
            data["description"] = description
        if schema is not None:
            data["schema"] = schema
            data["version"] = data.get("version", 1) + 1

        self.labs_api.update_record(
            definition_id,
            experiment=self.EXPERIMENT,
            type="pipeline_definition",
            data=data,
        )

        return PipelineDefinitionRecord(
            {
                "id": definition_id,
                "experiment": self.EXPERIMENT,
                "type": "pipeline_definition",
                "data": data,
                "opportunity_id": self.opportunity_id,
                "organization_id": self.organization_id,
                "program_id": self.program_id,
            }
        )

    # -------------------------------------------------------------------------
    # Render Code Methods
    # -------------------------------------------------------------------------

    def get_render_code(self, definition_id: int) -> PipelineRenderCodeRecord | None:
        """Get render code for a pipeline definition."""
        # First get the definition to find render_code_id
        definition = self.get_definition(definition_id)
        if not definition or not definition.render_code_id:
            return None

        record = self.labs_api.get_record_by_id(
            definition.render_code_id,
            experiment=self.EXPERIMENT,
            type="pipeline_render_code",
            model_class=PipelineRenderCodeRecord,
        )
        return record

    def save_render_code(self, definition_id: int, component_code: str) -> PipelineRenderCodeRecord:
        """Save or update render code for a pipeline definition."""
        definition = self.get_definition(definition_id)
        if not definition:
            raise ValueError(f"Pipeline definition {definition_id} not found")

        if definition.render_code_id:
            # Update existing
            existing = self.labs_api.get_record_by_id(
                definition.render_code_id,
                experiment=self.EXPERIMENT,
                type="pipeline_render_code",
            )
            if existing:
                data = existing.data.copy()
                data["component_code"] = component_code
                data["version"] = data.get("version", 1) + 1

                self.labs_api.update_record(
                    definition.render_code_id,
                    experiment=self.EXPERIMENT,
                    type="pipeline_render_code",
                    data=data,
                )

                return PipelineRenderCodeRecord(
                    {
                        "id": definition.render_code_id,
                        "experiment": self.EXPERIMENT,
                        "type": "pipeline_render_code",
                        "data": data,
                        "opportunity_id": self.opportunity_id,
                        "organization_id": self.organization_id,
                        "program_id": self.program_id,
                    }
                )

        # Create new render code record
        render_data = {
            "definition_id": definition_id,
            "component_code": component_code,
            "version": 1,
        }

        result = self.labs_api.create_record(
            experiment=self.EXPERIMENT,
            type="pipeline_render_code",
            data=render_data,
        )

        render_code_id = result.id

        # Update definition with render_code_id
        def_data = definition.data.copy()
        def_data["render_code_id"] = render_code_id
        self.labs_api.update_record(
            definition_id,
            experiment=self.EXPERIMENT,
            type="pipeline_definition",
            data=def_data,
        )

        return PipelineRenderCodeRecord(
            {
                "id": render_code_id,
                "experiment": self.EXPERIMENT,
                "type": "pipeline_render_code",
                "data": render_data,
                "opportunity_id": self.opportunity_id,
                "organization_id": self.organization_id,
                "program_id": self.program_id,
            }
        )

    # -------------------------------------------------------------------------
    # Chat History Methods
    # -------------------------------------------------------------------------

    def get_chat_history(self, definition_id: int) -> list[dict]:
        """Get chat history for a pipeline definition."""
        records = self.labs_api.get_records(
            experiment=self.EXPERIMENT,
            type="pipeline_chat_history",
            model_class=PipelineChatHistoryRecord,
        )

        for record in records:
            if record.data.get("definition_id") == definition_id:
                return record.data.get("messages", [])

        return []

    def add_chat_message(self, definition_id: int, role: str, content: str) -> None:
        """Add a message to chat history."""
        from datetime import datetime

        records = self.labs_api.get_records(
            experiment=self.EXPERIMENT,
            type="pipeline_chat_history",
            model_class=PipelineChatHistoryRecord,
        )

        existing_record = None
        for record in records:
            if record.data.get("definition_id") == definition_id:
                existing_record = record
                break

        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }

        if existing_record:
            # Update existing
            data = existing_record.data.copy()
            messages = data.get("messages", [])
            messages.append(message)
            data["messages"] = messages
            data["updated_at"] = datetime.now().isoformat()

            self.labs_api.update_record(
                existing_record.id,
                experiment=self.EXPERIMENT,
                type="pipeline_chat_history",
                data=data,
            )
        else:
            # Create new
            self.labs_api.create_record(
                experiment=self.EXPERIMENT,
                type="pipeline_chat_history",
                data={
                    "definition_id": definition_id,
                    "messages": [message],
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                },
            )

    def clear_chat_history(self, definition_id: int) -> None:
        """Clear chat history for a pipeline definition."""
        from datetime import datetime

        records = self.labs_api.get_records(
            experiment=self.EXPERIMENT,
            type="pipeline_chat_history",
            model_class=PipelineChatHistoryRecord,
        )

        for record in records:
            if record.data.get("definition_id") == definition_id:
                data = record.data.copy()
                data["messages"] = []
                data["updated_at"] = datetime.now().isoformat()

                self.labs_api.update_record(
                    record.id,
                    experiment=self.EXPERIMENT,
                    type="pipeline_chat_history",
                    data=data,
                )
                break

    # -------------------------------------------------------------------------
    # Pipeline Execution Helper
    # -------------------------------------------------------------------------

    def get_pipeline_config(self, definition_id: int) -> AnalysisPipelineConfig | None:
        """
        Get an AnalysisPipelineConfig for a pipeline definition.

        This converts the JSON schema to a usable config object.

        Args:
            definition_id: Pipeline definition ID

        Returns:
            AnalysisPipelineConfig or None if not found
        """
        definition = self.get_definition(definition_id)
        if not definition:
            return None

        schema = definition.schema
        if not schema:
            logger.warning(f"Pipeline {definition_id} has no schema")
            return None

        # Use definition ID as part of experiment name for unique caching
        experiment = f"custom_pipeline_{definition_id}"

        return json_to_pipeline_config(schema, experiment=experiment)
