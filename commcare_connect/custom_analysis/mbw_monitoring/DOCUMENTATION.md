# MBW Monitoring Dashboard - Technical Documentation

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Workflow Integration](#workflow-integration)
4. [Data Flow](#data-flow)
5. [Three-Tab Dashboard](#three-tab-dashboard)
6. [Data Sources & APIs](#data-sources--apis)
7. [Pipeline Configuration](#pipeline-configuration)
8. [Follow-Up Rate Business Logic](#follow-up-rate-business-logic)
9. [Quality Metrics](#quality-metrics)
10. [Caching Strategy](#caching-strategy)
11. [Authentication & OAuth](#authentication--oauth)
12. [Frontend Architecture](#frontend-architecture)
13. [Features & Capabilities](#features--capabilities)
14. [Configuration](#configuration)
15. [File Reference](#file-reference)
16. [Key Field Paths](#key-field-paths)

---

## Overview

The MBW (Mother Baby Wellness) Monitoring Dashboard is a real-time performance monitoring tool for frontline health workers (FLWs) operating within the CommCare Connect ecosystem. It provides supervisors with a unified view of FLW performance across three dimensions:

- **Overview**: High-level per-FLW summary combining cases registered, follow-up rate, GS score, GPS metrics, and quality/fraud indicators
- **GPS Analysis**: Distance-based anomaly detection using Haversine calculations to flag suspicious travel patterns
- **Follow-Up Rate**: Visit completion tracking across 6 visit types (ANC, Postnatal, Week 1, Month 1, Month 3, Month 6) with per-mother drill-down, eligibility filtering, and grace period

The dashboard is designed for the **Labs environment** (a session-based, database-light variant of CommCare Connect) and loads all data in a single Server-Sent Events (SSE) connection, enabling real-time progress feedback during data loading.

### Key Design Decisions

- **Single SSE connection**: All three tabs load data from one streaming endpoint, avoiding redundant API calls
- **Client-side filtering**: Raw data is sent once; FLW and mother filtering happens entirely in the browser via Alpine.js
- **Two-layer caching**: Pipeline-level cache (Redis) for visit form data + Django cache for CCHQ form/case data
- **Tolerance-based cache validation**: Caches are accepted if they meet count, percentage, or time-based tolerance thresholds
- **No database writes**: All data is fetched from external APIs (Connect Production + CommCare HQ) and cached transiently
- **CCHQ Form API for metadata**: Registration forms and GS forms are fetched directly from CCHQ Form API v1 (not from cases), with dynamic xmlns discovery via the Application Structure API
- **Cross-app xmlns discovery**: GS forms live in a separate supervisor app; the system searches all apps in the domain to find the correct xmlns

---

## Architecture

### High-Level Architecture

```
User Browser
    |
    ├── GET /custom_analysis/mbw_monitoring/
    │   └── MBWMonitoringDashboardView (renders template with context)
    │
    ├── SSE /custom_analysis/mbw_monitoring/stream/
    │   └── MBWMonitoringStreamView (streams all data)
    │       ├── Step 1: AnalysisPipeline → Connect API (visit forms, 12 fields)
    │       ├── Step 2: Connect API → FLW names
    │       ├── Step 3: GPS analysis (Haversine distances)
    │       ├── Step 4a: CCHQ Form API → Registration forms (mother metadata)
    │       ├── Step 4b: CCHQ Form API → GS forms (Gold Standard scores)
    │       ├── Step 5: Follow-up metric aggregation (eligibility + grace period)
    │       └── Step 6: Overview metric computation (quality, GPS, follow-up, GS)
    │
    ├── GET /custom_analysis/mbw_monitoring/api/gps/<username>/
    │   └── MBWGPSDetailView (JSON drill-down for GPS visits)
    │
    ├── POST /custom_analysis/mbw_monitoring/api/session/save-flw-result/
    │   └── MBWSaveFlwResultView (save FLW assessment via workflow_adapter)
    │
    ├── POST /custom_analysis/mbw_monitoring/api/session/complete/
    │   └── MBWCompleteSessionView (mark monitoring run complete via workflow_adapter)
    │
    ├── POST /custom_analysis/mbw_monitoring/api/opportunity-flws/
    │   └── OpportunityFLWListAPIView (FLW list with audit history for workflow render_code)
    │
    └── POST /custom_analysis/mbw_monitoring/api/suspend-user/
        └── MBWSuspendUserView (retained but disabled — suspension is now a status label)
```

### Component Relationships

```
┌─────────────────┐     ┌─────────────────────┐     ┌──────────────────┐
│  Dashboard View  │────>│   Stream View (SSE)  │────>│ AnalysisPipeline │
│  (Template +     │     │  MBWMonitoringStream │     │  (Labs Framework)│
│   Context)       │     │       View           │     │                  │
└─────────────────┘     └────────┬─────────────┘     └────────┬─────────┘
                                 │                             │
                   ┌─────────────┼─────────────┐               │
                   │             │             │               │
             ┌─────▼──────┐ ┌───▼────────┐ ┌──▼─────────┐     │
             │ data_       │ │ followup_  │ │ gps_       │     │
             │ fetchers.py │ │ analysis.py│ │ analysis.py│     │
             │ (CCHQ forms │ │ (metrics,  │ │ (MBW core) │     │
             │  + cases)   │ │ quality)   │ │            │     │
             └─────────────┘ └────────────┘ └────────────┘     │
                   │                                           │
             ┌─────▼───────────────────────────────────────────▼───┐
             │              External APIs                          │
             │  ┌──────────────────┐  ┌─────────────────────────┐  │
             │  │  CommCare HQ     │  │  Connect Production     │  │
             │  │  Form API v1     │  │  API                    │  │
             │  │  Application API │  │  (visits, FLW names,    │  │
             │  │  (reg forms,     │  │   opportunity metadata) │  │
             │  │   GS forms)      │  │                         │  │
             │  └──────────────────┘  └─────────────────────────┘  │
             └─────────────────────────────────────────────────────┘
```

---

## Workflow Integration

### Overview

MBW monitoring sessions are managed through the **Workflow module** (`commcare_connect/workflow/`). The Workflow module provides session creation, listing, state persistence, and a React-based render_code UI for FLW selection. The MBW dashboard (`custom_analysis/mbw_monitoring/`) handles data visualization, analysis, and assessment actions.

This hybrid approach means:
- **Session lifecycle** (create, list, resume, complete) is handled by the Workflow module
- **Data analysis and visualization** (GPS, follow-up, overview tabs) is handled by the MBW dashboard
- **State persistence** (FLW results, session metadata) is stored in `WorkflowRunRecord.state` via `WorkflowDataAccess.update_run_state()`

### Workflow Template

The MBW Monitoring workflow template is defined in `commcare_connect/workflow/templates/mbw_monitoring.py` and auto-discovered by `__init__.py`'s `pkgutil` scan.

**Template structure:**

| Field | Value |
|-------|-------|
| `key` | `mbw_monitoring` |
| `templateType` | `mbw_monitoring` |
| `name` | MBW Monitoring |
| `icon` | `fa-chart-line` |
| `color` | `purple` |
| `pipeline_schema` | `None` (MBW has its own data pipeline) |
| `statuses` | `in_progress`, `completed` |
| `config` | `showSummaryCards: False`, `showFilters: False` |

**Render code** (React JSX, ~275 lines): Handles the pre-dashboard workflow UI:
1. **FLW Selection step**: Lists all FLWs for the opportunity with checkboxes, enriched with audit history indicators. FLW history is fetched via `POST /custom_analysis/mbw_monitoring/api/opportunity-flws/`.
2. **Metadata inputs**: Session title and optional tag.
3. **Launch Dashboard**: Saves selected FLWs to `WorkflowRunRecord.state.selected_flws` via `onUpdateState()`, then redirects to `/custom_analysis/mbw_monitoring/?run_id={instance.id}`.
4. **Resume view** (when `state.selected_flws` exists): Shows progress bar (assessed/total FLWs), result summary table, and "Continue in Dashboard" link.

**FLW Selection Table Columns:**

| Column | Source | Description |
|--------|--------|-------------|
| Checkbox | — | Select/deselect FLW for monitoring |
| FLW | `w.name`, `w.username` | Display name + username |
| Past Audits | `h.audit_count` | Count of past audit sessions (traditional + workflow) |
| Last Audit Date | `h.last_audit_date` | Date of most recent audit, formatted as "Mon DD, YYYY" |
| Last Result | `h.last_audit_result` | Color-coded badge: green (eligible), amber (probation), red (suspended) |
| Open Tasks | `h.open_task_count`, `h.latest_task_id`, `h.latest_task_date` | Count badge + clickable link to latest task (`/tasks/{id}/edit/`) with date |

### WorkflowMonitoringSession Adapter

The `WorkflowMonitoringSession` class in `workflow_adapter.py` wraps a `WorkflowRunRecord` to expose the same interface the dashboard expects. This adapter pattern allows the dashboard to work with workflow runs without changing its internal data access patterns.

**Adapted properties:**

| Property | Source in `WorkflowRunRecord` |
|----------|-------------------------------|
| `id` / `pk` | `run.id` |
| `title` | `state.title` (default: "MBW Monitoring") |
| `tag` | `state.tag` |
| `status` | `run.data.status` (default: "in_progress") |
| `overall_result` | `state.overall_result` |
| `session_type` | Always `"mbw_monitoring"` |
| `is_monitoring` | Always `True` |
| `opportunity_id` | `run.data.opportunity_id` or `run.opportunity_id` |
| `opportunity_name` | `state.opportunity_name` |
| `selected_flw_usernames` | `state.selected_flws` (list of usernames) |
| `flw_results` | `state.flw_results` (dict: `{username: {result, notes, assessed_by, assessed_at}}`) |

**Methods:**
- `get_flw_result(username)` → single FLW's result dict
- `get_monitoring_progress_stats()` → `{percentage, assessed, total}`
- `to_summary_dict()` → serializable summary for JSON context

### Helper Functions

Three helper functions in `workflow_adapter.py` handle state mutations:

**`load_monitoring_run(request, run_id)`**
- Loads a `WorkflowRunRecord` via `WorkflowDataAccess.get_run()`
- Validates it's a monitoring run (has `selected_flws` in state)
- Returns `WorkflowMonitoringSession` or `None`

**`save_flw_result(request, run_id, username, result, notes, assessed_by)`**
- Reads the current full `flw_results` dict from state
- Merges the new entry: `{result, notes, assessed_by, assessed_at}`
- Passes the **entire** `flw_results` dict to `update_run_state()` (required because `update_run_state()` does a **shallow merge** — `{**current_state, **new_state}` — so passing only the changed entry would overwrite all other FLW results)
- Returns updated `WorkflowMonitoringSession`

**`complete_monitoring_run(request, run_id, overall_result, notes)`**
- Sets `data.status = "completed"` and `state.overall_result`
- Uses `labs_api.update_record()` directly (no `complete_run()` method exists in `WorkflowDataAccess`)
- Returns updated `WorkflowMonitoringSession`

### FLW API (OpportunityFLWListAPIView)

The `flw_api.py` module provides a `POST /custom_analysis/mbw_monitoring/api/opportunity-flws/` endpoint used by the workflow template's render_code during FLW selection.

**Request:** `{"opportunities": ["765"]}`

**Response:** `{"success": true, "flws": [...], "total": N}`

Each FLW entry includes:
- `username`, `name`, `connect_id`, `opportunity_id`
- `history`: `{last_audit_date, last_audit_result, audit_count, open_task_count, latest_task_id, latest_task_date, latest_task_title}`

**Two-source history enrichment** (`_build_flw_history()`):
1. **Traditional audit sessions** (via `AuditDataAccess`): Reads `flw_username` and `overall_result` from past audit sessions
2. **Workflow monitoring runs** (via `WorkflowDataAccess`): Reads per-FLW results from `state.flw_results` across all workflow runs
3. **Open tasks** (via `TaskDataAccess`): Counts non-closed tasks per FLW

This dual-source approach ensures the FLW selection UI shows complete history regardless of whether past assessments were done via traditional audits or workflow-based monitoring.

### State Structure

The `WorkflowRunRecord.state` dict for an MBW monitoring session:

```json
{
  "selected_flws": ["flw001", "flw002", "flw003"],
  "title": "March 2025 Review",
  "tag": "monthly-review",
  "opportunity_name": "MBW Nigeria",
  "flw_results": {
    "flw001": {
      "result": "eligible_for_renewal",
      "notes": "Good performance across all metrics",
      "assessed_by": 42,
      "assessed_at": "2025-03-15T14:30:00+00:00"
    },
    "flw002": {
      "result": "probation",
      "notes": "Low follow-up rate, GPS anomalies detected",
      "assessed_by": 42,
      "assessed_at": "2025-03-15T14:35:00+00:00"
    }
  },
  "overall_result": "completed"
}
```

### Shallow Merge Caveat

`WorkflowDataAccess.update_run_state()` (at `workflow/data_access.py:655-681`) performs a **shallow merge**: `new_state = {**current_state, **updates}`. This means:
- Top-level keys are replaced entirely, not deep-merged
- When saving a single FLW result, the entire `flw_results` dict must be passed, not just the changed entry
- If only `{"flw_results": {"flw001": {...}}}` is passed, it overwrites the entire `flw_results` dict, losing all other FLWs
- The `save_flw_result()` helper reads the current full dict, merges the new entry, then passes the complete dict

### URL Parameter Compatibility

The dashboard accepts both `?run_id=X` (new workflow path) and `?session_id=X` (backward compatibility) in:
- `MBWMonitoringDashboardView.get_context_data()`
- `MBWMonitoringStreamView.stream_data()`

Both resolve to `load_monitoring_run()` which loads from the Workflow module.

### User Flow

```
1. User navigates to /labs/workflow/
2. Clicks "Create Workflow" → selects "MBW Monitoring" template
3. Workflow Run page renders the RENDER_CODE (React JSX)
4. User selects FLWs, enters title/tag, clicks "Launch Dashboard"
5. RENDER_CODE calls onUpdateState() to save selected_flws to state
6. Browser redirects to /custom_analysis/mbw_monitoring/?run_id={run_id}
7. Dashboard loads, scoped to the selected FLWs
8. User assesses each FLW (eligible_for_renewal / probation / suspended)
9. Each assessment calls POST /api/session/save-flw-result/ → workflow_adapter.save_flw_result()
10. User clicks "Complete Session" → POST /api/session/complete/ → workflow_adapter.complete_monitoring_run()
11. "Back to Workflows" link returns to /labs/workflow/
```

---

## Data Flow

### Step-by-Step Data Loading Sequence

1. **Browser requests dashboard page** → `MBWMonitoringDashboardView` renders the HTML template with context (URLs, dates, OAuth status, cache config defaults, monitoring session)

2. **Browser opens SSE connection** → Alpine.js `init()` calls `loadDataWithSSE()` which opens an `EventSource` to the stream endpoint

3. **Stream view executes 6 steps**, yielding progress messages at each stage:

   | Step | Data Source | What It Fetches | Cache |
   |------|-----------|-----------------|-------|
   | 1 | Connect API via AnalysisPipeline | Visit form data (12 FieldComputations: GPS, case IDs, form names, dates, parity, etc.) | Pipeline cache (Redis, config-hash based) |
   | 2 | Connect API | Active FLW usernames + display names | In-memory |
   | 3 | In-memory | GPS metrics (Haversine distances, daily travel) | None (computed) |
   | 4a | CCHQ Form API v1 | Registration forms → mother metadata (name, age, phone, eligibility, EDD, etc.) | Django cache (1hr) |
   | 4b | CCHQ Form API v1 | Gold Standard Visit Checklist forms → GS scores per FLW | Django cache (1hr) |
   | 5 | In-memory | Follow-up metrics (visit status, completion rates with eligibility + grace period) | None (computed) |
   | 6 | In-memory | Overview metrics (merge follow-up rate, GS score, GPS, quality metrics) | None (computed) |

4. **Final SSE event** contains the combined payload for all three tabs, sent as `data.complete = true`

5. **Browser processes data** → `processLoadedData()` stores raw arrays, builds mother name lookup, loads OCS bots, and calls `applyFilters()` for initial display

### Two-Source Visit Architecture

The follow-up rate calculation relies on two fundamentally different data sources that are merged at computation time. Understanding this split is critical to the dashboard's architecture.

**Background**: FLWs use a CommCare application on their devices. All form submissions are stored in CommCare HQ (CCHQ), which is the primary data store. A forwarder then sends a subset of that data to Connect. The Connect API only exposes what has been forwarded — not the full CCHQ dataset. Since Connect Labs is built on the Connect codebase, the pipeline uses the Connect API as its primary data access layer. However, some data needed by the dashboard (registration forms, GS forms) is not available through the Connect API and must be fetched directly from CCHQ.

| Data Layer | Source | What It Provides | Granularity |
|------------|--------|-----------------|-------------|
| **Completed visits** | Connect API via AnalysisPipeline | Form submissions forwarded from CCHQ (ANC Visit, PNC Visit, 1 Week, etc.) with GPS, timestamps, case IDs | 1 form submission → 1 VisitRow |
| **Expected visits** (scheduled, due, missed) | CCHQ Form API (registration forms) | Visit schedules extracted from `var_visit_1..6` blocks: visit type, scheduled date, expiry date, mother_case_id | 1 registration form → up to 6 expected visit records |
| **Mother metadata** | CCHQ Form API (registration forms) | Name, phone, age, household size, eligibility, EDD, preferred visit time | 1 registration form → 1 mother record |
| **GS scores** | CCHQ Form API (GS forms, separate supervisor app) | Gold Standard assessment scores per FLW | 1 GS form → 1 FLW score |

**Key insight**: The pipeline (via Connect API) contains **only completed visits** — actual form submissions that FLWs have filed. It has no knowledge of what visits *should* exist. The expected visit schedules — which define the "due" and "missed" statuses — come entirely from CCHQ registration forms (`var_visit_1..6`). These registration forms are not available through the Connect API, so they are fetched directly from the CCHQ Form API.

**Merge logic** (in `build_followup_from_pipeline()` and `followup_analysis.py`):
1. Registration forms (from CCHQ) provide the expected visits with scheduled dates and expiry dates
2. Pipeline rows (from Connect API) provide completed form submissions with timestamps
3. For each expected visit, the system checks if a matching completed visit exists (via `COMPLETION_FLAGS` + `FORM_NAME_TO_VISIT_TYPE` normalization)
4. Unmatched expected visits become "due" or "missed" depending on the current date vs expiry date

**Why two API sources**: While all data originates in CCHQ, only a subset is forwarded to Connect. The Connect API exposes visit form submissions but not registration form data or GS assessment forms. Since Connect Labs focuses on data available through the Connect API, the pipeline uses Connect as its primary source. Registration forms and GS forms are fetched directly from CCHQ to fill the gap. The merge happens server-side in Python during SSE streaming.

### Data Payload Structure

The final SSE payload (`data.data`) contains:

```json
{
  "success": true,
  "opportunity_id": 123,
  "opportunity_name": "MBW Nigeria",
  "from_cache": true,
  "dev_fixture": false,
  "gps_data": {
    "total_visits": 500,
    "total_flagged": 12,
    "date_range_start": "2025-01-01",
    "date_range_end": "2025-01-31",
    "flw_summaries": [...]
  },
  "followup_data": {
    "total_cases": 300,
    "flw_summaries": [
      {
        "username": "flw001",
        "display_name": "Alice Mensah",
        "completed_on_time": 20,
        "completed_late": 5,
        "due_on_time": 3,
        "due_late": 2,
        "missed": 1,
        "completed_total": 25,
        "due_total": 5,
        "missed_total": 1,
        "total_visits": 31,
        "completion_rate": 81,
        "status_color": "green"
      }
    ],
    "flw_drilldown": {
      "flw001": [
        {
          "mother_case_id": "abc123",
          "mother_name": "Fatima Ibrahim",
          "registration_date": "2024-11-15",
          "age": "28",
          "phone_number": "+234...",
          "household_size": "5",
          "preferred_time_of_visit": "morning",
          "anc_completion_date": "2024-12-01",
          "pnc_completion_date": "",
          "expected_delivery_date": "2025-03-15",
          "baby_dob": "",
          "eligible": true,
          "completed": 4,
          "total": 5,
          "follow_up_rate": 80,
          "has_due_visits": true,
          "visits": [...]
        }
      ]
    }
  },
  "overview_data": {
    "flw_summaries": [
      {
        "username": "flw001",
        "display_name": "Alice Mensah",
        "cases_registered": 15,
        "eligible_mothers": 12,
        "first_gs_score": "86",
        "post_test_attempts": null,
        "followup_rate": 81,
        "revisit_distance_km": 1.2,
        "median_meters_per_visit": 450,
        "median_minutes_per_visit": 35,
        "phone_dup_pct": 5,
        "anc_pnc_same_date_count": 0,
        "anc_pnc_denominator": 8,
        "parity_concentration": {"pct_duplicate": 10, "mode_value": "2", "mode_pct": 30},
        "age_concentration": {"pct_duplicate": 8, "mode_value": "25", "mode_pct": 15},
        "age_equals_reg_pct": 2,
        "cases_still_eligible": {"eligible": 10, "total": 12, "pct": 83}
      }
    ],
    "visit_status_distribution": {
      "completed_on_time": 150,
      "completed_late": 30,
      "due_on_time": 20,
      "due_late": 15,
      "missed": 5,
      "total": 220
    }
  },
  "active_usernames": ["flw001", "flw002"],
  "flw_names": {"flw001": "Alice Mensah", "flw002": "Bob Kone"},
  "open_task_usernames": ["flw002"],
  "monitoring_session": { "id": 884, "title": "March 2025 Review", "tag": "monthly-review", "status": "in_progress", "session_type": "mbw_monitoring", "opportunity_id": "765", "selected_flw_usernames": ["flw001", "flw002"], "flw_results": {...}, "run_id": 884 }
}
```

---

## Three-Tab Dashboard

### Overview Tab

Provides a bird's-eye view of each FLW's performance by merging data from all sources.

**Summary Card**: Visit Status Distribution (100% stacked bar chart)
- Color-coded segments: Completed On Time (green), Completed Late (light green), Due On Time (yellow), Due Late (orange), Missed (red)

**FLW Table Columns**:
| Column | Data Source | Description |
|--------|-----------|-------------|
| FLW Name | Connect API | Display name with avatar |
| # Mothers | Registration forms + pipeline | Total registered / eligible for full intervention bonus |
| GS Score | CCHQ GS forms | First (oldest) Gold Standard Visit Checklist score. Color: green ≥70, yellow 50-69, red <50 |
| Follow-up Rate | Follow-up analysis | % of visits due 5+ days ago that are completed, among eligible mothers |
| Eligible 5+ | Drill-down data | Eligible mothers still on track (5+ completed OR ≤1 missed). Color: green ≥70%, yellow 50-69%, red <50% |
| Revisit Dist. | GPS analysis | Median haversine distance (km) between revisits to the same mother |
| Meter/Visit | GPS analysis | Median meters traveled per visit (filtered by app build version) |
| Min/Visit | GPS analysis | Median minutes per visit |
| Phone Dup % | Quality metrics | % of mothers sharing duplicate phone numbers |
| Parity Conc. | Quality metrics | Parity value concentration (% duplicate + mode) |
| Age Conc. | Quality metrics | Age value concentration (% duplicate + mode) |
| ANC≠PNC | Quality metrics | Count of mothers where ANC and PNC completion dates match |

**Actions per FLW** (Overview tab only — other tabs have Filter only):
- **Assessment buttons** (monitoring session only): Eligible for Renewal (green), Probation (yellow), Suspended (red) — toggle on click, stored in `flw_results`
- **Notes button**: Opens modal with assessment + notes for the FLW
- **Filter button**: Adds FLW to the multi-select filter
- **Task creation button**: Creates a task for the FLW (greyed out if open task exists)

### GPS Analysis Tab

Identifies potential fraud or GPS anomalies by analyzing distances between consecutive visits to the same mother case.

**Summary Cards**: Total Visits, Flagged Visits, Date Range, Flag Threshold (5 km)

**FLW Table Columns**:
| Column | Description |
|--------|-----------|
| FLW Name | With avatar initial |
| Total Visits | Within date range |
| With GPS | Count + percentage |
| Flagged | Visits exceeding 5km threshold (highlighted red) |
| Unique Cases | Distinct mother_case_id count |
| Avg Case Dist | Average distance between visits to same case (km) |
| Max Case Dist | Maximum distance (red if >5km) |
| Trailing 7 Days | Sparkline bar chart of daily travel distance |

**Actions per FLW**: Filter button, Details drill-down button (no assessment or task buttons)

**Drill-Down**: Clicking "Details" on a FLW row expands an inline panel showing individual visit records with date, form name, entity, GPS coordinates, distance from previous visit, and flagged status.

**GPS Analysis Logic** (from `mbw/gps_analysis.py`):
- Haversine formula calculates great-circle distance between GPS coordinates
- Visits are grouped by `mother_case_id` (linking field) and sorted by date
- Sequential visits to the same mother are compared; distance > 5km triggers a flag
- Daily travel is computed as the path distance through all visits in a day
- Trailing 7-day sparkline shows daily travel pattern for quick visual assessment
- **Meter/Visit**: Median meters per visit, filtered by `app_build_version` (requires extractor-based extraction from pipeline)
- **Minute/Visit**: Median minutes per visit from GPS timestamps

### Follow-Up Rate Tab

Tracks visit completion across 6 visit types with per-mother granularity, eligibility filtering, and grace period.

**Summary Cards**: Total Visit Cases, Total FLWs, Average Follow-up Rate (color-coded: green ≥80%, yellow ≥60%, red <60%)

**FLW Table Columns**:
| Column | Description |
|--------|-----------|
| FLW Name | Color-coded avatar (green/yellow/red based on follow-up rate) |
| Follow-up Rate | Progress bar + percentage (business definition: eligible mothers, 5+ day grace) |
| Completed | Total completed visits with percentage: "8 (20%)" |
| Due | Due visits (on-time + late only, excludes completed and missed) |
| Missed | Missed visits count |
| ANC through Month 6 | Per-visit-type breakdown showing completed/due/missed counts in mini columns |

**Eligibility Filter**: "Full intervention bonus only" checkbox (default checked). When checked, follow-up rate only counts mothers with `eligible_full_intervention_bonus = "1"`. Non-eligible mothers show "Not eligible" badge.

**Actions per FLW**: Filter button only (no assessment or task buttons)

**Drill-Down**: Clicking a FLW row expands to show per-mother visit details:
- Mother header with metadata (name, age, phone, registration date, household size, preferred visit time)
- Additional fields: ANC/PNC completion dates, expected delivery date, baby DOB
- Eligibility badge (eligible / not eligible)
- Visit table showing visit type, scheduled date, expiry date, and status
- "Show missed/completed visits" toggle (default: shows only due visits)
- "Full intervention bonus only" checkbox (default checked)
- Mother filter dropdown to narrow by specific mothers
- Close button (no task or suspend buttons in drill-down)

---

## Data Sources & APIs

### Connect Production API

Used for: Visit form data, FLW names, opportunity metadata

- **Visit forms**: Fetched via `AnalysisPipeline` using `MBW_GPS_PIPELINE_CONFIG` from `mbw/pipeline_config.py`. Extracts 12 fields per visit using FieldComputations (3 use `extractor`, 9 use `path`).
- **FLW names**: `fetch_flw_names()` from `labs/analysis/data_access.py`
- **Opportunity metadata**: `GET /export/opportunity/{id}/` — extracts `cc_domain` and `cc_app_id` from `deliver_app` or `learn_app`

Authentication: Connect OAuth token from `request.session["labs_oauth"]`

### CommCare HQ Form API v1

Used for: Registration forms (expected visit schedules + mother metadata) and Gold Standard Visit Checklist forms (GS scores). These forms are not available through the Connect API and must be fetched directly from CCHQ.

- **Registration forms**: `fetch_registration_forms()` in `data_fetchers.py`
  - Dynamically discovers xmlns for "Register Mother" via Application Structure API
  - Endpoint: `GET /a/{domain}/api/form/v1/?xmlns={xmlns}`
  - Extracts **expected visit schedules**: `var_visit_1..6` blocks containing visit type, scheduled date, expiry date, mother_case_id, and create flags — these are the source of all "due" and "missed" visits in the follow-up rate calculation (see [Two-Source Visit Architecture](#two-source-visit-architecture))
  - Extracts **mother metadata**: mother name, phone, age (from DOB), household size, eligibility, EDD, preferred visit time
- **Gold Standard forms**: `fetch_gs_forms()` in `data_fetchers.py`
  - GS form lives in a **separate supervisor app** (not the deliver app)
  - First tries deliver app's `cc_app_id`, then falls back to cross-app xmlns discovery via `discover_form_xmlns()`
  - Cross-app discovery: `list_applications()` lists all apps in the domain, then `get_form_xmlns()` checks each app
  - Extracts: `load_flw_connect_id` (assessed FLW), `checklist_percentage` (GS score), `meta.timeEnd` (for oldest-first sorting)

Authentication: CommCare OAuth token from `request.session["commcare_oauth"]`

### CommCare HQ Application Structure API

Used for: Dynamic xmlns discovery (so the correct form xmlns is used regardless of which app version is deployed)

- **Single app**: `GET /a/{domain}/api/application/v1/{app_id}/` → walks `modules[].forms[]` matching by multilingual name dict
- **All apps**: `GET /a/{domain}/api/application/v1/` → paginated listing of all apps in the domain

### Data Relationships

```
Pipeline Visit Forms (Connect API)
    │
    ├── username ──────────> FLW Names (Connect API)
    ├── GPS coordinates ──> GPS Analysis (Haversine, meter/visit, min/visit)
    ├── form_name ─────────> Visit type normalization (FORM_NAME_TO_VISIT_TYPE)
    ├── mother_case_id ───> Mother-to-FLW mapping
    ├── parity ────────────> Quality metrics (from ANC Visit rows)
    ├── anc/pnc dates ────> Quality metrics + drill-down metadata
    └── baby_dob ──────────> Drill-down metadata (from Post delivery visit rows)

Registration Forms (CCHQ Form API)
    │
    ├── var_visit_1..6 ───> Expected visit schedules (type, dates, mother_case_id)
    ├── mother_details ───> Mother metadata (name, phone, age/DOB)
    ├── eligible_full_intervention_bonus ──> Eligibility filtering
    ├── mother_birth_outcome.expected_delivery_date ──> EDD
    └── metadata.username ──> FLW-to-mother mapping

Gold Standard Forms (CCHQ Form API, separate supervisor app)
    │
    ├── load_flw_connect_id ──> Maps to FLW username (assessed FLW)
    ├── checklist_percentage ──> GS score (0-100)
    └── meta.timeEnd ──────────> Sorting (oldest first)
```

---

## Pipeline Configuration

The `MBW_GPS_PIPELINE_CONFIG` in `pipeline_config.py` defines 12 FieldComputations for visit-level data extraction:

| Name | Type | Path / Extractor | Notes |
|------|------|-----------------|-------|
| `gps_location` | extractor | `extract_gps_location(visit_data)` | Reads `form_json.form.meta.location` |
| `case_id` | path | `form.case.@case_id` | |
| `mother_case_id` | path | `form.parents.parent.case.@case_id` | |
| `form_name` | path | `form.@name` | Has trailing space variant ("ANC Visit ") |
| `visit_datetime` | extractor | `extract_visit_datetime(visit_data)` | Reads `form_json.form.meta.timeEnd` |
| `entity_id_deliver` | paths | `form.mbw_visit.deliver.entity_id` (+ alt) | |
| `entity_name` | paths | `form.mbw_visit.deliver.entity_name` (+ alt) | |
| `parity` | path | `form.confirm_visit_information.parity__of_...` | From ANC forms only |
| `anc_completion_date` | path | `form.visit_completion.anc_completion_date` | From ANC forms only |
| `pnc_completion_date` | path | `form.pnc_completion_date` | From PNC forms only |
| `baby_dob` | path | `form.capture_the_following_birth_details.baby_dob` | From PNC forms only |
| `app_build_version` | extractor | `extract_app_build_version(visit_data)` | Integer from `form_json.form.meta.app_build_version` |

**Important**: Three fields (`gps_location`, `visit_datetime`, `app_build_version`) use the `extractor` parameter instead of `path+transform`. This is required because the PythonRedis backend cannot pass the full visit dict to transform functions — it only passes the extracted path value. The `extractor` parameter receives the full `visit._data` dict directly via `computations.py:47-49`.

---

## Follow-Up Rate Business Logic

### Business Definition

**Follow-up rate** = % of visits due 5+ days ago that have been completed, among mothers marked as eligible for full intervention bonus at registration.

### Key Constants

```python
GRACE_PERIOD_DAYS = 5       # Only count visits due 5+ days ago
THRESHOLD_GREEN = 80        # Follow-up rate ≥80% = green
THRESHOLD_YELLOW = 60       # Follow-up rate ≥60% = yellow
```

### Eligibility Filtering

- `eligible_full_intervention_bonus` is extracted from registration form top-level field
- Value `"1"` = eligible, `"0"` = not eligible
- Non-eligible mothers show "Not eligible" badge in drill-down and "N/A" rate
- "Full intervention bonus only" checkbox (default checked) toggles eligibility filtering in the UI

### Visit Status Calculation

| Status | Condition |
|--------|-----------|
| Completed - On Time | Completed within 7 days of scheduled date |
| Completed - Late | Completed after 7-day window |
| Due - On Time | Not completed, within 7-day window |
| Due - Late | Not completed, past 7-day window but before expiry |
| Missed | Not completed, past expiry date |

### Follow-Up Data Pipeline

1. **Registration forms** (CCHQ Form API) → expected visits with schedules (var_visit_1..6, checking create flags)
2. **Pipeline rows** → mother-to-FLW mapping (username + mother_case_id)
3. **Pipeline completion forms** → mark matching visits as completed (via COMPLETION_FLAGS + FORM_NAME_TO_VISIT_TYPE normalization)
4. **Aggregation** → per-FLW and per-mother metrics with filtered follow-up rate

### Key Mappings

```python
COMPLETION_FLAGS = {
    "ANC Visit": "antenatal_visit_completion",
    "Postnatal Visit": "postnatal_visit_completion",
    "Postnatal Delivery Visit": "postnatal_visit_completion",
    "1 Week Visit": "one_two_week_visit_completion",
    "1 Month Visit": "one_month_visit_completion",
    "3 Month Visit": "three_month_visit_completion",
    "6 Month Visit": "six_month_visit_completion",
}

FORM_NAME_TO_VISIT_TYPE = {
    "ANC Visit": "ANC Visit",
    "ANC Visit ": "ANC Visit",       # trailing space variant
    "Post delivery visit": "Postnatal Delivery Visit",
    "1 Week Visit": "1 Week Visit",
    "1 Month Visit": "1 Month Visit",
    "3 Month Visit": "3 Month Visit",
    "6 Month Visit": "6 Month Visit",
}
```

---

## Quality Metrics

Computed per FLW in `compute_overview_quality_metrics()` from `followup_analysis.py`:

| Metric | Description | Fraud Signal |
|--------|-------------|-------------|
| Phone Dup % | % of mothers sharing duplicate phone numbers | High % = possible fabrication |
| ANC≠PNC | Count of mothers where ANC and PNC completion dates are identical | Same-day = suspicious |
| Parity Concentration | % of parity values appearing more than once + mode value | High concentration = possible data copying |
| Age Concentration | % of age values appearing more than once + mode value | High concentration = possible data copying |
| Age = Reg % | % of mothers where DOB month/day matches registration month/day | Suggests DOB was fabricated from registration date |

---

## Caching Strategy

### Cache Layers

| Layer | What | Key Pattern | TTL | Scope |
|-------|------|-------------|-----|-------|
| Pipeline Cache | Processed visit form data | Config hash-based | Configurable | Per opportunity + config hash |
| Registration Forms | CCHQ registration forms | `mbw_registration_forms:{domain}` | 1hr | Per domain |
| GS Forms | CCHQ Gold Standard forms | `mbw_gs_forms:{domain}` | 1hr | Per domain |
| Metadata Cache | Opportunity metadata | `mbw_opp_metadata:{opp_id}` | 1hr | Per opportunity_id |
| HQ Case Cache | Visit + mother cases | `mbw_visit_cases:{domain}` | 1hr prod / 24hr dev | Per domain |

### Tolerance-Based Cache Validation

HQ case caches use a 3-tier validation system (implemented in `_validate_hq_cache()`):

1. **Count check**: If cached case count >= requested count → valid
2. **Percentage tolerance**: If cached/requested ratio >= threshold → valid
3. **Time tolerance**: If cache age <= time threshold → valid

| Mode | % Tolerance | Time Tolerance | Redis TTL |
|------|------------|---------------|-----------|
| Production | 98% | 30 minutes | 1 hour |
| Dev Fixture (`MBW_DEV_FIXTURE=1`) | 85% | 90 minutes | 24 hours |

### Cache Invalidation

- **Pipeline cache**: Auto-invalidates when `MBW_GPS_PIPELINE_CONFIG` changes (config hash)
- **CCHQ form caches**: TTL-based (1 hour)
- **Bust Cache button** (dev mode): Clears all MBW caches and forces full re-fetch
- **Refresh button**: Forces pipeline cache miss via `?bust_cache=1` URL parameter

---

## Authentication & OAuth

### Triple OAuth Requirement

The dashboard uses up to three OAuth tokens:

1. **Connect OAuth** (`labs_oauth` in session): For accessing Connect Production API (visit data, FLW names, metadata)
2. **CommCare OAuth** (`commcare_oauth` in session): For accessing CommCare HQ APIs (Form API, Application API)
3. **OCS OAuth** (`ocs_oauth` in session): For AI task creation via Open Chat Studio (optional)

### CommCare OAuth Flow

Implemented in `labs/integrations/commcare/oauth_views.py`:

1. **Initiate**: `GET /labs/commcare/initiate/?next=/mbw/` → Redirects to CommCare HQ authorization page with PKCE
2. **Callback**: `GET /labs/commcare/callback/` → Exchanges authorization code for access token, stores in session
3. **Logout**: `GET /labs/commcare/logout/` → Clears CommCare OAuth from session

### Automatic Token Refresh

The `CommCareDataAccess` client automatically refreshes expired tokens:

1. `check_token_valid()` compares `expires_at` against current time
2. If expired, calls `_refresh_token()` which POSTs to `/oauth/token/` with `grant_type=refresh_token`
3. On success, updates both instance state and session storage
4. On failure, returns `False` — caller raises `ValueError` prompting re-authorization

---

## Frontend Architecture

### Technology Stack

- **Alpine.js**: Reactive state management and DOM manipulation
- **Tailwind CSS**: Utility-first styling
- **Server-Sent Events (SSE)**: Real-time data streaming from backend
- **Fetch API**: JSON API calls for drill-down and actions

### Client-Side Filtering

All filtering happens in the browser without additional API calls:

- **FLW filter**: Multi-select dropdown. Filters all three tabs by `username` set membership
- **Mother filter**: Multi-select dropdown (populated from drilldown data with display names). Filters follow-up tab by `mother_case_id`
- **Date filter**: Start/end date inputs affect GPS data only
- **"Full intervention bonus only" checkbox**: Toggles eligibility filtering in follow-up rate
- **"Show missed/completed" toggle**: Filters visible visits in follow-up drill-down (default: only due visits)

### Sorting

Each table has independent sort state. Clicking a column header toggles ascending/descending. Numeric columns sort numerically; string columns sort alphabetically using `localeCompare()`.

### Monitoring Session Mode

When `?run_id=X` (or `?session_id=X` for backward compatibility) is provided:
- Dashboard loads the `WorkflowRunRecord` via `load_monitoring_run()` from `workflow_adapter.py`
- Dashboard scopes to the monitoring session's selected FLWs (from `state.selected_flws`)
- Three assessment buttons appear per FLW on the **Overview tab only**: Eligible for Renewal (green), Probation (amber), Suspended (red)
- Toggle behavior: clicking the same button clears the result; clicking a different button changes it
- Progress bar tracks assessed vs total FLWs
- Notes modal allows adding per-FLW notes alongside the assessment
- Session completion shows assessment summary (counts per status) — no overall pass/fail required

**FLW Assessment Statuses** (stored in `WorkflowRunRecord.state.flw_results[username].result`):

| Status | Value | Color | Meaning |
|--------|-------|-------|---------|
| (No assessment) | `null` | — | Monitoring in progress, FLW not yet assessed |
| Eligible for Renewal | `eligible_for_renewal` | Green | Good performance, eligible for renewal in future MBW opps |
| Probation | `probation` | Amber | Poor performance or potentially fraudulent, not eligible for renewal |
| Suspended | `suspended` | Red | Strong evidence of fraud or very poor performance, FLW should be replaced |

**Note**: The "Suspended" status is a **label only** — it does NOT trigger any action on Connect. The existing `MBWSuspendUserView` endpoint is retained but disabled in the UI.

Valid values are defined by `VALID_FLW_RESULTS` in `workflow_adapter.py` (tuple: `("eligible_for_renewal", "probation", "suspended")`).

---

## Features & Capabilities

### Implemented Features

| Feature | Tab | Description |
|---------|-----|------------|
| Three-tab navigation | All | Overview, GPS Analysis, Follow-Up Rate tabs |
| SSE streaming with progress | All | Real-time loading messages during data loading |
| FLW filter (multi-select) | All | Filter by FLW name across all tabs |
| Mother filter (multi-select) | Follow-Up | Filter by mother name |
| Column sorting | All | Click column headers to sort asc/desc |
| GPS drill-down | GPS | Individual visit GPS details |
| Follow-up drill-down | Follow-Up | Per-mother visit details with metadata |
| Visit status distribution | Overview | 100% stacked bar chart |
| Per-visit-type breakdown | Follow-Up | ANC through Month 6 mini columns with completed/due/missed rows |
| Trailing 7-day sparkline | GPS | Daily travel distance bar chart |
| GPS flag threshold (5km) | GPS | Red highlighting for suspicious distances |
| Follow-up rate (business def) | Follow-Up | Eligibility + grace period filtered rate |
| GS Score from CCHQ | Overview | First Gold Standard score fetched from supervisor app |
| Eligible 5+ column | Overview | Eligible mothers on track (5+ completed OR ≤1 missed) |
| Quality/fraud metrics | Overview | Phone dup, parity/age concentration, ANC≠PNC, age=reg |
| Mother metadata | Follow-Up | Name, age, phone, household size, visit time, EDD, baby DOB, eligibility |
| Meter/Visit, Min/Visit | Overview | GPS-based per-visit metrics (extractor-based extraction) |
| Monitoring session mode | Overview | 3-option FLW assessment (Eligible for Renewal / Probation / Suspended) with progress tracking |
| Task creation | Overview | Create task for FLW with automated performance prompt |
| AI conversation initiation | Overview | OCS bot conversation with pre-built prompt |
| Automatic token refresh | Backend | CommCare OAuth token auto-refreshed when expired |
| Cross-app xmlns discovery | Backend | GS form xmlns found by searching all apps in domain |
| Tolerance-based caching | Backend | 3-tier cache validation (count, percentage, time) |
| Toast notifications | All | Temporary notification messages |

### Placeholder / TBD Features

| Feature | Status | Notes |
|---------|--------|-------|
| Post-Test attempts | TBD | Column present in overview table, shows "—" |
| User suspension (Connect action) | Disabled | "Suspended" is now an assessment label only. `MBWSuspendUserView` endpoint retained but not called from UI. Actual Connect API suspension TBD. |

---

## Configuration

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `MBW_DEV_FIXTURE` | Enable dev mode (relaxed caching, bust cache button) | `False` |
| `COMMCARE_OAUTH_CLIENT_ID` | CommCare OAuth client ID | Required |
| `COMMCARE_OAUTH_CLIENT_SECRET` | CommCare OAuth client secret | Required |
| `COMMCARE_HQ_URL` | CommCare HQ base URL | `https://www.commcarehq.org` |
| `CONNECT_PRODUCTION_URL` | Connect production API URL | Required |
| `OCS_URL` | Open Chat Studio URL (for AI tasks) | Optional |
| `OCS_OAUTH_CLIENT_ID` | OCS OAuth client ID | Optional |
| `OCS_OAUTH_CLIENT_SECRET` | OCS OAuth client secret | Optional |

### Follow-Up Analysis Constants

Defined in `followup_analysis.py`:

| Constant | Value | Description |
|----------|-------|-------------|
| `GRACE_PERIOD_DAYS` | 5 | Only count visits due 5+ days ago in follow-up rate |
| `THRESHOLD_GREEN` | 80% | Follow-up rate for green status |
| `THRESHOLD_YELLOW` | 60% | Follow-up rate for yellow status |
| On-time window | 7 days | Days after scheduled date for on-time completion |

### Overview Color Thresholds

| Column | Green | Yellow | Red |
|--------|-------|--------|-----|
| Follow-up Rate | ≥80% | ≥60% | <60% |
| GS Score | ≥70 | 50-69 | <50 |
| Eligible 5+ | ≥70% | 50-69% | <50% |

### GPS Analysis Constants

Defined in `mbw/gps_analysis.py`:

| Constant | Value | Description |
|----------|-------|-------------|
| Flag threshold | 5 km | Distance above which a visit is flagged |
| Trailing days | 7 | Number of days for the sparkline chart |
| Earth radius | 6,371,000 m | Used in Haversine calculation |

### Visit Type Completion Flags

| Visit Type | CommCare Property |
|-----------|------------------|
| ANC Visit | `antenatal_visit_completion` |
| Postnatal Visit | `postnatal_visit_completion` |
| Postnatal Delivery Visit | `postnatal_visit_completion` |
| 1 Week Visit | `one_two_week_visit_completion` |
| 1 Month Visit | `one_month_visit_completion` |
| 3 Month Visit | `three_month_visit_completion` |
| 6 Month Visit | `six_month_visit_completion` |

---

## File Reference

### Core Dashboard Files

| File | Purpose |
|------|---------|
| `views.py` | 6 views: Dashboard (template), Stream (SSE), GPS Detail (JSON), Save FLW Result (3-option assessment via `workflow_adapter`), Complete Session (via `workflow_adapter`), Suspend (retained, disabled). Imports `VALID_FLW_RESULTS` from `workflow_adapter.py`. |
| `workflow_adapter.py` | `WorkflowMonitoringSession` adapter class wrapping `WorkflowRunRecord`. Helper functions: `load_monitoring_run()`, `save_flw_result()`, `complete_monitoring_run()`. Defines `VALID_FLW_RESULTS` constant. |
| `flw_api.py` | `OpportunityFLWListAPIView` — lists FLWs for an opportunity enriched with audit history from both traditional audit sessions and workflow monitoring runs. Used by the workflow template's render_code during FLW selection. |
| `data_fetchers.py` | CCHQ form fetching (registration + GS), case fetching, caching with tolerance validation, metadata fetching |
| `followup_analysis.py` | Visit status calculation, per-FLW/per-mother aggregation, eligibility filtering, quality metrics |
| `urls.py` | URL routing for dashboard, tab aliases, stream, API endpoints, and `opportunity-flws` endpoint |

### Workflow Template

| File | Purpose |
|------|---------|
| `workflow/templates/mbw_monitoring.py` | Workflow template definition (`DEFINITION`, `RENDER_CODE`, `TEMPLATE`). Auto-discovered by `workflow/templates/__init__.py`. RENDER_CODE is React JSX handling FLW selection, audit history display, metadata inputs, and dashboard launch. |

### Dashboard Template

| File | Purpose |
|------|---------|
| `templates/custom_analysis/mbw_monitoring/dashboard.html` | Full dashboard UI: tabs, tables, filters, modals, monitoring session, Alpine.js state + methods. "Back to Workflows" link navigates to `/labs/workflow/`. |

### Shared Dependencies (from existing MBW module)

| File | What's Reused |
|------|--------------|
| `custom_analysis/mbw/gps_analysis.py` | `analyze_gps_metrics()`, `compute_median_meters_per_visit()`, `compute_median_minutes_per_visit()` |
| `custom_analysis/mbw/gps_utils.py` | Haversine distance calculation, GPS coordinate parsing |
| `custom_analysis/mbw/pipeline_config.py` | `MBW_GPS_PIPELINE_CONFIG` (12 FieldComputations, 3 extractor-based) |
| `custom_analysis/mbw/views.py` | `filter_visits_by_date()`, `serialize_flw_summary()`, `serialize_visit()` |

### Labs Framework Dependencies

| File | What's Used |
|------|------------|
| `labs/analysis/pipeline.py` | `AnalysisPipeline` — data fetching and caching facade |
| `labs/analysis/sse_streaming.py` | `BaseSSEStreamView`, `AnalysisPipelineSSEMixin`, `send_sse_event()` |
| `labs/analysis/data_access.py` | `fetch_flw_names()` |
| `labs/integrations/commcare/api_client.py` | `CommCareDataAccess` — CommCare HQ API client with OAuth, `list_applications()`, `discover_form_xmlns()` |
| `labs/integrations/commcare/oauth_views.py` | CommCare OAuth initiate/callback/logout views |

### Workflow Module Dependencies

| File | What's Used |
|------|------------|
| `workflow/data_access.py` | `WorkflowDataAccess` (session CRUD, `update_run_state()` with shallow merge), `WorkflowRunRecord` |
| `workflow/templates/__init__.py` | Template registry (auto-discovers `mbw_monitoring.py` via `pkgutil`), `create_workflow_from_template()` |
| `workflow/urls.py` | Workflow list/create/run URLs (nested under `/labs/workflow/`) |

### Audit Module Dependencies (read-only)

| File | What's Used |
|------|------------|
| `audit/data_access.py` | `AuditDataAccess.get_audit_sessions()` — read-only, used by `flw_api.py` to fetch traditional audit history for FLW enrichment |

### Task Module Dependencies (read-only)

| File | What's Used |
|------|------------|
| `tasks/data_access.py` | `TaskDataAccess.get_tasks()` — read-only, used by `flw_api.py` to count open tasks per FLW |

---

## Key Field Paths

### Registration Form (CCHQ)

| Field | Path | Notes |
|-------|------|-------|
| Mother name | `form.mother_details.format_mother_name` (fallbacks: `mother_full_name`, `mother_name` + `mother_surname`) | |
| Phone | `form.mother_details.phone_number` (fallback: `back_up_phone_number`) | |
| Age | Computed from `form.mother_details.mother_dob` (fallback: `age_in_years_rounded`, `mothers_age`) | |
| Household size | `form.number_of_other_household_members` | Top-level |
| Eligibility | `form.eligible_full_intervention_bonus` | Top-level, "1"/"0" |
| Expected delivery date | `form.mother_birth_outcome.expected_delivery_date` | |
| Preferred visit time | `form.var_visit_1.preferred_visit_time` | Per-visit block |
| Mother case ID | `form.var_visit_N.mother_case_id` | First non-empty from var_visit_1..6 |

### Gold Standard Form (CCHQ, supervisor app)

| Field | Path | Notes |
|-------|------|-------|
| Assessed FLW connect ID | `form.load_flw_connect_id` | Maps to FLW username |
| GS Score | `form.checklist_percentage` | 0-100 integer |
| Visit datetime | `form.meta.timeEnd` | For oldest-first sorting |
| GS visit number | `form.gs_visit_number.which_gold_standard_visit_are_you_assessing` | e.g. "gold_standard_1" |

### Pipeline FieldComputation Extractors

| Field | Source in `visit._data` | Notes |
|-------|------------------------|-------|
| `gps_location` | `form_json.form.meta.location.#text` or string | |
| `visit_datetime` | `form_json.form.meta.timeEnd` | ISO datetime |
| `app_build_version` | `form_json.form.meta.app_build_version` | Parsed to integer |

---

## Related: OCS Session Linking Fix (Task Module)

The Task module's AI assistant integration (`tasks/views.py`) was updated to improve OCS session linking reliability. This affects all tasks (not MBW-specific).

**Problem:** `task_initiate_ai()` discarded the `trigger_bot()` response and always saved `session_id=None`. A fragile frontend-only polling mechanism (5 attempts x 2s) often failed to link the session.

**Fix (3-layer approach):**

1. **Capture `trigger_bot()` response** — session_id extracted from response if OCS returns it (checks `session_id`, `session.id`, `id` keys). Response is logged for debugging.
2. **Server-side polling fallback** — if no session_id in response, polls OCS `list_sessions()` 3 times x 2s, matching by experiment_id + identifier. `ocs_client.close()` moved after the polling loop.
3. **Frontend polling increased** — from 5x2s (10s) to 8x3s (24s) total window.
4. **"Retry Linking" button** — added to the Session Pending UI, allowing manual re-attempt via `task_ai_sessions()` endpoint.

**Files changed:**
- `tasks/views.py` — `task_initiate_ai()`: capture response, server-side polling, deferred `ocs_client.close()`
- `templates/tasks/task_create_edit.html` — increased polling, added `retrySessionLink()` method and retry button

---

*Documentation updated for the MBW Monitoring Dashboard with Workflow integration, FLW selection table enhancements, and OCS session linking fix.*
