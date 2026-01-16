"""
Workflow Agent for editing workflow definitions and UI via AI.

This agent allows users to describe changes to their workflow in natural language
and returns updated workflow definition and/or render code (React components).
"""

import json
import logging

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from commcare_connect.ai.types import UserDependencies

logger = logging.getLogger(__name__)

WORKFLOW_INSTRUCTIONS = """
You are an expert React developer helping users build and modify workflow UIs.

You can edit TWO things:
1. **Definition** - JSON config for the workflow (name, description, statuses, etc.)
2. **Render Code** - React/JSX code that renders the workflow UI

## Definition Structure
```json
{
    "name": "Workflow Name",
    "description": "What this workflow does",
    "version": 1,
    "statuses": [
        {"id": "pending", "label": "Pending", "color": "gray"},
        {"id": "approved", "label": "Approved", "color": "green"}
    ],
    "config": {
        "showSummaryCards": true,
        "showFilters": true
    }
}
```
Available status colors: gray, green, yellow, blue, red, purple, orange, pink

## Render Code Guidelines
The render code is a React functional component. It receives these props:
- `definition` - The workflow definition object
- `instance` - Current instance with `state` (contains `worker_states`, `period_start`, `period_end`)
- `workers` - Array of worker objects with `username`, `name`, `visit_count`, `last_active`
- `links` - Object with `auditUrl(params)` and `taskUrl(params)` functions for generating URLs
- `actions` - Object with async action handlers (see Actions section below)
- `onUpdateState` - Async function to save state changes

## Actions - Programmatic Operations
The `actions` prop provides handlers for creating tasks and initiating OCS chatbot sessions:

### Task Creation
```jsx
// Create a task for a worker
const result = await actions.createTask({
    username: worker.username,
    title: "Follow up required",
    description: "Review this worker's recent activity",
    priority: "high"  // "low", "medium", or "high"
});
// result: { success: boolean, task_id?: number, error?: string }
```

### OCS (Open Chat Studio) Integration
```jsx
// Check if OCS is connected
const status = await actions.checkOCSStatus();
// status: { connected: boolean, login_url?: string }

// List available chatbots
const bots = await actions.listOCSBots();
// bots: { success: boolean, bots?: [{id, name, version}], needs_oauth?: boolean }

// Create task AND initiate OCS session in one call
const result = await actions.createTaskWithOCS({
    username: worker.username,
    title: "AI Outreach",
    description: "Automated outreach via chatbot",
    priority: "medium",
    ocs: {
        experiment: selectedBotId,     // Bot ID from listOCSBots
        prompt_text: "Your instructions for the bot..."
    }
});
// result: { success, task_id, ocs?: { success, message, error } }
```

### Example: Bulk OCS Outreach
```jsx
function WorkflowUI({ definition, instance, workers, links, actions, onUpdateState }) {
    const [ocsConnected, setOcsConnected] = React.useState(false);
    const [bots, setBots] = React.useState([]);
    const [selectedBot, setSelectedBot] = React.useState('');
    const [prompt, setPrompt] = React.useState('');
    const [selectedWorkers, setSelectedWorkers] = React.useState([]);

    // Check OCS status on mount
    React.useEffect(() => {
        actions.checkOCSStatus().then(status => {
            setOcsConnected(status.connected);
            if (status.connected) {
                actions.listOCSBots().then(result => {
                    if (result.success) setBots(result.bots || []);
                });
            }
        });
    }, []);

    const handleBulkOutreach = async () => {
        for (const worker of selectedWorkers) {
            const result = await actions.createTaskWithOCS({
                username: worker.username,
                title: "AI Outreach: " + worker.name,
                ocs: { experiment: selectedBot, prompt_text: prompt }
            });

            // Update workflow state to track the task
            await onUpdateState({
                worker_states: {
                    ...instance.state?.worker_states,
                    [worker.username]: {
                        ...instance.state?.worker_states?.[worker.username],
                        task_id: result.task_id,
                        status: 'outreach_initiated'
                    }
                }
            });
        }
    };

    // ... rest of component
}
```

## Available CSS Classes (Tailwind)
Use standard Tailwind CSS classes for styling:
- Layout: flex, grid, space-y-4, gap-4, p-4, m-2
- Colors: bg-white, bg-gray-50, text-gray-900, text-blue-600
- Borders: border, rounded-lg, shadow-sm
- Typography: text-sm, text-xl, font-bold, font-medium

## When to Change What
- User asks about data/statuses/fields -> modify definition
- User asks about layout/display/UI -> modify render_code
- User asks about both -> modify both

## CRITICAL OUTPUT RULES
1. If you set render_code_changed=true, you MUST include the complete render_code string
2. If you set definition_changed=true, you MUST include the complete definition object
3. ALWAYS return the COMPLETE code, not partial snippets or descriptions
4. The render_code must be the entire file content, not just the changed parts
5. Never summarize code changes - always output the full working code
"""


