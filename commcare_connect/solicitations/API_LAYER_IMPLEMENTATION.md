# API Helper Layer Implementation

## Overview

Successfully implemented a two-layer data access architecture for the solicitations lab project to simulate production API access patterns. This prepares the codebase for eventual production API integration.

## Architecture

```
Views/Forms
    |
    v
experiment_helpers.py (Legacy interface)
    |
    v
data_access.py (Solicitations-specific wrapper)
    |
    v
labs/api_helpers.py (Generic ExperimentRecordAPI)
    |
    v
ExperimentRecord (Database)
```

## Changes Made

### 1. Generic API Layer (`commcare_connect/labs/api_helpers.py`)

Created `ExperimentRecordAPI` class with methods:

- `get_records()` - Query with filters for all ExperimentRecord fields
- `get_record_by_id()` - Get single record by ID
- `create_record()` - Create new ExperimentRecord
- `update_record()` - Update existing ExperimentRecord

**Key features:**

- Returns untyped ExperimentRecord instances
- Supports filtering by: experiment, type, user_id, organization_id, program_id, parent_id
- Supports JSON field queries via `data_filters` parameter
- Simple, explicit parameter interface (easy to refactor for real APIs)

### 2. Solicitations Data Access Layer (`commcare_connect/solicitations/data_access.py`)

Created `SolicitationDataAccess` class that:

- Wraps ExperimentRecordAPI for solicitations-specific operations
- Casts ExperimentRecords to typed proxy models (SolicitationRecord, ResponseRecord, ReviewRecord)
- Provides same interface as existing helper functions

**Methods implemented:**

- `get_solicitations()` - Query solicitations with filters
- `get_solicitation_by_id()` - Get single solicitation
- `create_solicitation()` - Create new solicitation
- `get_responses_for_solicitation()` - Get all responses for a solicitation
- `get_response_for_solicitation()` - Get specific org's response
- `get_response_by_id()` - Get single response
- `create_response()` - Create new response
- `get_review_by_user()` - Get user's review
- `create_review()` - Create new review
- `get_responses_for_organization()` - Get all org responses

### 3. Refactored Helper Functions (`commcare_connect/solicitations/experiment_helpers.py`)

- All functions now delegate to `SolicitationDataAccess`
- Function signatures unchanged (backward compatible)
- No more direct QuerySet operations
- Maintains existing interface for views/forms

### 4. Updated Views (`commcare_connect/solicitations/views.py`)

Updated views to use the API layer instead of direct QuerySet operations:

- `ManageSolicitationsListView.get_queryset()` - Uses ExperimentRecordAPI
- `MyResponsesListView.get_queryset()` - Uses ExperimentRecordAPI
- `SolicitationResponseDetailView.get_queryset()` - Uses ExperimentRecordAPI

All other views continue to use `experiment_helpers.py` functions (which now use the API layer internally).

## Benefits

1. **API-Ready**: Interface designed to easily swap QuerySet operations for HTTP API calls
2. **Type Safety**: Explicit casting to proxy models at data access layer
3. **Separation of Concerns**: Generic API layer separated from solicitations-specific logic
4. **Backward Compatible**: Existing code continues to work without changes
5. **Testable**: Clear boundaries make it easy to mock API layer in tests

## Migration Path to Production APIs

When production APIs are ready:

1. Update `ExperimentRecordAPI` methods to make HTTP calls instead of database queries
2. Parse API responses and instantiate ExperimentRecord objects from JSON
3. No changes needed to `SolicitationDataAccess` or higher-level code

Example:

```python
def get_records(self, experiment, type, **filters):
    # OLD: qs = ExperimentRecord.objects.filter(...)
    # NEW:
    response = httpx.get(
        f"{API_BASE_URL}/experiments/{experiment}/{type}/",
        params=filters,
        headers={"Authorization": f"Bearer {access_token}"}
    )
    data = response.json()
    return [self._deserialize(item) for item in data['results']]
```

## Testing Status

- Django system check: PASSED
- Linter errors: NONE
- Manual testing: Recommended to verify all solicitation features work correctly

## Future Improvements

1. Add `get_reviews_for_response()` to `SolicitationDataAccess` (currently uses API directly in helpers)
2. Consider caching layer for frequently accessed records
3. Add pagination support to API methods
4. Add bulk create/update methods for batch operations
