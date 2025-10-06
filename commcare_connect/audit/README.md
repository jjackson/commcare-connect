# Audit App - Simplified Plan

## Purpose

Local Django app for auditing FLW visit images. Review visits, mark pass/fail, export results as JSON. The current approach involves pulling data from Superset to populate uservisits and other database models for auditing purposes. Superset is connecting to our Connect's production instance. The code is being developed as a prototype for future production implementation.

## Setup

Once you have a local environment setup, you should only need to switch to this branch

## Core Components

### Models ✅

- `AuditSession`: Tracks audit of specific FLW/date range (uses text fields, not FKs)
- `AuditResult`: Individual visit pass/fail results

### Views ✅

- List/Create/Detail views for audit sessions
- AJAX endpoints for updating results
- JSON export functionality
- Image serving

### Management Commands

- `setup_audit_dependencies`: (Optional) Creates minimal database records from YAML config
  - Note: This is likely not needed if working with production data from Superset. Can be removed if not used.

**Note:** All data loading and clearing commands have been removed - the UI wizard handles everything through `/audit/create/`.

## Key URLs

```
/audit/                          # List sessions
/audit/create/                   # Create audit wizard (search programs, select opps, configure)
/audit/sessions/<id>/            # Main audit interface
/audit/sessions/<id>/export/     # Export JSON
/audit/api/database/reset/       # Clear audit data via API
```

## Data Flow (UI-Based Workflow)

1. Use audit creation wizard at `/audit/create/`
   - Search for programs
   - Select opportunities
   - Configure audit criteria (date range, per-FLW, last N, etc.)
   - Preview visit counts
2. System automatically downloads data from Superset and CommCare
3. Review visits with images, mark pass/fail
4. Export results as JSON

# CommCareApp Fallback CSV

commcare_app_fallback.csv

This file provides CommCareApp domain mapping that **SHOULD** be in Superset's `opportunity_commcareapp` table but is currently missing (the table has 0 rows in Superset)

## Fields

- **id**: The CommCareApp ID (matches `opportunity.deliver_app_id` in Superset)
- **cc_domain**: The CommCare project domain (e.g., "connect-experiments")
- **cc_app_id**: The CommCare application ID (32-character hex string)
- **name**: A friendly name for reference

# Notes to instruct AI on:

## Safe Styling colors to use for project that are included with tailwind:

text-green-600
text-slate-100
text-orange-600
text-violet-500
text-orange-600
text-indigo-700

bg-violet-500/20
bg-orange-600/20
bg-indigo-700/20
bg-green-600/20
bg-slate-100/20
bg-orange-600/20

bg-slate-100
gap-16

font-bold
border-red-500

## Connect Supserset Schema.csv

This the schema of all tables available in Superset. You need to check if the tables are empty however, as not everything is populated.