class WorkflowEditResponse(BaseModel):
    """Response from workflow edit agent."""

    message: str = Field(description="Explanation of what was changed")
    definition: dict | None = Field(
        default=None, description="Updated workflow definition JSON (if definition was changed)"
    )
    definition_changed: bool = Field(default=False, description="Whether the definition was modified")
    render_code: str | None = Field(default=None, description="Updated React render code (if UI was changed)")
    render_code_changed: bool = Field(default=False, description="Whether the render code was modified")


def get_workflow_agent() -> Agent[UserDependencies, WorkflowEditResponse]:
    """Create and return the workflow editing agent."""

    agent = Agent(
        "anthropic:claude-sonnet-4-20250514",
        deps_type=UserDependencies,
        output_type=WorkflowEditResponse,
        instructions=WORKFLOW_INSTRUCTIONS,
        model_settings=ModelSettings(max_tokens=16384),
    )

    return agent


def get_workflow_agent_openai() -> Agent[UserDependencies, WorkflowEditResponse]:
    """Create and return the workflow editing agent using OpenAI."""

    agent = Agent(
        "openai:gpt-4o",
        deps_type=UserDependencies,
        output_type=WorkflowEditResponse,
        instructions=WORKFLOW_INSTRUCTIONS,
        model_settings=ModelSettings(max_tokens=16384),  # GPT-4o has lower limit
    )

    return agent


def build_workflow_prompt(
    user_prompt: str, current_definition: dict | None = None, current_render_code: str | None = None
) -> str:
    """
    Build the prompt for the workflow agent including current workflow context.

    Args:
        user_prompt: The user's request
        current_definition: The current workflow definition JSON
        current_render_code: The current React render code

    Returns:
        The full prompt to send to the agent
    """
    prompt_parts = []

    if current_definition:
        prompt_parts.append("## Current Workflow Definition")
        prompt_parts.append(f"```json\n{json.dumps(current_definition, indent=2)}\n```")
        prompt_parts.append("")

    if current_render_code:
        prompt_parts.append("## Current Render Code")
        prompt_parts.append(f"```jsx\n{current_render_code}\n```")
        prompt_parts.append("")

    prompt_parts.append(f"## User Request\n{user_prompt}")

    return "\n".join(prompt_parts)


