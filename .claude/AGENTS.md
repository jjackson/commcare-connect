# Agent Guidelines for CommCare Connect Labs

## Labs Architecture Overview

Labs is a **separate Django deployment** that communicates with production CommCare Connect entirely via OAuth and HTTP APIs. It has no direct database access to production data.

**Key principles:**

- **OAuth session auth** — no Django User model. `LabsUser` is transient (created from session on each request, never saved to DB)
- **All data via API** — `LabsRecordAPIClient` calls `/export/labs_record/` on production for all CRUD operations
- **Proxy models** — `LocalLabsRecord` subclasses provide typed access to JSON data from the API. They cannot be saved locally.
- **Context middleware** — `request.labs_context` provides `opportunity_id`, `program_id`, `organization_id` on every request

**Three middleware layers** (configured in `config/settings/local.py`):

1. `LabsAuthenticationMiddleware` — populates `request.user` as `LabsUser` from session OAuth data
2. `LabsURLWhitelistMiddleware` — redirects non-labs URLs to `connect.dimagi.com`; whitelisted prefixes: `/ai/`, `/audit/`, `/coverage/`, `/tasks/`, `/solicitations/`, `/labs/`, `/custom_analysis/`
3. `LabsContextMiddleware` — extracts opportunity/program/organization from URL params and session into `request.labs_context`

**Important:** Use `config.settings.local` for local development, NOT `config.settings.labs`. The labs settings are for AWS deployment only. Local settings already have `IS_LABS_ENVIRONMENT = True`.

## Data Access Patterns

### Pattern A: LabsRecordAPIClient (The Correct Pattern for Labs)

All labs apps use `LabsRecordAPIClient` (`commcare_connect/labs/integrations/connect/api_client.py`) for data operations:

```
View receives request
  → Extracts OAuth token from request.session["labs_oauth"]["access_token"]
  → Extracts context from request.labs_context
  → Creates AppDataAccess(request=request)
    → DataAccess creates LabsRecordAPIClient(access_token, opportunity_id, ...)
      → Client calls GET/POST/PUT/DELETE on /export/labs_record/
    → DataAccess casts responses to proxy models (LocalLabsRecord subclasses)
  → View renders template with proxy model lists (NOT Django QuerySets)
```

Each app wraps the client in a `data_access.py` with domain-specific methods. See `commcare_connect/tasks/data_access.py` for the simplest example.

### Pattern B: Django ORM (Legacy — Do Not Use for Labs)

The `opportunity/`, `organization/`, `program/`, `users/` apps contain Django ORM models from the production CommCare Connect codebase. In the labs environment, these tables are empty. **Never query these models expecting production data.**

The only local Django models used by labs are cache tables in `commcare_connect/labs/analysis/backends/sql/models.py` (`RawVisitCache`, `ComputedVisitCache`, `ComputedFLWCache`).

### When to Use Which

- **Need to store/retrieve domain data?** → `LabsRecordAPIClient` via `data_access.py`
- **Need visit/user CSV data for analysis?** → `AnalysisPipeline` (handles caching transparently)
- **Need opportunity/organization metadata?** → HTTP call to `/export/opp_org_program_list/`
- **Need CommCare HQ case data?** → CommCare HQ OAuth + Case API v2 (see `coverage/` app)
- **Need AI integration?** → Add agent in `ai/agents/`, SSE streaming via `AIStreamView`
- **Need async processing?** → Celery task in `{app}/tasks.py`, SSE for progress

## Data Export API Endpoints

Base URL: `settings.CONNECT_PRODUCTION_URL` (production: `https://connect.dimagi.com`)

**Authentication:** OAuth Bearer token with `export` scope

### LabsRecord CRUD API

- `GET /export/labs_record/` — Query records. Params: `experiment`, `type`, `username`, `opportunity_id`, `organization_id`, `program_id`, `labs_record_id`, `public`, `data__<field>=<value>`
- `POST /export/labs_record/` — Create or update record. Body: `{experiment, type, data, username, opportunity_id, organization_id, program_id, labs_record_id, public}`
- `DELETE /export/labs_record/` — Delete record. Params: `id`

### Metadata APIs

- `GET /export/opp_org_program_list/` — Lists opportunities, organizations, programs (JSON)
- `GET /export/opportunity/<opp_id>/` — Full opportunity details including `learn_app`, `deliver_app`

