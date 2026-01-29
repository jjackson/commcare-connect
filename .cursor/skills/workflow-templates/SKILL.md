---
name: workflow-templates
description: Create and modify workflow templates for CommCare Connect. Use when the user wants to create a new workflow template, add a workflow type, modify existing workflow UI code, or asks about workflow render code patterns.
---

# Creating Workflow Templates

Workflow templates define reusable workflow types with UI render code. Templates are stored as individual Python files in `commcare_connect/workflow/templates/` and auto-discovered by the registry.

## Quick Start

To add a new workflow template:

1. Create a new file in `commcare_connect/workflow/templates/` (e.g., `my_template.py`)
2. Export a `TEMPLATE` dict with required fields
3. Done - UI automatically loads templates from API

## File Structure

```
workflow/
  templates/
    __init__.py              # Auto-discovery registry
    base.py                  # Type definitions
    performance_review.py    # Individual template
    ocs_outreach.py
    kmc_scale_validation.py
    audit_with_ai_review.py
```

## Template File Structure

Each template file should export a `TEMPLATE` dict:

```python
"""
My Template Workflow.

Brief description of what this workflow does.
"""

# Optional: Pipeline Schema for data extraction
PIPELINE_SCHEMA = {
    "name": "...",
    "description": "...",
    "version": 1,
    "grouping_key": "username",
    "terminal_stage": "visit_level" | "aggregated",
    "fields": [...],
}

# Workflow Definition
DEFINITION = {
    "name": "Human-readable Name",
    "description": "What this workflow does",
    "version": 1,
    "templateType": "my_template_key",
    "statuses": [
        {"id": "pending", "label": "Pending", "color": "gray"},
        {"id": "completed", "label": "Done", "color": "green"},
    ],
    "config": {},
    "pipeline_sources": [],
}

# React Component as string (JSX)
RENDER_CODE = """function WorkflowUI({ definition, instance, workers, pipelines, links, actions, onUpdateState }) {
    // React component code
    return (<div>...</div>);
}"""

# REQUIRED: Template export dict
TEMPLATE = {
    "key": "my_template_key",           # Unique identifier
    "name": "Human-readable Name",
    "description": "Brief description",
    "icon": "fa-cog",                   # Font Awesome icon class
    "color": "blue",                    # Tailwind color: green, blue, purple, orange, red, gray
    "definition": DEFINITION,
    "render_code": RENDER_CODE,
    "pipeline_schema": PIPELINE_SCHEMA, # or None if no pipeline
}
```

## Render Code Props

The `WorkflowUI` component receives:

| Prop            | Type     | Description                                            |
| --------------- | -------- | ------------------------------------------------------ |
| `definition`    | object   | Workflow definition (statuses, config, etc.)           |
| `instance`      | object   | Current run instance with `id`, `state`                |
| `workers`       | array    | List of workers with `username`, `name`, pipeline data |
| `pipelines`     | object   | Pipeline data by alias (e.g., `pipelines.visits.rows`) |
| `links`         | object   | URL builders: `auditUrl()`, `taskUrl()`                |
| `actions`       | object   | Action handlers (see below)                            |
| `onUpdateState` | function | Persist state: `await onUpdateState({ key: value })`   |

## Available Actions

```javascript
// Audit Actions
await actions.createAudit({
  opportunities: [{ id: 123, name: 'Opp Name' }],
  criteria: { audit_type: 'date_range', startDate: '...', endDate: '...' },
  workflow_run_id: instance.id,
  ai_agent_id: 'scale_validation', // optional
});

await actions.getAuditStatus(taskId);
const cleanup = actions.streamAuditProgress(
  taskId,
  onProgress,
  onComplete,
  onError,
);

// Job Actions (for pipeline processing)
await actions.startJob(instanceId, {
  job_type: 'scale_validation',
  params: {},
  records: [],
});
const cleanup = actions.streamJobProgress(
  taskId,
  onProgress,
  onItem,
  onComplete,
  onError,
  onCancel,
);
await actions.cancelJob(taskId, instanceId);

// OCS Actions
await actions.checkOCSStatus();
await actions.listOCSBots();
await actions.createTaskWithOCS({
  username,
  title,
  description,
  ocs: { experiment, prompt_text },
});
```

## State Management

Persist workflow state using `onUpdateState`:

```javascript
// Save to instance.state
await onUpdateState({
    worker_states: { [username]: { status: "reviewed" } },
    audit_results: { sessions: [...] },
});

// Read from instance.state
const workerStates = instance.state?.worker_states || {};
```

## Common Patterns

### Loading State with SSE Pipeline

```javascript
const [loading, setLoading] = React.useState(true);
const [data, setData] = React.useState([]);

React.useEffect(() => {
  const url = window.WORKFLOW_API_ENDPOINTS?.streamPipelineData;
  const eventSource = new EventSource(url);
  eventSource.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.complete) {
      setData(msg.data.pipelines?.visits?.rows || []);
      setLoading(false);
      eventSource.close();
    }
  };
  return () => eventSource.close();
}, []);
```

### Progress Tracking

```javascript
const [progress, setProgress] = React.useState(null);
const [isRunning, setIsRunning] = React.useState(false);

const handleStart = async () => {
    setIsRunning(true);
    const result = await actions.createAudit({ ... });
    if (result.success) {
        actions.streamAuditProgress(
            result.task_id,
            (p) => setProgress(p),
            (final) => { setIsRunning(false); setProgress({ status: 'completed', ...final }); },
            (err) => { setIsRunning(false); setProgress({ status: 'failed', error: err }); }
        );
    }
};
```

### Status Badges

```javascript
const getStatusBadge = (statusId) => {
  const colors = {
    gray: 'bg-gray-100 text-gray-800',
    green: 'bg-green-100 text-green-800',
    yellow: 'bg-yellow-100 text-yellow-800',
    red: 'bg-red-100 text-red-800',
    blue: 'bg-blue-100 text-blue-800',
    purple: 'bg-purple-100 text-purple-800',
  };
  const status = definition.statuses.find((s) => s.id === statusId);
  return colors[status?.color] || colors.gray;
};
```

## Existing Templates

| Key                    | File                      | Purpose                                 | Has Pipeline |
| ---------------------- | ------------------------- | --------------------------------------- | ------------ |
| `performance_review`   | `performance_review.py`   | Review worker performance, create tasks | Yes          |
| `ocs_outreach`         | `ocs_outreach.py`         | Bulk AI chatbot outreach                | No           |
| `kmc_scale_validation` | `kmc_scale_validation.py` | ML validation of scale images           | Yes          |
| `audit_with_ai_review` | `audit_with_ai_review.py` | Create audits with AI pre-validation    | No           |

## Files Reference

- **Template files**: `commcare_connect/workflow/templates/` (individual .py files)
- **Registry**: `commcare_connect/workflow/templates/__init__.py`
- **UI list**: `commcare_connect/templates/workflow/list.html`
- **Action handlers**: `commcare_connect/static/js/workflow-runner.tsx`
- **TypeScript types**: `components/workflow/types.ts`
- **View handlers**: `commcare_connect/workflow/views.py`
