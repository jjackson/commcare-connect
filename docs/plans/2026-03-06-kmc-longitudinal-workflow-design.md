# KMC Longitudinal Tracking — Workflow Template Design

**Date:** 2026-03-06
**Status:** Implemented

## Overview

Build a Kangaroo Mother Care (KMC) longitudinal tracking workflow as a first-class template in the Workflow Engine. Replaces the existing `custom_analysis/kmc/` + `configurable_ui/` approach with a single React-based workflow template that provides: actionable dashboard → filterable child list → interactive child timeline.

## Goals

1. Consolidate KMC multi-visit views into the Workflow Engine (eliminate the parallel `configurable_ui` system)
2. Dashboard-first design with actionable KPI cards that drill into filtered child lists
3. Rich child timeline with weight chart, map, visit history, and clinical details
4. Fully self-contained workflow template — no external component dependencies

## Architecture

### Template: `kmc_longitudinal.py`

Single workflow template file containing:
- `DEFINITION` — workflow metadata, statuses (active/discharged/lost to follow-up)
- `PIPELINE_SCHEMAS` — visit-level data extraction with `beneficiary_case_id` linking
- `RENDER_CODE` — React component handling all three views

### Pipeline Schema

Uses `pipeline_schemas` (plural) with one source:

```python
PIPELINE_SCHEMAS = [
    {
        "alias": "visits",
        "name": "KMC Visit Data",
        "schema": {
            "grouping_key": "username",
            "terminal_stage": "visit_level",
            "linking_field": "beneficiary_case_id",
            "fields": [
                # Identity & linking
                {"name": "beneficiary_case_id", "paths": [...]},
                {"name": "child_name", "paths": [...]},
                {"name": "mother_name", "paths": [...]},
                # Clinical outcomes
                {"name": "weight", "path": "form.weight", "transform": "float"},
                {"name": "birth_weight", "paths": [...], "transform": "float"},
                # Visit metadata
                {"name": "visit_date", "path": "form.visit_date", "transform": "date"},
                {"name": "visit_number", "path": "form.visit_number", "transform": "int"},
                {"name": "form_name", "path": "form.@name"},
                {"name": "gps", "path": "form.gps"},
                # Clinical detail fields (KMC hours, breastfeeding, temperature, etc.)
                ...
            ],
        },
    },
]
```

Key: `terminal_stage: "visit_level"` returns one row per visit (not aggregated per FLW). `linking_field: "beneficiary_case_id"` enables client-side grouping of visits to children.

### React Component (render_code)

Single `WorkflowUI` function component with three internal views managed by React state:

#### View 1: Dashboard

Actionable KPI summary cards computed client-side from pipeline visit data:

| Card | Metric | Click Action |
|------|--------|-------------|
| Active Children | Last visit < 14 days ago | Filter child list: active |
| Overdue Visits | Last visit > 14 days ago | Filter child list: overdue |
| Below Avg Weight Gain | Weight gain < threshold | Filter child list: low_gain |
| Reached 2.5kg | Current weight >= 2500g | Filter child list: threshold_met |
| Avg Visits/Child | Mean visit count | Informational only |
| Discharged | Marked discharged | Filter child list: discharged |

Below cards: trends section with enrollment over time (line chart) and visits per week (bar chart).

#### View 2: Child List

Filterable, sortable table of all children:
- Columns: name, FLW, visit count, current weight, last visit date
- Visual indicators: warning for overdue, checkmark for 2.5kg threshold
- Pre-filtered when arriving from dashboard KPI card click
- Search by name
- Click row → navigate to child timeline

#### View 3: Child Timeline (3-column layout)

Re-implements existing timeline UX in React:

**Header:** Child name, status badge, mother info, birth weight, current weight (+gain), contact info

**Left column (narrow):** Visit history list — clickable visit entries with date and visit number

**Center column (wide):** Weight progression chart (Chart.js line chart with 2.5kg threshold line) + Visit location map (Leaflet with colored markers)

**Right column (medium):** Clinical detail panel for selected visit — weight, temperature, KMC hours, breastfeeding status, etc. organized by section

**Bottom strip:** Visit photos

**Interactions:** Click visit in list → highlight on chart + map, show details. Click chart point → select visit. Click map marker → select visit. Back button returns to child list preserving filter state.

**Improvements over existing Alpine.js version:**
1. Back navigation preserving filter state
2. Weight gain indicator in header
3. 2.5kg threshold line on chart
4. Photo strip at bottom (less clutter)
5. Status badge in header
6. Unified React rendering (no Alpine.js ↔ React boundary)

### Data Flow

```
Template creation:
  create_workflow_from_template("kmc_longitudinal")
  → Creates pipeline definition from schema
  → Creates workflow definition with pipeline_sources
  → Creates render_code record

Runtime:
  User opens workflow → SSE streams pipeline data
  → Pipeline returns visit-level rows with computed fields
  → React receives pipelines.visits.rows
  → groupVisitsByChild() groups by beneficiary_case_id
  → computeKPIs() calculates dashboard metrics
  → Dashboard renders → user drills down → child list → timeline
```

### CDN Dependencies

Add to `run.html` (global for all workflows):
- Chart.js 4.x — weight chart and dashboard trend charts
- Leaflet 1.9.x — visit location map
- Leaflet CSS

Accessed in render_code via `window.Chart` and `window.L`.

## File Changes

| File | Action | Purpose |
|------|--------|---------|
| `workflow/templates/kmc_longitudinal.py` | New | Template definition + pipeline schemas |
| `workflow/templates/kmc_longitudinal/template.py` | New | Render code (large JSX, separate file) |
| `templates/workflow/run.html` | Edit | Add Chart.js + Leaflet CDN scripts |
| `labs/analysis/backends/sql/backend.py` | Maybe edit | Ensure visit-level + linking_field in schema pipeline |

No changes to workflow engine core, template registry, or pipeline infrastructure.

## State Management

**Ephemeral (React state only, not persisted):**
- `currentView` — dashboard / childList / timeline
- `selectedChildId` — which child's timeline to show
- `childListFilter` — active / overdue / low_gain / etc.
- `selectedVisitId` — which visit is highlighted in timeline

**Persistent (via onUpdateState → API):**
- Child status overrides (manually marking as discharged)
- Any future workflow-level state

## Design Decisions

1. **Client-side grouping** — Pipeline returns flat visit rows. Grouping by child happens in React via `useMemo`. This keeps the pipeline simple and the schema standard.

2. **Single render_code** — All three views in one component. Follows mbw_monitoring_v2 precedent. Large file but self-contained.

3. **No job handler** — Dashboard KPIs are computed client-side from visit data. No async Celery job needed (unlike mbw_monitoring which does GPS analysis server-side).

4. **Pipeline schemas format** — Uses `pipeline_schemas` (plural) even though there's only one source. This is future-proof for adding registration forms or other data sources.

5. **Global CDN loading** — Chart.js and Leaflet added to run.html for all workflows. Small libraries, no harm to other templates, simpler than conditional loading.
