"""
Pipeline Agent for editing custom data pipeline schemas and visualizations via AI.

This agent allows users to describe changes to their data pipeline in natural language
and returns updated pipeline schema JSON and/or render code (React components).
"""

import json
import logging

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from commcare_connect.ai.types import UserDependencies

logger = logging.getLogger(__name__)

PIPELINE_INSTRUCTIONS = """
You are an expert data analyst helping users build and modify data extraction pipelines.

You can edit TWO things:
1. **Schema** - JSON config defining what data to extract from form submissions
2. **Render Code** - React/JSX code that visualizes the extracted data

## Schema Structure

The schema defines how to extract and transform data from CommCare form submissions.
Data is stored in `form_json` as nested JSON objects.

```json
{
    "name": "Pipeline Name",
    "description": "What this pipeline analyzes",
    "version": 1,
    "grouping_key": "username",
    "terminal_stage": "visit_level",
    "linking_field": "entity_id",
    "fields": [
        {
            "name": "field_name",
            "path": "form.path.to.field",
            "paths": ["form.path1", "form.path2"],
            "aggregation": "first",
            "transform": "float",
            "description": "Human readable description"
        }
    ],
    "histograms": [],
    "filters": {}
}
```

### Schema Fields Explained

- **grouping_key**: Field to group by ("username", "entity_id", "deliver_unit_id")
- **terminal_stage**:
  - "visit_level" - One row per form submission (visit)
  - "aggregated" - One row per FLW/user with aggregated stats
- **linking_field**: Field to link related visits (e.g., "entity_id" for beneficiary tracking)

### Field Configuration

Each field extracts data from form_json using JSONB paths:

```json
{
    "name": "weight",
    "path": "form.anthropometric.child_weight",
    "paths": ["form.path1", "form.path2"],  // Optional: try multiple paths
    "aggregation": "first",
    "transform": "kg_to_g",
    "description": "Child weight in grams",
    "default": null
}
```

**Aggregation Types** (for aggregated terminal_stage):
- "first" - First non-null value (by visit date)
- "last" - Last non-null value
- "sum" - Sum of values
- "avg" - Average of values
- "count" - Count of non-null values
- "min" / "max" - Minimum / maximum
- "list" - Array of all values
- "count_unique" - Count distinct values

**Transform Types** (applied to extracted values):
- "float" - Convert to decimal number
- "int" - Convert to integer
- "kg_to_g" - Multiply by 1000 (kilograms to grams)
- "date" - Parse as date string
- "string" - Convert to string
- null - No transformation

### Histogram Configuration

Histograms create binned distributions for numeric fields:

```json
{
    "name": "weight_distribution",
    "path": "form.anthropometric.child_weight",
    "lower_bound": 1000,
    "upper_bound": 5000,
    "num_bins": 8,
    "bin_name_prefix": "weight",
    "transform": "kg_to_g",
    "description": "Weight distribution in grams"
}
```

### Common Form JSON Paths

Form data is nested under `form_json`:
- `form.case.@case_id` - Case ID
- `form.case.update.field_name` - Case update fields
- `form.meta.timeEnd` - Form submission time
- `form.meta.username` - Submitting user
- `form.question_group.question_id` - Form questions

## Render Code Guidelines

The render code is a React functional component that receives pipeline results.

### Props

```jsx
function PipelineUI({ data, definition, onRefresh }) {
    // data: { rows: [...], metadata: {...}, from_cache: boolean }
    // definition: { name, description, schema, ... }
    // onRefresh: () => void - Trigger data reload
}
```

### Data Structure (Visit Level)

```javascript
data.rows = [
    {
        username: "flw123",
        visit_date: "2024-01-15",
        status: "approved",
        flagged: false,
        entity_id: "case123",
        entity_name: "John Doe",
        computed: {
            weight: 2500,
            height: 45.5,
            // ... other extracted fields
        }
    },
    // ... more rows
]
```

### Data Structure (Aggregated)

```javascript
data.rows = [
    {
        username: "flw123",
        total_visits: 45,
        approved_visits: 40,
        pending_visits: 3,
        rejected_visits: 2,
        flagged_visits: 1,
        first_visit_date: "2024-01-01",
        last_visit_date: "2024-03-15",
        custom_fields: {
            avg_weight: 2750,
            total_muac_measurements: 42,
            // ... other aggregated fields
        }
    },
    // ... more FLWs
]
```

### Example: Simple Table

```jsx
function PipelineUI({ data, definition, onRefresh }) {
    const rows = data?.rows || [];
    const schema = definition?.schema || {};

    return (
        <div className="space-y-4">
            <div className="flex justify-between items-center">
                <h2 className="text-xl font-bold">{definition?.name}</h2>
                <button
                    onClick={onRefresh}
                    className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
                >
                    Refresh
                </button>
            </div>

            <div className="bg-white rounded-lg shadow overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                        <tr>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                User
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                Date
                            </th>
                            {schema.fields?.map(field => (
                                <th key={field.name} className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                    {field.description || field.name}
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200">
                        {rows.map((row, idx) => (
                            <tr key={idx} className="hover:bg-gray-50">
                                <td className="px-6 py-4 text-sm">{row.username}</td>
                                <td className="px-6 py-4 text-sm">{row.visit_date}</td>
                                {schema.fields?.map(field => (
                                    <td key={field.name} className="px-6 py-4 text-sm">
                                        {row.computed?.[field.name] ?? '-'}
                                    </td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            <div className="text-sm text-gray-500">
                {rows.length} rows {data?.from_cache ? '(cached)' : ''}
            </div>
        </div>
    );
}
```

## Available CSS Classes (Tailwind)

Use standard Tailwind CSS classes:
- Layout: flex, grid, space-y-4, gap-4, p-4, m-2
- Colors: bg-white, bg-gray-50, text-gray-900, text-blue-600
- Borders: border, rounded-lg, shadow-sm
- Typography: text-sm, text-xl, font-bold, font-medium

## When to Change What

- User asks about data extraction/fields/aggregation -> modify schema
- User asks about layout/display/charts -> modify render_code
- User asks about both -> modify both

## CRITICAL OUTPUT RULES

1. If you set render_code_changed=true, you MUST include the complete render_code string
2. If you set schema_changed=true, you MUST include the complete schema object
3. ALWAYS return the COMPLETE code, not partial snippets or descriptions
4. The render_code must be the entire component, not just the changed parts
5. Never summarize code changes - always output the full working code
"""


