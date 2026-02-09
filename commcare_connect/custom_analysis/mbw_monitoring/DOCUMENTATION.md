# MBW Monitoring Dashboard - Technical Documentation

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Data Flow](#data-flow)
4. [Three-Tab Dashboard](#three-tab-dashboard)
5. [Data Sources & APIs](#data-sources--apis)
6. [Caching Strategy](#caching-strategy)
7. [Authentication & OAuth](#authentication--oauth)
8. [Frontend Architecture](#frontend-architecture)
9. [Features & Capabilities](#features--capabilities)
10. [Configuration](#configuration)
11. [File Reference](#file-reference)
12. [Requirements Traceability](#requirements-traceability)

---

## Overview

The MBW (Mother Baby Wellness) Monitoring Dashboard is a real-time performance monitoring tool for frontline health workers (FLWs) operating within the CommCare Connect ecosystem. It provides supervisors with a unified view of FLW performance across three dimensions:

- **Overview**: High-level per-FLW summary combining cases registered, visit completion, and GPS metrics
- **GPS Analysis**: Distance-based anomaly detection using Haversine calculations to flag suspicious travel patterns
- **Follow-Up Rate**: Visit completion tracking across 6 visit types (ANC, Postnatal, Week 1, Month 1, Month 3, Month 6) with per-mother drill-down

The dashboard is designed for the **Labs environment** (a session-based, database-light variant of CommCare Connect) and loads all data in a single Server-Sent Events (SSE) connection, enabling real-time progress feedback during data loading.

### Key Design Decisions

- **Single SSE connection**: All three tabs load data from one streaming endpoint, avoiding redundant API calls
- **Client-side filtering**: Raw data is sent once; FLW and mother filtering happens entirely in the browser via Alpine.js
- **Two-layer caching**: Pipeline-level cache (Redis) for visit form data + HQ case cache (Django cache) for CommCare HQ case data
- **Tolerance-based cache validation**: Caches are accepted if they meet count, percentage, or time-based tolerance thresholds
- **No database writes**: All data is fetched from external APIs (Connect Production + CommCare HQ) and cached transiently

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
    │       ├── Step 1: AnalysisPipeline → Connect API (visit forms)
    │       ├── Step 2: Connect API → FLW names
    │       ├── Step 3: GPS analysis (Haversine distances)
    │       ├── Step 4: Connect API → opportunity metadata (cc_domain)
    │       ├── Step 5: CommCare HQ API → visit cases (by case IDs)
    │       ├── Step 6: CommCare HQ API → mother cases
    │       ├── Step 7: Follow-up metric aggregation
    │       └── Step 8: Overview metric computation
    │
    ├── GET /custom_analysis/mbw_monitoring/api/gps/<username>/
    │   └── MBWGPSDetailView (JSON drill-down for GPS visits)
    │
    └── POST /custom_analysis/mbw_monitoring/api/suspend-user/
        └── MBWSuspendUserView (placeholder for user suspension)
```

### Component Relationships

```
┌─────────────────┐     ┌─────────────────────┐     ┌──────────────────┐
│  Dashboard View  │────>│   Stream View (SSE)  │────>│ AnalysisPipeline │
│  (Template +     │     │  MBWMonitoringStream │     │  (Labs Framework)│
│   Context)       │     │       View           │     │                  │
└────────────────-─┘     └────────┬───────────┘     └────────┬─────────┘
                                  │                           │
                    ┌─────────────┼─────────────┐             │
                    │             │             │             │
              ┌─────▼────-──┐ ┌───▼────────┐ ┌──▼─────────┐   │
              │ data_       │ │ followup_  │ │ gps_       │   │
              │ fetchers.py │ │ analysis.py│ │ analysis.py│   │
              │ (HQ cases)  │ │ (metrics)  │ │ (MBW core) │   │
              └─────────────┘ └────────────┘ └────────────┘   │
                    │                                         │
              ┌─────▼─────────────────────────────────────────▼-─┐
              │              External APIs                       │
              │  ┌──────────────────┐  ┌─────────────────────┐   │
              │  │  CommCare HQ     │  │  Connect Production │   │
              │  │  Case API v2     │  │  API                │   │
              │  │  (visit + mother │  │  (visits, FLW names,│   │
              │  │   cases)         │  │   opportunity meta) │   │
              │  └──────────────────┘  └─────────────────────┘   │
              └──────────────────────────────────────────────────┘
```

---

## Data Flow

### Step-by-Step Data Loading Sequence

1. **Browser requests dashboard page** → `MBWMonitoringDashboardView` renders the HTML template with context (URLs, dates, OAuth status, cache config defaults)

2. **Browser opens SSE connection** → Alpine.js `init()` calls `loadDataWithSSE()` which opens an `EventSource` to the stream endpoint

3. **Stream view executes 8 steps**, yielding progress messages at each stage:

   | Step | Data Source | What It Fetches | Cache |
   |------|-----------|-----------------|-------|
   | 1 | Connect API via AnalysisPipeline | Visit form data (GPS locations, case IDs, dates) | Pipeline cache (Redis) |
   | 2 | Connect API | Active FLW usernames + display names | Django cache |
   | 3 | In-memory | GPS metrics (Haversine distances, daily travel) | None (computed) |
   | 4 | Connect API | Opportunity metadata (cc_domain) | Django cache (1hr) |
   | 5 | CommCare HQ Case API v2 | Visit cases (by case IDs from step 1) | Django cache (tolerance-validated) |
   | 6 | CommCare HQ Case API v2 | Mother cases (by mother_case_id from step 5) | Django cache (tolerance-validated) |
   | 7 | In-memory | Follow-up metrics (status, completion rates) | None (computed) |
   | 8 | In-memory | Overview metrics (merge GPS + follow-up + mother counts) | None (computed) |

4. **Final SSE event** contains the combined payload for all three tabs, sent as `data.complete = true`

5. **Browser processes data** → `processLoadedData()` stores raw arrays, builds mother name lookup, loads OCS bots, and calls `applyFilters()` for initial display

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
    "flw_summaries": [
      {
        "username": "flw001",
        "display_name": "Alice Mensah",
        "total_visits": 50,
        "visits_with_gps": 48,
        "flagged_visits": 2,
        "unique_cases": 15,
        "avg_case_distance_km": 1.2,
        "max_case_distance_km": 7.5,
        "avg_daily_travel_km": 3.4,
        "trailing_7_days": [
          {"date": "2025-01-25", "distance_km": 4.2, "visit_count": 8}
        ]
      }
    ]
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
        "due_total": 31,
        "completion_rate": 81,
        "status_color": "green",
        "anc_completed_on_time": 5,
        "anc_completed_late": 1,
        "anc_due_on_time": 0,
        "anc_due_late": 1,
        "anc_missed": 0
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
          "completed": 4,
          "total": 5,
          "follow_up_rate": 80,
          "has_due_visits": true,
          "visits": [
            {
              "case_id": "visit001",
              "visit_type": "ANC",
              "visit_date_scheduled": "2024-12-01",
              "visit_expiry_date": "2025-01-01",
              "status": "Completed - On Time"
            }
          ]
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
        "completed_visits": 25,
        "median_meters_per_case": 1.2,
        "first_gs_score": null,
        "post_test_attempts": null,
        "pct_visits_due_5_plus_days": null
      }
    ],
    "visit_status_distribution": {
      "completed_on_time": 150,
      "completed_late": 30,
      "due_on_time": 20,
      "due_late": 15,
      "missed": 5,
      "completed_on_time_pct": 68.2,
      "total": 220
    }
  },
  "active_usernames": ["flw001", "flw002"],
  "flw_names": {"flw001": "Alice Mensah", "flw002": "Bob Kone"},
  "open_task_usernames": ["flw002"]
}
```

---

## Three-Tab Dashboard

### Overview Tab

Provides a bird's-eye view of each FLW's performance by merging data from all sources.

**Summary Card**: Visit Status Distribution (100% stacked bar chart)
- Color-coded segments: Completed On Time (green), Completed Late (light green), Due On Time (yellow), Due Late (orange), Missed (red)

**FLW Table Columns**:
| Column | Data Source | Status |
|--------|-----------|--------|
| FLW Name | Connect API | Active |
| # Cases (registered mothers) | CommCare HQ mother cases | Active |
| GS Score (first Gold Standard) | - | TBD |
| Post-Test | - | TBD |
| % Due 5+ Days | - | TBD |
| Completed Visits | Follow-up analysis | Active |
| Median m/Case (GPS distance) | GPS analysis | Active |

**Actions per FLW**: Filter button, Task creation button

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

**Drill-Down**: Clicking "Details" on a FLW row expands an inline panel showing individual visit records with date, form name, entity, GPS coordinates, distance from previous visit, and flagged status.

**GPS Analysis Logic** (from `mbw/gps_analysis.py`):
- Haversine formula calculates great-circle distance between GPS coordinates
- Visits are grouped by `mother_case_id` (linking field) and sorted by date
- Sequential visits to the same mother are compared; distance > 5km triggers a flag
- Daily travel is computed as the path distance through all visits in a day
- Trailing 7-day sparkline shows daily travel pattern for quick visual assessment

### Follow-Up Rate Tab

Tracks visit completion across 6 visit types with per-mother granularity.

**Summary Cards**: Total Visit Cases, Total FLWs, Average Completion Rate

**FLW Table Columns**:
| Column | Description |
|--------|-----------|
| FLW Name | Color-coded avatar (green/yellow/red based on completion rate) |
| Completion Rate | Progress bar + percentage |
| Completed | Total completed visits (on-time + late) |
| Total Due | All visits (completed + due + missed) |
| ANC through Month 6 | Per-visit-type breakdown showing completed/due/missed counts |

**Color Thresholds**: Green >= 80%, Yellow >= 60%, Red < 60%

**Drill-Down**: Clicking a FLW row expands to show per-mother visit details:
- Mother header with metadata (name, age, phone, registration date, ANC/PNC completion dates)
- Visit table showing visit type, scheduled date, expiry date, and status
- "Show missed/completed visits" toggle (default: shows only due visits)
- Mother filter dropdown to narrow by specific mothers

**Visit Status Calculation** (from `followup_analysis.py`):
| Status | Condition |
|--------|-----------|
| Completed - On Time | Completed within 7 days of scheduled date |
| Completed - Late | Completed after 7-day window |
| Due - On Time | Not completed, within 7-day window |
| Due - Late | Not completed, past 7-day window but before expiry |
| Missed | Not completed, past expiry date |

---

## Data Sources & APIs

### Connect Production API

Used for: Visit form data, FLW names, opportunity metadata

- **Visit forms**: Fetched via `AnalysisPipeline` using `MBW_GPS_PIPELINE_CONFIG` from `mbw/pipeline_config.py`
- **FLW names**: `get_flw_names_for_opportunity()` from `labs/analysis/data_access.py`
- **Opportunity metadata**: `GET /export/opportunity/{id}/` — extracts `cc_domain` from `deliver_app` or `learn_app`

Authentication: Connect OAuth token from `request.session["labs_oauth"]`

### CommCare HQ Case API v2

Used for: Visit cases, mother cases

- **Visit cases**: Bulk-fetched via `CommCareDataAccess.fetch_cases_by_ids()` using comma-separated IDs in URL path
  - Endpoint: `GET /a/{domain}/api/case/v2/{id1},{id2},...,{idN}/`
  - Batch size: 100 cases per request (URL length limit)
  - Handles pagination within each batch
- **Mother cases**: Same API, different case IDs extracted from visit case properties

Authentication: CommCare OAuth token from `request.session["commcare_oauth"]`

### Case Data Relationships

```
Visit Forms (Connect API)
    │
    ├── case_id ──────────> Visit Cases (CommCare HQ)
    │                           │
    │                           ├── properties.mother_case_id ──> Mother Cases (CommCare HQ)
    │                           ├── properties.visit_type
    │                           ├── properties.visit_date_scheduled
    │                           ├── properties.visit_expiry_date
    │                           └── properties.*_visit_completion
    │
    ├── username ──────────> FLW Names (Connect API)
    │
    └── GPS coordinates ──> GPS Analysis (in-memory computation)
```

---

## Caching Strategy

### Two-Layer Cache Architecture

| Layer | What | Backend | TTL | Scope |
|-------|------|---------|-----|-------|
| Pipeline Cache | Processed visit form data | Redis (via `AnalysisPipeline`) | Configurable | Per opportunity + config hash |
| HQ Case Cache | Visit cases + mother cases | Django cache (Redis-backed) | 1hr prod / 24hr dev | Per cc_domain |
| Metadata Cache | Opportunity metadata | Django cache | 1 hour | Per opportunity_id |

### Tolerance-Based Cache Validation

HQ case caches use a 3-tier validation system (implemented in `_validate_hq_cache()`):

1. **Count check**: If cached case count >= requested count → valid
2. **Percentage tolerance**: If cached/requested ratio >= threshold → valid
3. **Time tolerance**: If cache age <= time threshold → valid

| Mode | % Tolerance | Time Tolerance | Redis TTL |
|------|------------|---------------|-----------|
| Production | 98% | 30 minutes | 1 hour |
| Dev Fixture (`MBW_DEV_FIXTURE=1`) | 85% | 90 minutes | 24 hours |

### Cache Busting

- **Bust Cache button** (dev mode only): Clears all MBW HQ caches (`mbw_visit_cases:*`, `mbw_mother_cases:*`, `mbw_opp_metadata:*`) and forces full re-fetch
- **Refresh button**: Forces pipeline cache miss via `?refresh=1` URL parameter
- Both can be combined: `?refresh=1&bust_cache=1` clears everything

---

## Authentication & OAuth

### Dual OAuth Requirement

The dashboard requires two separate OAuth tokens:

1. **Connect OAuth** (`labs_oauth` in session): For accessing Connect Production API (visit data, FLW names, metadata)
2. **CommCare OAuth** (`commcare_oauth` in session): For accessing CommCare HQ Case API (visit cases, mother cases)

### CommCare OAuth Flow

Implemented in `labs/integrations/commcare/oauth_views.py`:

1. **Initiate**: `GET /labs/commcare/initiate/?next=/mbw/` → Redirects to CommCare HQ authorization page with PKCE (S256 code challenge)
2. **Callback**: `GET /labs/commcare/callback/` → Exchanges authorization code for access token, stores in `request.session["commcare_oauth"]`
3. **Logout**: `GET /labs/commcare/logout/` → Clears CommCare OAuth from session

### Automatic Token Refresh

The `CommCareDataAccess` client automatically refreshes expired tokens:

1. `check_token_valid()` compares `expires_at` against current time
2. If expired, calls `_refresh_token()` which POSTs to `/oauth/token/` with `grant_type=refresh_token`
3. On success, updates both instance state and session storage
4. On failure, returns `False` — caller raises `ValueError` prompting re-authorization

### Dashboard OAuth UI

- If CommCare OAuth is not active, a prominent red banner with "Authorize CommCare HQ" button is shown
- The authorize URL includes `?next=` pointing back to the current dashboard URL, so the user returns after authorization
- OCS (Open Chat Studio) OAuth status is also tracked for the AI task creation feature

---

## Frontend Architecture

### Technology Stack

- **Alpine.js**: Reactive state management and DOM manipulation
- **Tailwind CSS**: Utility-first styling
- **Server-Sent Events (SSE)**: Real-time data streaming from backend
- **Fetch API**: JSON API calls for drill-down and actions

### Alpine.js State Structure

```javascript
mbwDashboard() {
    return {
        // Loading
        loading: true,
        loadingMessage: '',
        loadError: null,

        // Navigation
        activeTab: 'overview',  // 'overview' | 'gps' | 'followup'

        // Filters
        startDate, endDate,          // GPS date range (ISO strings)
        selectedFlws: [],             // Multi-select FLW usernames
        selectedMothers: [],          // Multi-select mother case IDs
        allUsernames: [],             // All available FLW usernames
        flwNames: {},                 // username → display name mapping
        allMotherIds: [],             // All mother case IDs (sorted by name)
        motherNames: {},              // mother_case_id → display name mapping

        // Raw data (unfiltered, set once from SSE)
        _rawGpsFlws: [],
        _rawFollowupFlws: [],
        _rawOverviewFlws: [],
        _followupDrilldownByFlw: {},  // Pre-computed per-FLW mother drill-down
        _openTaskUsernames: new Set(),

        // Filtered data (recomputed on filter change)
        filteredGpsFlws: [],
        filteredFollowupFlws: [],
        filteredOverviewFlws: [],

        // Sort state (per-table)
        sortState: {
            overview: { column: null, direction: 'asc' },
            gps: { column: null, direction: 'asc' },
            followup: { column: 'completion_rate', direction: 'asc' },
        },

        // GPS drill-down
        gpsExpandedFlw: null,
        gpsDrillDownVisits: [],

        // Follow-up drill-down
        followupExpandedFlw: null,
        followupDrillDownMothers: [],
        showAllVisits: false,

        // AI Task modal
        showAIModal: false,
        aiModalFlw: null,
        aiBots: [],
        aiSelectedBot: '',

        // Suspend modal
        showSuspendModal: false,
        suspendUsername: null,
    }
}
```

### Client-Side Filtering

All filtering happens in the browser without additional API calls:

- **FLW filter**: Multi-select dropdown. Filters all three tabs by `username` set membership
- **Mother filter**: Multi-select dropdown (populated from drilldown data with display names). Filters follow-up tab by `mother_case_id`; FLWs without matching mothers are hidden
- **Date filter**: Start/end date inputs affect GPS data only (date filtering happens server-side during GPS analysis)
- **"Show missed/completed" toggle**: Filters visible visits in follow-up drill-down (default: only due visits shown)

### Sorting

Each table has independent sort state. Clicking a column header toggles ascending/descending. Numeric columns sort numerically; string columns sort alphabetically using `localeCompare()`.

---

## Features & Capabilities

### Implemented Features

| Feature | Tab | Description |
|---------|-----|------------|
| Three-tab navigation | All | Overview, GPS Analysis, Follow-Up Rate tabs |
| SSE streaming with progress | All | Real-time loading messages ("Loading visit forms...", "Fetching 500 visit cases...") |
| FLW filter (multi-select) | All | Filter by FLW name across all tabs |
| Mother filter (multi-select) | Follow-Up | Filter by mother name across follow-up tab |
| Column sorting | All | Click column headers to sort asc/desc |
| GPS drill-down | GPS | Expand FLW row to see individual visit GPS details |
| Follow-up drill-down | Follow-Up | Expand FLW row to see per-mother visit details |
| Visit status distribution chart | Overview | 100% stacked bar with 5 status categories |
| Per-visit-type breakdown | Follow-Up | ANC, Postnatal, Week 1, Month 1, Month 3, Month 6 columns |
| Trailing 7-day sparkline | GPS | Mini bar chart showing daily travel distances |
| GPS flag threshold (5km) | GPS | Visits with case distance > 5km highlighted in red |
| Completion rate color coding | Follow-Up | Green (>=80%), Yellow (>=60%), Red (<60%) avatars and bars |
| Task creation | All | Create task for FLW with automated prompt including performance data |
| AI conversation initiation | All | Initiate OCS bot conversation with pre-built prompt |
| Task button state | All | Greyed out if FLW already has an open task |
| Suspend user | Follow-Up | Confirmation modal (placeholder - not yet implemented) |
| Cache busting (dev mode) | All | "Bust Cache" button clears all MBW caches |
| Refresh | All | "Refresh" button forces pipeline cache miss |
| CommCare OAuth prompt | All | Red banner when CommCare HQ not authorized |
| OCS OAuth prompt | AI Modal | Warning when Open Chat Studio not connected |
| DEV badge | Header | Shows "DEV" badge when `MBW_DEV_FIXTURE=1` |
| Mother metadata display | Follow-Up | Registration date, age, phone, ANC/PNC completion dates |
| Automatic token refresh | Backend | CommCare OAuth token auto-refreshed when expired |
| Tolerance-based caching | Backend | 3-tier cache validation (count, percentage, time) |
| Bulk case fetching | Backend | Comma-separated IDs in URL path, batched at 100 |
| "Add to filter" shortcut | All | Click filter icon on a FLW row to add them to the filter |
| Toast notifications | All | Temporary notification messages (3-second duration) |

### Placeholder / TBD Features

| Feature | Status | Notes |
|---------|--------|-------|
| GS Score (Gold Standard) | TBD | Column present in overview table, shows "—" |
| Post-Test attempts | TBD | Column present in overview table, shows "—" |
| % Due 5+ Days | TBD | Column present in overview table, shows "—" |
| User suspension | Placeholder | API endpoint exists but returns "not yet available" |

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

### Cache Configuration Constants

Defined in `data_fetchers.py`:

```python
METADATA_CACHE_TTL = 3600          # 1 hour (opportunity metadata)
CASES_CACHE_TTL = 3600             # 1 hour (production HQ case cache)
DEV_FIXTURE_CACHE_TTL = 86400      # 24 hours (dev mode HQ case cache)
```

Dynamic configuration via `_get_cache_config()`:

| Setting | Production | Dev Fixture |
|---------|-----------|-------------|
| `cases_ttl` | 3600s (1hr) | 86400s (24hr) |
| `cache_tolerance_pct` | 98% | 85% |
| `cache_tolerance_minutes` | 30 min | 90 min |

Pipeline-level cache TTL is configured in `labs/analysis/utils.py`:

```python
DJANGO_CACHE_TTL = 5400 if MBW_DEV_FIXTURE else 3600  # 90min dev / 1hr prod
```

### GPS Analysis Constants

Defined in `mbw/gps_analysis.py`:

| Constant | Value | Description |
|----------|-------|-------------|
| Flag threshold | 5 km | Distance above which a visit is flagged |
| Trailing days | 7 | Number of days for the sparkline chart |
| Earth radius | 6,371,000 m | Used in Haversine calculation |

### Follow-Up Analysis Constants

Defined in `followup_analysis.py`:

| Constant | Value | Description |
|----------|-------|-------------|
| `THRESHOLD_GREEN` | 80% | Completion rate for green status |
| `THRESHOLD_YELLOW` | 60% | Completion rate for yellow status |
| On-time window | 7 days | Days after scheduled date for on-time completion |

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

| File | Lines | Purpose |
|------|-------|---------|
| `views.py` | ~496 | 4 views: Dashboard (template), Stream (SSE), GPS Detail (JSON), Suspend (placeholder) |
| `data_fetchers.py` | ~425 | HQ case fetching, caching with tolerance validation, metadata fetching, FLW grouping |
| `followup_analysis.py` | ~393 | Visit status calculation, per-FLW aggregation, per-mother metrics, status distribution |
| `urls.py` | ~19 | URL routing for dashboard, tab aliases, stream, and API endpoints |
| `__init__.py` | 1 | Empty init |

### Template

| File | Lines | Purpose |
|------|-------|---------|
| `templates/custom_analysis/mbw_monitoring/dashboard.html` | ~1430 | Full dashboard UI: tabs, tables, filters, modals, Alpine.js state + methods |

### Shared Dependencies (from existing MBW module)

| File | What's Reused |
|------|--------------|
| `custom_analysis/mbw/gps_analysis.py` | `analyze_gps_metrics()`, `build_result_from_analyzed_visits()` |
| `custom_analysis/mbw/gps_utils.py` | Haversine distance calculation, GPS coordinate parsing |
| `custom_analysis/mbw/pipeline_config.py` | `MBW_GPS_PIPELINE_CONFIG` (field extraction configuration) |
| `custom_analysis/mbw/views.py` | `filter_visits_by_date()`, `serialize_flw_summary()`, `serialize_visit()` |

### Labs Framework Dependencies

| File | What's Used |
|------|------------|
| `labs/analysis/pipeline.py` | `AnalysisPipeline` — data fetching and caching facade |
| `labs/analysis/sse_streaming.py` | `BaseSSEStreamView`, `AnalysisPipelineSSEMixin`, `send_sse_event()` |
| `labs/analysis/data_access.py` | `get_flw_names_for_opportunity()` |
| `labs/analysis/utils.py` | `DJANGO_CACHE_TTL` |
| `labs/integrations/commcare/api_client.py` | `CommCareDataAccess` — CommCare HQ API client with OAuth |
| `labs/integrations/commcare/oauth_views.py` | CommCare OAuth initiate/callback/logout views |

### URL Configuration

Registered in `config/urls.py`:

```python
path("custom_analysis/mbw_monitoring/",
     include("commcare_connect.custom_analysis.mbw_monitoring.urls", namespace="mbw"))
```

Dashboard URL endpoints:

| URL | View | Name |
|-----|------|------|
| `/custom_analysis/mbw_monitoring/` | `MBWMonitoringDashboardView` | `mbw:dashboard` |
| `/custom_analysis/mbw_monitoring/gps/` | Same view, `default_tab="gps"` | `mbw:gps` |
| `/custom_analysis/mbw_monitoring/followup/` | Same view, `default_tab="followup"` | `mbw:followup` |
| `/custom_analysis/mbw_monitoring/stream/` | `MBWMonitoringStreamView` | `mbw:stream` |
| `/custom_analysis/mbw_monitoring/api/gps/<username>/` | `MBWGPSDetailView` | `mbw:gps_detail` |
| `/custom_analysis/mbw_monitoring/api/suspend-user/` | `MBWSuspendUserView` | `mbw:suspend_user` |

---

## Requirements Traceability

### Original Requirements (from MBW_Monitoring_Dashboard_Requirements.md)

| Requirement | Status | Implementation |
|------------|--------|---------------|
| Overview tab with per-FLW summary table | Done | Overview tab with 8-column table |
| GPS Analysis tab with distance metrics | Done | GPS tab with Haversine analysis, 5km flag threshold |
| Follow-up Rate tab with visit tracking | Done | Follow-up tab with 6 visit types, per-mother drill-down |
| 5 visit statuses (Completed On Time, Late, Due On Time, Late, Missed) | Done | `calculate_visit_status()` in `followup_analysis.py` |
| Per-visit-type breakdown | Done | ANC through Month 6 columns in follow-up table |
| Completion rate thresholds (80%/60%) | Done | Green/yellow/red color coding |
| Visit Status Distribution chart | Done | 100% stacked bar in overview tab |
| GPS trailing 7-day sparkline | Done | Mini bar chart per FLW in GPS table |
| GPS flagging for distances > 5km | Done | Red highlighting, flag badge |
| FLW filtering | Done | Multi-select dropdown by display name |
| Column sorting | Done | Click-to-sort with direction toggle |
| Real-time loading progress | Done | SSE streaming with step-by-step messages |
| Task creation from dashboard | Done | Modal with bot selection and automated prompt |
| AI conversation initiation | Done | OCS integration with pre-built performance data prompt |
| User suspension | Partial | Modal + endpoint exist, actual API call not implemented |
| Mother filter | Done | Multi-select dropdown by mother name (addendum) |
| Mother metadata display | Done | Registration date, age, phone, ANC/PNC dates (addendum) |
| CommCare HQ OAuth integration | Done | PKCE flow with auto-refresh |
| Cache tolerance validation | Done | 3-tier validation (count, percentage, time) |
| Bust cache capability | Done | Dev-mode button + URL parameter |
| Bulk case fetching | Done | Comma-separated IDs, batched at 100 |

### Addendum Requirements (from MBW_Monitoring_Dashboard_Requirements_ADDENDUM.md)

| Requirement | Status | Implementation |
|------------|--------|---------------|
| Mother name display in drill-down | Done | Mother case lookup enriches drill-down data |
| Mother metadata (age, phone, dates) | Done | Extracted from mother case properties |
| Mother filter dropdown | Done | Multi-select with display names, sorted alphabetically |
| Show/hide completed visits toggle | Done | "Show missed/completed visits" checkbox |
| Per-mother follow-up rate badge | Done | Color-coded rate badge on each mother header |
| Due visits default view | Done | Only due visits shown by default in drill-down |

---

*Documentation generated for the MBW Monitoring Dashboard as implemented on branch `labs-mbw`.*
