# Labs API Migration Status

## Completed Implementation

This document summarizes the migration from `ExperimentRecord` (local database prototype) to `LocalLabsRecord` (production API client).

### ✅ Core Infrastructure (COMPLETED)

1. **LocalLabsRecord Class** (`labs/models.py`)

   - Transient Python object (not a Django model)
   - Deserializes production API responses
   - Fields: `id`, `experiment`, `type`, `data`, `username`, `opportunity_id`, `organization_id`, `program_id`, `labs_record_id`
   - Prevents `save()`/`delete()` operations (raises `NotImplementedError`)

2. **LabsRecordAPIClient** (`labs/api_client.py`)

   - Pure HTTP client for production `/export/opportunity/{opp_id}/labs_record/` API
   - Methods:
     - `get_records(experiment, type, **filters)` → `list[LocalLabsRecord]`
     - `get_record_by_id(record_id, experiment, type)` → `LocalLabsRecord | None`
     - `create_record(experiment, type, data, **metadata)` → `LocalLabsRecord`
     - `update_record(record_id, data, **metadata)` → `LocalLabsRecord`
   - Requires `opportunity_id` at initialization (API is opportunity-scoped)
   - Uses OAuth Bearer token authentication

3. **Proxy Models Updated** (audit, tasks, solicitations)

   - Changed from `ExperimentRecord` → `LocalLabsRecord` inheritance
   - Removed `class Meta: proxy = True` (not Django models anymore)
   - All property accessors remain unchanged (still access `self.data`)
   - Files updated:
     - `audit/experiment_models.py` (AuditTemplateRecord, AuditSessionRecord)
     - `tasks/experiment_models.py` (TaskRecord)
     - `solicitations/experiment_models.py` (SolicitationRecord, ResponseRecord, ReviewRecord)

4. **Data Access Layers Updated**

   - **audit/data_access.py**:
     - `AuditDataAccess.__init__()` now requires `opportunity_id` parameter
     - Replaced `ExperimentRecordAPI` with `LabsRecordAPIClient`
     - Changed `user_id` → `username` throughout
     - Return types: `QuerySet` → `list`
   - **tasks/data_access.py**:
     - `TaskDataAccess.__init__()` now requires `opportunity_id` parameter
     - Replaced `ExperimentRecordAPI` with `LabsRecordAPIClient`
     - All `.save()` calls replaced with `labs_api.update_record()`
     - Return types: `QuerySet` → `list`
   - **solicitations/data_access.py**:
     - `SolicitationDataAccess.__init__()` now requires `opportunity_id` and `access_token`
     - Replaced `ExperimentRecordAPI` with `LabsRecordAPIClient`
     - Changed `user_id` → `username`, `parent_id` → `labs_record_id`
     - Return types: `QuerySet` → `list`

5. **ExperimentRecord Model Removed**
   - Deleted from `labs/models.py`
   - Migration created: `labs/migrations/0004_remove_experiment_record.py`
   - **IMPORTANT**: Run migration before deploying: `python manage.py migrate labs`

### Key API Changes

#### Field Name Changes

| Old (ExperimentRecord) | New (LocalLabsRecord) | Notes                                   |
| ---------------------- | --------------------- | --------------------------------------- |
| `user_id`              | `username`            | API uses username as primary identifier |
| `parent_id`            | `labs_record_id`      | Matches production model field name     |
| `parent` (property)    | `labs_record_id`      | No automatic FK resolution              |
| `program_id`           | `program_id`          | Being added to production API soon      |

#### Method Signature Changes

```python
# OLD
data_access = AuditDataAccess(access_token=token)
records = data_access.get_audit_sessions(auditor_id=123)  # Returns QuerySet

# NEW
data_access = AuditDataAccess(opportunity_id=456, access_token=token)
records = data_access.get_audit_sessions(username="user@example.com")  # Returns list
```

### 🚧 Remaining Work (TODO)

#### 1. Update Views and URLs (HIGH PRIORITY)

**Impact**: All views currently broken until updated

**Required Changes**:

- Add `opportunity_id` to all URL patterns:
  ```python
  # OLD: path("sessions/", ...)
  # NEW: path("opportunity/<int:opportunity_id>/sessions/", ...)
  ```
- Update all view methods to:
  - Extract `opportunity_id` from URL kwargs
  - Get OAuth token from `request.session["labs_oauth"]["access_token"]`
  - Pass both to data access layer initialization
  - Handle list returns instead of QuerySets (no `.filter()`, `.order_by()`, etc.)

**Example Pattern**:

```python
class AuditSessionListView(ListView):
    def get_queryset(self):
        # Get OAuth token
        access_token = self.request.session["labs_oauth"]["access_token"]

        # Initialize data access with opportunity context
        data_access = AuditDataAccess(
            opportunity_id=self.kwargs["opportunity_id"],
            access_token=access_token,
        )

        # Fetch from API (returns list, not QuerySet)
        sessions = data_access.get_audit_sessions(username=self.request.user.username)

        # Sort in Python if needed
        return sorted(sessions, key=lambda x: x.date_created, reverse=True)
```

**Files Needing Updates**:

- `audit/urls.py` + `audit/views.py` + `audit/experiment_views.py`
- `tasks/urls.py` + `tasks/views.py`
- `solicitations/urls.py` + `solicitations/views.py`

#### 2. Add Error Handling (MEDIUM PRIORITY)

**Impact**: Production errors will crash views

**Required**:

- Wrap API calls in try/except blocks
- Handle `LabsAPIError` exceptions gracefully
- Show user-friendly error messages
- Add offline mode support (optional)

**Example**:

```python
from commcare_connect.labs.api_client import LabsAPIError
from django.contrib import messages

try:
    sessions = data_access.get_audit_sessions()
except LabsAPIError as e:
    messages.error(request, f"Failed to load data from API: {e}")
    sessions = []  # Or show cached data
```

#### 3. Update Templates (MEDIUM PRIORITY)

**Impact**: Links and forms may be broken

**Required**:

- Update all URL reversals to include `opportunity_id`:

  ```django
  {% raw %}
  {# OLD #}
  {% url 'audit:session_list' %}

  {# NEW #}
  {% url 'audit:session_list' opportunity_id=opportunity.id %}
  {% endraw %}
  ```

- Update pagination (lists don't support Django pagination)
- Update any QuerySet-specific template code

#### 4. Add Tests (MEDIUM PRIORITY)

**Impact**: No regression protection

**Required**:

- Unit tests for `LocalLabsRecord`
- Unit tests for `LabsRecordAPIClient` (with mocked HTTP)
- Integration tests for data access layers
- View tests with mocked API

**Test file structure**:

```
labs/tests/
  test_local_labs_record.py
  test_api_client.py

audit/tests/
  test_data_access_api.py
  test_views_api.py
```

#### 5. Update Documentation (LOW PRIORITY)

**Impact**: Developer confusion

**Files to Update**:

- `labs/DATA_ACCESS_GUIDE.md` - Update ExperimentRecordAPI → LabsRecordAPIClient
- `labs/DATA_ACCESS_QUICKSTART.md` - Update quick start examples
- Individual project READMEs

## Migration Checklist

### Pre-Deployment

- [ ] Export any existing ExperimentRecord data (if needed)
- [ ] Test OAuth token extraction from session
- [ ] Verify production API endpoint is accessible
- [ ] Update all view files (see list above)
- [ ] Update all URL files (see list above)
- [ ] Update templates with correct URL reversals
- [ ] Add error handling to views

### Deployment

- [ ] Deploy code changes
- [ ] Run migration: `python manage.py migrate labs`
- [ ] Verify ExperimentRecord table is dropped
- [ ] Test each Labs project (audit, tasks, solicitations)
- [ ] Monitor API error rates

### Post-Deployment

- [ ] Add tests
- [ ] Update documentation
- [ ] Monitor performance (API latency)
- [ ] Gather user feedback

## Breaking Changes Summary

1. **Data Access Initialization**: All require `opportunity_id` parameter
2. **Return Types**: `QuerySet` → `list` (no Django ORM methods)
3. **User Identification**: `user_id` (int) → `username` (str)
4. **Parent References**: `parent_id` → `labs_record_id`
5. **Save Operations**: No `.save()` method, must use `labs_api.update_record()`

## Production API Endpoint

**URL**: `/export/opportunity/<int:opp_id>/labs_record/`

**Authentication**: OAuth Bearer token

**GET Parameters**:

- `experiment`: Filter by experiment name
- `type`: Filter by record type
- `username`: Filter by username
- `organization_id`: Filter by org
- `program_id`: Filter by program (coming soon)
- `labs_record_id`: Filter by parent
- `data__<field>`: Filter by JSON data field

**POST Body** (upsert):

```json
[
  {
    "id": 123,  // Omit for create, include for update
    "experiment": "audit",
    "type": "AuditSession",
    "data": {"status": "in_progress", ...},
    "username": "user@example.com",
    "labs_record_id": 789,  // Parent reference
    "program_id": 25  // Coming soon
  }
]
```

## Questions / Issues

Contact the team if you encounter:

- OAuth token expiration issues
- API performance problems
- Missing fields in API responses
- Confusion about opportunity scoping

## Timeline

- **Phase 1 (DONE)**: Core infrastructure - LocalLabsRecord, API client, data access
- **Phase 2 (TODO)**: Views and URLs updates
- **Phase 3 (TODO)**: Error handling and testing
- **Phase 4 (TODO)**: Documentation and refinement