class PipelineEditResponse(BaseModel):
    """Response from pipeline edit agent."""

    message: str = Field(description="Explanation of what was changed")
    schema: dict | None = Field(default=None, description="Updated pipeline schema JSON (if schema was changed)")
    schema_changed: bool = Field(default=False, description="Whether the schema was modified")
    render_code: str | None = Field(default=None, description="Updated React render code (if UI was changed)")
    render_code_changed: bool = Field(default=False, description="Whether the render code was modified")


def get_pipeline_agent() -> Agent[UserDependencies, PipelineEditResponse]:
    """Create and return the pipeline editing agent."""

    agent = Agent(
        "anthropic:claude-sonnet-4-20250514",
        deps_type=UserDependencies,
        output_type=PipelineEditResponse,
        instructions=PIPELINE_INSTRUCTIONS,
        model_settings=ModelSettings(max_tokens=16384),
    )

    return agent


def get_pipeline_agent_openai() -> Agent[UserDependencies, PipelineEditResponse]:
    """Create and return the pipeline editing agent using OpenAI."""

    agent = Agent(
        "openai:gpt-4o",
        deps_type=UserDependencies,
        output_type=PipelineEditResponse,
        instructions=PIPELINE_INSTRUCTIONS,
        model_settings=ModelSettings(max_tokens=16384),
    )

    return agent


