# Solicitations Helpers Migration Summary

## Overview

The `helpers.py` file has been removed and all views/forms now use `SolicitationDataAccess` directly.

## Changes Made

### 1. Configuration (`config.py`)

Created `commcare_connect/solicitations/config.py` with:

- `SOLICITATION_DEFAULT_OPPORTUNITY_ID`: Hardcoded opportunity_id for API calls
- Can be overridden in Django settings with `SOLICITATION_DEFAULT_OPPORTUNITY_ID = <value>`
- **TEMPORARY**: This will be removed once the production API no longer requires `opportunity_id` for solicitations

### 2. Views (`views.py`)

- **Removed**: All imports from `helpers.py`
- **Added**: `SolicitationDataAccessMixin` providing `data_access` property to all views
- **Updated**: All view classes now inherit from `SolicitationDataAccessMixin`
- **Replaced**: All helper function calls with `self.data_access.<method>()` calls

Examples:

```python
# Before:
from .helpers import get_solicitations
solicitations = get_solicitations(status="active")

# After:
class MyView(SolicitationDataAccessMixin, ...):
    def get_queryset(self):
        return self.data_access.get_solicitations(status="active")
```

### 3. Forms (`forms.py`)

- **Removed**: Import of `get_responses_for_solicitation` from helpers
- **Updated**: `SolicitationResponseForm.__init__()` now accepts `data_access` parameter
- **Updated**: Views pass `data_access` to forms via `get_form_kwargs()`

### 4. Deleted Files

- `commcare_connect/solicitations/helpers.py` - No longer needed

## How It Works Now

### Data Access Flow

```
Request → View (with SolicitationDataAccessMixin)
    ↓
View.data_access property
    ↓
SolicitationDataAccess(
    opportunity_id=SOLICITATION_DEFAULT_OPPORTUNITY_ID,  # Hardcoded for now
    access_token=request.labs_access_token  # From OAuth middleware
)
    ↓
LabsRecordAPIClient → Production API
```

### Setting the Opportunity ID

In your `local_settings.py` or environment-specific settings:

```python
# Override the default opportunity_id for solicitations
SOLICITATION_DEFAULT_OPPORTUNITY_ID = 123  # Your desired opportunity ID
```

If not set, defaults to `1`.

## Migration Path (Future)

Once the production API is updated to tie solicitations to programs instead of opportunities:

1. Remove `opportunity_id` parameter from `SolicitationDataAccess` calls
2. Update `LabsRecordAPIClient` to not require `opportunity_id` for solicitation endpoints
3. Delete `config.py` and remove the hardcoded `SOLICITATION_DEFAULT_OPPORTUNITY_ID`

## Benefits of This Change

1. **Consistency**: Now follows the same pattern as `audit` and `tasks` apps
2. **Explicitness**: Views explicitly manage context (opportunity_id, access_token)
3. **No Hidden State**: No global singletons or module-level instantiation
4. **Easier Testing**: Data access can be mocked at the view level
5. **Better Error Messages**: Failures happen where context is needed, not at import time

## Testing

The changes have been verified with `python manage.py check` and pass successfully.

Note: `solicitations/tests/test_experiment_helpers.py` may need updating if it relies on the old helpers. Consider either:

- Deleting it (if it was just testing the thin helper wrappers)
- Updating it to test `SolicitationDataAccess` directly