### CSV Stream APIs (Opportunity-scoped)

- `/export/opportunity/<opp_id>/user_data/`
- `/export/opportunity/<opp_id>/user_visits/`
- `/export/opportunity/<opp_id>/completed_works/`
- `/export/opportunity/<opp_id>/payment/`
- `/export/opportunity/<opp_id>/invoice/`
- `/export/opportunity/<opp_id>/assessment/`
- `/export/opportunity/<opp_id>/completed_module/`

## How Each Labs App Works

### `audit/` — Quality Assurance Review

> See also: [`commcare_connect/audit/README.md`](../commcare_connect/audit/README.md) for data model details and testing guidance.

Structured audits of FLW visits with AI-powered reviews.

- **DataAccess:** `AuditDataAccess` in `audit/data_access.py`
- **Proxy models:** `AuditSessionRecord` (experiment=`"audit"`, type=`"AuditSession"`)
- **Key views:** Audit list (`/audit/`), creation wizard (`/audit/create/`), bulk assessment (`/audit/<pk>/bulk/`)
- **Async:** Celery task for audit creation with SSE progress streaming
- **AI review:** `audit/ai_review.py` runs validation agents on individual visits
- **Uses:** `AnalysisPipeline` for visit data filtering

#### Audit API Contracts (used by workflow templates)

**Create async** `POST /audit/api/audit/create-async/`
```json
{ "opportunities": [{"id": 1, "name": "..."}], "criteria": {
    "audit_type": "date_range|last_n_per_opp",
    "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD",
    "count_per_opp": 10, "sample_percentage": 100,
    "related_fields": [{"image_path": "...", "filter_by_image": true}]
  }, "workflow_run_id": 123 }
```
Response: `{"success": true, "task_id": "..."}`. Task result has `{"sessions": [{"id", "title", "visits", "images"}]}`.

**Bulk data** `GET /audit/api/<session_id>/bulk-data/`
Response: `{"assessments": [{id, visit_id, blob_id, question_id, opportunity_id, filename, result, notes, status, image_url, visit_date, entity_name, username, related_fields, ai_result, ai_notes}], ...}`
Note: `opportunity_id` = `session.opportunity_id` (same for all assessments in a session). `status` = `"pass"|"fail"|"pending"`.

**Save progress** `POST /audit/api/<session_id>/save/`
FormData: `visit_results` = JSON string of `{visit_id: {assessments: {blob_id: {question_id, result, notes, ai_result, ai_notes}}}}`

**Complete** `POST /audit/api/<session_id>/complete/`
FormData: `overall_result` (`"pass"|"fail"`), `notes`, `kpi_notes` (can be `""`), `visit_results` (same shape as save).

**AI Review** `POST /audit/api/<session_id>/ai-review/`
JSON body (NOT FormData): `{"assessments": [{"visit_id", "blob_id", "reading"}], "agent_id": "scale_validation", "opportunity_id": <int>}`
Response: `{"results": [{"visit_id", "blob_id", "ai_result": "match|no_match|error", "ai_notes": "..."}]}`
Note: `opportunity_id` is **required**. Use `a.opportunity_id` from the assessment object (not `selected_opps[0].id`).

**Opp search** `GET /audit/api/opportunities/search/?q=<query>`
Response: `{"opportunities": [{"id", "name"}]}`

**Workflow sessions** `GET /audit/api/workflow/<workflow_run_id>/sessions/`
Response: `{"sessions": [{"id", ...}]}` — fallback for session_id discovery after async creation.

### `tasks/` — Task Management

> See also: [`commcare_connect/tasks/README.md`](../commcare_connect/tasks/README.md) for data model details and testing guidance.

Task tracking for FLW follow-ups with timeline, comments, and AI assistant.

- **DataAccess:** `TaskDataAccess` in `tasks/data_access.py` (simplest example of the pattern)
- **Proxy models:** `TaskRecord` (experiment=`"tasks"`, type=`"Task"`)
- **Key views:** Task list (`/tasks/`), create/edit (`/tasks/new/`, `/tasks/<id>/edit/`)
- **OCS integration:** Tasks can trigger Open Chat Studio bots and save transcripts
- **Cross-app:** Tasks can reference audit sessions via `audit_session_id` in task data

### `workflow/` — Configurable Workflow Engine

