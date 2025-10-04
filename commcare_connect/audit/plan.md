# Audit App - Simplified Plan

## Purpose

Local Django app for auditing FLW visit images. Review visits, mark pass/fail, export results as JSON.

## Core Components

### Models ✅

- `AuditSession`: Tracks audit of specific FLW/date range (uses text fields, not FKs)
- `AuditResult`: Individual visit pass/fail results

### Views ✅

- List/Create/Detail views for audit sessions
- AJAX endpoints for updating results
- JSON export functionality
- Image serving

### Management Commands ✅

- `load_audit_data`: Pull data from CommCare HQ APIs
- `clear_audit_data`: Reset local database

### Missing Components ❌

- **Templates**: All UI templates missing
- **Forms**: No forms.py file
- **Tables**: No django-tables2 integration

## Key URLs

```
/audit/                          # List sessions
/audit/sessions/create/          # Create session
/audit/sessions/<id>/            # Main audit interface
/audit/sessions/<id>/export/     # Export JSON
```

## Data Flow

1. Load visit data via management command
2. Create audit session for FLW/date range
3. Review visits with images, mark pass/fail
4. Export results as JSON

## Configuration Notes

- Domain: `connect-experiments`
- Readers 2nd Cohort AppID: `86bab9977e9afe5a61dbd30e0e500da7`
- Readers 1st Cohort AppID: `0181d43975fd18d5cf8724f094abe47c`