# Default render code template for new workflows
DEFAULT_RENDER_CODE = """function WorkflowUI({ definition, instance, workers, links, actions, onUpdateState }) {
    const [sortBy, setSortBy] = React.useState('name');
    const [filterStatus, setFilterStatus] = React.useState('all');

    const statuses = definition.statuses || [];
    const workerStates = instance.state?.worker_states || {};
    const config = definition.config || {};

    // Calculate stats
    const stats = React.useMemo(() => {
        const counts = {};
        statuses.forEach(s => { counts[s.id] = 0; });
        workers.forEach(w => {
            const status = workerStates[w.username]?.status || 'pending';
            counts[status] = (counts[status] || 0) + 1;
        });
        return {
            total: workers.length,
            reviewed: workers.length - (counts['pending'] || 0),
            counts
        };
    }, [workers, workerStates, statuses]);

    // Filter workers
    const displayWorkers = React.useMemo(() => {
        let filtered = workers;
        if (filterStatus !== 'all') {
            filtered = workers.filter(w =>
                (workerStates[w.username]?.status || 'pending') === filterStatus
            );
        }
        return [...filtered].sort((a, b) => {
            if (sortBy === 'name') return (a.name || a.username).localeCompare(b.name || b.username);
            if (sortBy === 'visits') return b.visit_count - a.visit_count;
            return 0;
        });
    }, [workers, workerStates, filterStatus, sortBy]);

    const handleStatusChange = async (username, newStatus) => {
        await onUpdateState({
            worker_states: {
                ...workerStates,
                [username]: { ...workerStates[username], status: newStatus }
            }
        });
    };

    const getStatusColor = (statusId) => {
        const colorMap = {
            gray: 'bg-gray-100 text-gray-800',
            green: 'bg-green-100 text-green-800',
            yellow: 'bg-yellow-100 text-yellow-800',
            blue: 'bg-blue-100 text-blue-800',
            red: 'bg-red-100 text-red-800',
            purple: 'bg-purple-100 text-purple-800',
            orange: 'bg-orange-100 text-orange-800',
            pink: 'bg-pink-100 text-pink-800'
        };
        const status = statuses.find(s => s.id === statusId);
        return colorMap[status?.color] || colorMap.gray;
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="bg-white rounded-lg shadow-sm p-6">
                <div className="flex justify-between items-start">
                    <div>
                        <h1 className="text-2xl font-bold text-gray-900">{definition.name}</h1>
                        <p className="text-gray-600 mt-1">{definition.description}</p>
                    </div>
                    <div className="text-sm text-gray-500">
                        {instance.state?.period_start} - {instance.state?.period_end}
                    </div>
                </div>
            </div>

            {/* Summary Cards */}
            {config.showSummaryCards !== false && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="bg-white p-4 rounded-lg shadow-sm">
                        <div className="text-3xl font-bold text-gray-900">{stats.total}</div>
                        <div className="text-gray-600">Total Workers</div>
                    </div>
                    <div className="bg-green-50 p-4 rounded-lg shadow-sm border border-green-200">
                        <div className="text-3xl font-bold text-green-700">{stats.reviewed}</div>
                        <div className="text-gray-600">Reviewed</div>
                    </div>
                    {statuses.slice(0, 2).map(status => (
                        <div key={status.id} className={"p-4 rounded-lg shadow-sm " + getStatusColor(status.id)}>
                            <div className="text-2xl font-bold">{stats.counts[status.id] || 0}</div>
                            <div className="text-sm">{status.label}</div>
                        </div>
                    ))}
                </div>
            )}

            {/* Filters */}
            {config.showFilters !== false && (
                <div className="bg-white rounded-lg shadow-sm p-4">
                    <div className="flex flex-wrap gap-4 items-center">
                        <select
                            value={filterStatus}
                            onChange={e => setFilterStatus(e.target.value)}
                            className="border border-gray-300 rounded-md px-3 py-2 text-sm"
                        >
                            <option value="all">All Statuses</option>
                            {statuses.map(s => (
                                <option key={s.id} value={s.id}>{s.label}</option>
                            ))}
                        </select>
                        <select
                            value={sortBy}
                            onChange={e => setSortBy(e.target.value)}
                            className="border border-gray-300 rounded-md px-3 py-2 text-sm"
                        >
                            <option value="name">Sort by Name</option>
                            <option value="visits">Sort by Visits</option>
                        </select>
                        <div className="ml-auto text-sm text-gray-500">
                            Showing {displayWorkers.length} of {workers.length} workers
                        </div>
                    </div>
                </div>
            )}

            {/* Worker Table */}
            <div className="bg-white rounded-lg shadow-sm overflow-hidden">
                <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                        <tr>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Worker</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Visits</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Last Active</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                        </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                        {displayWorkers.map(worker => {
                            const currentStatus = workerStates[worker.username]?.status || 'pending';
                            return (
                                <tr key={worker.username} className="hover:bg-gray-50">
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <div className="font-medium text-gray-900">{worker.name || worker.username}</div>
                                        <div className="text-sm text-gray-500">{worker.username}</div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                        {worker.visit_count || 0}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                        {worker.last_active || 'Never'}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <select
                                            value={currentStatus}
                                            onChange={e => handleStatusChange(worker.username, e.target.value)}
                                            className="border rounded px-2 py-1 text-sm"
                                        >
                                            {statuses.map(s => (
                                                <option key={s.id} value={s.id}>{s.label}</option>
                                            ))}
                                        </select>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                                        <div className="flex gap-2">
                                            <a
                                                href={links.auditUrl({ username: worker.username, count: 5 })}
                                                className="text-blue-600 hover:text-blue-800"
                                            >
                                                Audit
                                            </a>
                                            <a
                                                href={links.taskUrl({ username: worker.username })}
                                                className="text-blue-600 hover:text-blue-800"
                                            >
                                                Task
                                            </a>
                                        </div>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
                {displayWorkers.length === 0 && (
                    <div className="px-6 py-12 text-center text-gray-500">
                        No workers match the current filter.
                    </div>
                )}
            </div>
        </div>
    );
}"""