> See also: [`commcare_connect/workflow/README.md`](../commcare_connect/workflow/README.md) for data model details and testing guidance.

Data-driven workflows with custom React UIs and pipeline integration.

- **DataAccess:** `WorkflowDataAccess`, `PipelineDataAccess` (both extend `BaseDataAccess`) in `workflow/data_access.py`
- **Proxy models:** `WorkflowDefinitionRecord`, `WorkflowRenderCodeRecord`, `WorkflowRunRecord`, `WorkflowChatHistoryRecord`, `PipelineDefinitionRecord` (experiment=`"workflow"` / `"pipeline"`)
- **Key views:** Workflow list (`/workflow/`), definition view, run view
- **Templates:** Predefined workflow templates in `workflow/templates/` (audit_with_ai_review, bulk_image_audit, mbw_monitoring_v2, performance_review, ocs_outreach)
- **Render code:** React components stored as LabsRecords, rendered dynamically in workflow runner
- **Cross-app:** Can create audit sessions and tasks from workflow actions

#### Workflow Template Anatomy

Each template is a Python file in `workflow/templates/` that exports three dicts:

```python
DEFINITION = {
    "name": str, "description": str, "version": 1,
    "templateType": str,         # must match TEMPLATE["key"]
    "statuses": [...],           # list of {id, label, color}
    "config": {...},             # e.g. {"showSummaryCards": True}
    "pipeline_sources": [],
}

RENDER_CODE = """function WorkflowUI({ definition, instance, workers,
    pipelines, links, actions, onUpdateState }) {
    // Full React JSX component — Babel standalone transpiles in-browser, no build step
    // Inner components defined as const arrows INSIDE WorkflowUI to close over parent state
    // Phase router at bottom: {phase === 'foo' && <FooPhase />}
}"""

TEMPLATE = {
    "key": str,           # e.g. "bulk_image_audit" — unique, used for lookup
    "name": str,
    "description": str,
    "icon": str,          # Font Awesome class e.g. "fa-images"
    "color": str,         # Tailwind color e.g. "blue"
    "definition": DEFINITION,
    "render_code": RENDER_CODE,
    "pipeline_schema": None,  # or dict for single pipeline; use "pipeline_schemas" list for multi
}
```

**Registration:** `__init__.py` auto-discovers via `pkgutil.iter_modules`. Also has explicit re-exports at the bottom — **add new templates to both the `from . import` line and `__all__`**.

**JSX-in-Python rules:**
- Cannot use `"""` inside `RENDER_CODE` (Python string delimiter conflict)
- Inner components must be defined BEFORE they are used (no hoisting)
- State for child components is hoisted to outer `WorkflowUI` so it persists across re-renders
- `onUpdateState(patch)` PATCH-merges into `run.data.state` on the server
- Workflow props: `{ definition, instance, workers, pipelines, links, actions, onUpdateState }`
- `actions.createAudit(payload)` → `POST /audit/api/audit/create-async/`
- `actions.streamAuditProgress(task_id, onProgress, onComplete, onError)` → SSE stream
- `actions.cancelAudit(task_id)` → cancel endpoint

### `ai/` — AI Agent Integration

> See also: [`commcare_connect/ai/README.md`](../commcare_connect/ai/README.md) for data model details and testing guidance.

SSE streaming endpoints for AI-assisted editing using pydantic-ai agents.

- **No data_access.py** — agents call into other apps' DataAccess classes via tool functions
- **Agents:** `workflow_agent.py`, `pipeline_agent.py`, `solicitation_agent.py`, `coding_agent.py` in `ai/agents/`
- **Key view:** `AIStreamView` at `/ai/stream/` (POST → SSE streaming)
- **Tool calls:** Agents modify workflow definitions, render code, pipeline schemas via WorkflowDataAccess/PipelineDataAccess
- **Models:** Claude Sonnet/Opus or GPT via pydantic-ai

### `solicitations/` — RFP Management

> See also: [`commcare_connect/solicitations/README.md`](../commcare_connect/solicitations/README.md) for data model details and testing guidance.

Solicitations (requests for proposals), responses, and reviews.