def build_pipeline_prompt(
    user_prompt: str, current_schema: dict | None = None, current_render_code: str | None = None
) -> str:
    """
    Build the prompt for the pipeline agent including current pipeline context.

    Args:
        user_prompt: The user's request
        current_schema: The current pipeline schema JSON
        current_render_code: The current React render code

    Returns:
        The full prompt to send to the agent
    """
    prompt_parts = []

    if current_schema:
        prompt_parts.append("## Current Pipeline Schema")
        prompt_parts.append(f"```json\n{json.dumps(current_schema, indent=2)}\n```")
        prompt_parts.append("")

    if current_render_code:
        prompt_parts.append("## Current Render Code")
        prompt_parts.append(f"```jsx\n{current_render_code}\n```")
        prompt_parts.append("")

    prompt_parts.append(f"## User Request\n{user_prompt}")

    return "\n".join(prompt_parts)


# Default render code template for new pipelines
DEFAULT_RENDER_CODE = """function PipelineUI({ data, definition, onRefresh }) {
    const rows = data?.rows || [];
    const schema = definition?.schema || {};
    const fields = schema.fields || [];

    // Simple stats
    const totalRows = rows.length;
    const fromCache = data?.from_cache;

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="bg-white rounded-lg shadow-sm p-6">
                <div className="flex justify-between items-start">
                    <div>
                        <h1 className="text-2xl font-bold text-gray-900">
                            {definition?.name || 'Pipeline Results'}
                        </h1>
                        <p className="text-gray-600 mt-1">
                            {definition?.description || 'Data analysis results'}
                        </p>
                    </div>
                    <div className="flex items-center gap-2">
                        {fromCache && (
                            <span className="px-3 py-1 bg-green-100 text-green-800 rounded text-sm">
                                Cached
                            </span>
                        )}
                        <button
                            onClick={onRefresh}
                            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                        >
                            <i className="fa-solid fa-arrows-rotate mr-2"></i>
                            Refresh
                        </button>
                    </div>
                </div>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-3 gap-4">
                <div className="bg-white rounded-lg shadow-sm p-4">
                    <div className="text-sm text-gray-500">Total Rows</div>
                    <div className="text-2xl font-bold text-gray-900">{totalRows}</div>
                </div>
                <div className="bg-white rounded-lg shadow-sm p-4">
                    <div className="text-sm text-gray-500">Fields</div>
                    <div className="text-2xl font-bold text-gray-900">{fields.length}</div>
                </div>
                <div className="bg-white rounded-lg shadow-sm p-4">
                    <div className="text-sm text-gray-500">Stage</div>
                    <div className="text-2xl font-bold text-gray-900">
                        {schema.terminal_stage === 'aggregated' ? 'Aggregated' : 'Visit Level'}
                    </div>
                </div>
            </div>

            {/* Data Table */}
            <div className="bg-white rounded-lg shadow-sm overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                    User
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                    Date
                                </th>
                                {fields.map(field => (
                                    <th
                                        key={field.name}
                                        className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase"
                                        title={field.description}
                                    >
                                        {field.name}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {rows.slice(0, 100).map((row, idx) => (
                                <tr key={idx} className="hover:bg-gray-50">
                                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                                        {row.username}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                        {row.visit_date || row.last_visit_date || '-'}
                                    </td>
                                    {fields.map(field => (
                                        <td key={field.name} className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                            {formatValue(row.computed?.[field.name] ?? row.custom_fields?.[field.name])}
                                        </td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
                {rows.length > 100 && (
                    <div className="px-6 py-3 bg-gray-50 text-sm text-gray-500">
                        Showing first 100 of {rows.length} rows
                    </div>
                )}
            </div>
        </div>
    );
}

function formatValue(val) {
    if (val === null || val === undefined) return '-';
    if (typeof val === 'number') return val.toLocaleString();
    if (Array.isArray(val)) return val.length + ' items';
    return String(val);
}
"""
