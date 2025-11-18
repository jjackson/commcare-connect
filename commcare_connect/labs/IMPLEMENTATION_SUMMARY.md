# Labs API Migration - Implementation Summary

## Overview

Successfully migrated Labs from prototype `ExperimentRecord` (local database) to production `LabsRecord` API integration.

## ✅ What Was Completed

### 1. Core API Client Infrastructure

- **`LocalLabsRecord`** (`labs/models.py`): Transient Python object that deserializes production API responses

  - Similar pattern to `LabsUser` (no database storage)
  - Fields map to production `LabsRecord` API response
  - Uses `username` (not `user_id`) as primary user identifier

- **`LabsRecordAPIClient`** (`labs/api_client.py`): Pure HTTP client for production API
  - Endpoint: `/export/labs_record/`
  - Methods: `get_records()`, `get_record_by_id()`, `create_record()`, `update_record()`
  - Returns `LocalLabsRecord` instances
  - Supports flexible scoping via `organization_id`, `program_id`, or `opportunity_id`

### 2. Proxy Models Updated

All proxy models now inherit from `LocalLabsRecord` instead of `ExperimentRecord`:

- `audit/experiment_models.py`: `AuditTemplateRecord`, `AuditSessionRecord`
- `tasks/experiment_models.py`: `TaskRecord`
- `solicitations/experiment_models.py`: `SolicitationRecord`, `ResponseRecord`, `ReviewRecord`

### 3. Data Access Layers Migrated

All three Labs projects updated to use `LabsRecordAPIClient`:

**audit/data_access.py**:

```python
# Now requires opportunity_id
data_access = AuditDataAccess(
    opportunity_id=456,
    access_token=token,
    request=request
)

# Returns lists instead of QuerySets
sessions: list[AuditSessionRecord] = data_access.get_audit_sessions(username="user@example.com")
```

**tasks/data_access.py** & **solicitations/data_access.py**: Similar changes

### 4. Database Cleanup

- Removed `ExperimentRecord` model from `labs/models.py`
- Created migration: `labs/migrations/0004_remove_experiment_record.py`
- **Run before deploying**: `python manage.py migrate labs`

### 5. Documentation

- `labs/MIGRATION_STATUS.md`: Comprehensive migration guide with checklists
- `labs/IMPLEMENTATION_SUMMARY.md`: This file

## 🚧 What Remains (Critical for Deployment)

### Views and URLs Must Be Updated

**All three Labs projects will be broken until views/URLs are updated.**

Required changes for each project:

1. Add `opportunity_id` to URL patterns
2. Update views to extract `opportunity_id` and `access_token`
3. Pass both to data access initialization
4. Handle list returns (no QuerySet methods like `.filter()`, `.order_by()`)

**Files needing updates**:

- `audit/urls.py` + `audit/views.py`
- `tasks/urls.py` + `tasks/views.py`
- `solicitations/urls.py` + `solicitations/views.py`

**Template for view updates**:

```python
class MyListView(ListView):
    def get_queryset(self):
        # Extract OAuth token from session
        access_token = self.request.session["labs_oauth"]["access_token"]

        # Get opportunity_id from URL
        opportunity_id = self.kwargs["opportunity_id"]

        # Initialize data access
        data_access = AuditDataAccess(
            opportunity_id=opportunity_id,
            access_token=access_token
        )

        # Fetch from API (returns list)
        records = data_access.get_audit_sessions(username=self.request.user.username)

        # Sort in Python if needed
        return sorted(records, key=lambda x: x.date_created, reverse=True)
```

See `labs/MIGRATION_STATUS.md` for complete details and checklists.

## Breaking Changes

1. **Initialization**: All data access classes support flexible scoping (no longer require hardcoded `opportunity_id`)
2. **Return Types**: `QuerySet` → `list`
3. **User ID**: `user_id` (int) → `username` (str)
4. **Parent Field**: `parent_id` → `labs_record_id`
5. **No .save()**: Must use `labs_api.update_record(record.id, record.data)`

## Production API Details

**Endpoint**: `/export/labs_record/` (no opportunity_id in URL path)

**Authentication**: OAuth Bearer token from `request.session["labs_oauth"]["access_token"]`

**Scoping**: API accepts `organization_id`, `program_id`, or `opportunity_id` as query parameters (GET) or body fields (POST)

**Key Features**:

- Flexible scoping by `organization_id`, `program_id`, or `opportunity_id`
- Supports filtering by experiment, type, username, labs_record_id
- Upsert operation (POST with or without ID)
- Returns list of records in JSON format

## Next Steps

1. **Update views/URLs** for all three projects (see MIGRATION_STATUS.md)
2. **Add error handling** around API calls
3. **Update templates** to use new URL patterns
4. **Run migration** before deploying
5. **Test thoroughly** with production API
6. **Add comprehensive tests** after views are working

## Questions?

Refer to `labs/MIGRATION_STATUS.md` for detailed checklists and examples.

Contact the team with any issues during the migration.