- **DataAccess:** `SolicitationDataAccess` in `solicitations/data_access.py`
- **Proxy models:** `SolicitationRecord`, `ResponseRecord`, `ReviewRecord`, `DeliveryTypeDescriptionRecord`, `OppOrgEnrichmentRecord` (experiment=`"solicitations"`)
- **Scoping:** Uses `program_id` and `organization_id` (NOT `opportunity_id`)
- **Key views:** Solicitation list, create, respond, review
- **Standalone:** No cross-app dependencies (except AI agent integration)

### `coverage/` — Delivery Unit Mapping

Interactive map visualization of FLW coverage.

- **Different pattern:** Uses CommCare HQ OAuth (separate from Connect OAuth) + Case API v2
- **Models:** Dataclasses (`LocalUserVisit`, `DeliveryUnit`), NOT LabsRecord proxies
- **DataAccess:** `CoverageDataAccess` fetches from CommCare HQ, not Connect
- **Key views:** Map view (`/coverage/map/`), SSE stream for GeoJSON loading
- **Standalone:** No cross-app dependencies

### `labs/` — Core Infrastructure

Foundation layer used by all other apps.

- **Key files:**
  - `models.py` — `LabsUser`, `LocalLabsRecord` base classes
  - `middleware.py` — Authentication, URL whitelist, context middleware
  - `context.py` — Context extraction and session management
  - `view_mixins.py` — `AsyncLoadingViewMixin`, `AsyncDataViewMixin`
  - `integrations/connect/api_client.py` — `LabsRecordAPIClient`
  - `integrations/connect/oauth.py` — `introspect_token()`, `fetch_user_organization_data()`
  - `integrations/connect/oauth_views.py` — OAuth flow (login, callback, logout)
  - `analysis/` — Analysis pipeline (SQL backend with PostgreSQL cache tables)
  - `explorer/` — LabsRecord data explorer UI
  - `admin_boundaries/` — Geographic boundary data (PostGIS)

## Cross-App Connections

```
Workflow ──imports──→ AuditDataAccess (creates audits from workflow actions)
Workflow ──imports──→ TaskDataAccess (creates tasks from workflow actions)
AI ──────imports──→ WorkflowDataAccess (agents modify workflow definitions)
AI ──────imports──→ SolicitationDataAccess (solicitation agent)
Audit ←──references── Tasks (tasks store audit_session_id)
All apps ──depend──→ labs/ (API client, models, middleware)
Coverage ──────────→ CommCare HQ (separate OAuth, no Connect dependency)
```

## Key Files Quick Reference

| File                                                       | Purpose                                            |
| ---------------------------------------------------------- | -------------------------------------------------- |
| `commcare_connect/labs/integrations/connect/api_client.py` | Core `LabsRecordAPIClient`                         |
| `commcare_connect/labs/models.py`                          | `LabsUser`, `LocalLabsRecord` base classes         |
| `commcare_connect/labs/middleware.py`                      | Auth, URL whitelist, context middleware            |
| `commcare_connect/labs/context.py`                         | Context extraction and session management          |
| `commcare_connect/labs/view_mixins.py`                     | Base view mixins for labs views                    |
| `commcare_connect/labs/LABS_GUIDE.md`                      | Detailed patterns: OAuth, API client, proxy models |
| `commcare_connect/{app}/data_access.py`                    | Per-app data access layer                          |
| `commcare_connect/{app}/models.py`                         | Per-app proxy model definitions                    |
| `config/settings/local.py`                                 | Labs-enabled local development settings            |

## Common Mistakes to Avoid

1. **Using Django ORM models** (`Opportunity`, `User`, `Organization`) expecting production data — these tables are empty in labs
2. **Using `config.settings.labs` locally** — use `config.settings.local` instead. Labs settings are for AWS deployment.
3. **Calling `.save()` on `LabsUser` or `LocalLabsRecord`** — raises `NotImplementedError`. Use `LabsRecordAPIClient` for persistence.
4. **Forgetting the URL whitelist** — new app URL prefixes must be added to `WHITELISTED_PREFIXES` in `commcare_connect/labs/middleware.py`
5. **Using `user_id` with the production API** — production uses `username` as the primary identifier, not integer IDs
6. **Not handling API errors** — `LabsRecordAPIClient` raises `LabsAPIError` on HTTP failures; handle timeouts gracefully
7. **Creating Django migrations for production models** — don't modify `opportunity/`, `organization/`, etc. Labs data lives in production via the API.
8. **Hardcoding opportunity IDs** — use `request.labs_context` from middleware instead
