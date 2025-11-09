# Labs Data Access Architecture Guide

## Overview

This guide describes the standardized data access pattern for CommCare Connect Labs projects. This architecture prepares labs projects for eventual production API integration while allowing rapid prototyping using the shared database.

## Architecture Layers

```
┌─────────────────────────────────────────────────┐
│  Views / Forms / Business Logic                 │
│  (Uses helper functions)                        │
└───────────────┬─────────────────────────────────┘
                │
┌───────────────▼─────────────────────────────────┐
│  Helper Functions (experiment_helpers.py)       │
│  (Backward-compatible interface)                │
└───────────────┬─────────────────────────────────┘
                │
┌───────────────▼─────────────────────────────────┐
│  Data Access Layer (data_access.py)             │
│  (Experiment-specific, typed models)            │
└───────────────┬─────────────────────────────────┘
                │
┌───────────────▼─────────────────────────────────┐
│  Generic API Layer (labs/api_helpers.py)        │
│  (ExperimentRecordAPI - reusable)               │
└───────────────┬─────────────────────────────────┘
                │
┌───────────────▼─────────────────────────────────┐
│  ExperimentRecord Model                         │
│  (Database storage)                             │
└─────────────────────────────────────────────────┘
```

## Why This Architecture?

1. **API-Ready**: Easy to swap database queries for HTTP API calls
2. **Separation of Concerns**: Generic API layer separated from experiment logic
3. **Type Safety**: Proxy models provide typed access to JSON data
4. **Backward Compatible**: Existing code continues to work
5. **Testable**: Clear boundaries for mocking and testing

## Setting Up a New Labs Project

### Step 1: Define Your Proxy Models

Create `your_app/experiment_models.py`:

```python
"""
Proxy models for ExperimentRecord.

These provide typed access to JSON data stored in ExperimentRecord.
"""
from commcare_connect.labs.models import ExperimentRecord


class YourRecordType(ExperimentRecord):
    """Proxy model for YourRecordType-type ExperimentRecords."""

    class Meta:
        proxy = True

    # Properties for convenient access to JSON data
    @property
    def title(self):
        return self.data.get("title", "")

    @property
    def status(self):
        return self.data.get("status", "draft")

    @property
    def custom_field(self):
        return self.data.get("custom_field", "")

    # Add helper methods as needed
    def is_active(self):
        return self.status == "active"
```

**Best Practices:**

- Use `@property` for simple field access
- Return sensible defaults (don't return `None` if you can avoid it)
- Add helper methods for common business logic
- Document expected data structure in docstrings

### Step 2: Create Your Data Access Layer

Create `your_app/data_access.py`:

```python
"""
Data Access Layer for YourApp.

This layer wraps ExperimentRecordAPI to provide app-specific data access methods.
Handles casting ExperimentRecords to typed proxy models.
"""
from typing import Optional
from django.db.models import QuerySet

from commcare_connect.labs.api_helpers import ExperimentRecordAPI
from your_app.experiment_models import YourRecordType


class YourAppDataAccess:
    """Data access layer for YourApp using ExperimentRecordAPI."""

    def __init__(self):
        self.api = ExperimentRecordAPI()

    def get_records(
        self,
        program_id: Optional[int] = None,
        status: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> QuerySet[YourRecordType]:
        """
        Query for records with optional filters.

        Args:
            program_id: Filter by program ID
            status: Filter by status in JSON data
            user_id: Filter by user ID

        Returns:
            QuerySet of YourRecordType instances
        """
        # Build data_filters for JSON field queries
        data_filters = {}
        if status:
            data_filters["status"] = status

        # Get untyped ExperimentRecords from API
        qs = self.api.get_records(
            experiment="your_app",
            type="YourRecordType",
            program_id=program_id,
            user_id=user_id,
            data_filters=data_filters if data_filters else None,
        )

        # Cast to typed proxy model
        return YourRecordType.objects.filter(pk__in=qs.values_list('pk', flat=True))

    def get_record_by_id(self, record_id: int) -> Optional[YourRecordType]:
        """Get a single record by ID."""
        record = self.api.get_record_by_id(
            record_id=record_id,
            experiment="your_app",
            type="YourRecordType"
        )

        if record:
            # Cast to typed proxy model
            record.__class__ = YourRecordType
            return record
        return None

    def create_record(
        self,
        program_id: int,
        user_id: int,
        data_dict: dict
    ) -> YourRecordType:
        """Create a new record."""
        record = self.api.create_record(
            experiment="your_app",
            type="YourRecordType",
            data=data_dict,
            program_id=program_id,
            user_id=user_id,
        )

        # Cast to typed proxy model
        record.__class__ = YourRecordType
        return record

    def update_record(
        self,
        record_id: int,
        data_dict: dict
    ) -> YourRecordType:
        """Update an existing record."""
        record = self.api.update_record(
            record_id=record_id,
            data=data_dict
        )

        # Cast to typed proxy model
        record.__class__ = YourRecordType
        return record
```

**Best Practices:**

- Keep one data access class per major record type
- Use clear, descriptive method names
- Document expected parameters and return types
- Handle casting from ExperimentRecord to proxy models consistently
- Use `pk__in` pattern for QuerySet casting to maintain pagination/ordering

### Step 3: Create Helper Functions

Create `your_app/experiment_helpers.py`:

```python
"""
Helper functions for working with ExperimentRecords in YourApp.

These provide backward-compatible interfaces and delegate to the data access layer.
"""
from typing import Optional
from your_app.data_access import YourAppDataAccess
from your_app.experiment_models import YourRecordType

# Initialize the data access layer
_data_access = YourAppDataAccess()


def get_records(
    program_id: Optional[int] = None,
    status: Optional[str] = None,
) -> "QuerySet[YourRecordType]":
    """Query for records with optional filters."""
    return _data_access.get_records(
        program_id=program_id,
        status=status
    )


def get_record_by_id(record_id: int) -> Optional[YourRecordType]:
    """Get a single record by ID."""
    return _data_access.get_record_by_id(record_id)


def create_record(
    program_id: int,
    user_id: int,
    data_dict: dict
) -> YourRecordType:
    """Create a new record."""
    return _data_access.create_record(
        program_id=program_id,
        user_id=user_id,
        data_dict=data_dict
    )
```

**Best Practices:**

- Keep function signatures simple and focused
- Use module-level `_data_access` instance (lightweight singleton)
- Maintain backward compatibility when refactoring
- Document parameters and return types

### Step 4: Use in Views

```python
from django.views.generic import ListView, DetailView
from your_app.experiment_helpers import get_records, get_record_by_id
from your_app.experiment_models import YourRecordType


class RecordListView(ListView):
    """List view using the data access layer."""
    model = YourRecordType
    template_name = "your_app/record_list.html"
    context_object_name = "records"

    def get_queryset(self):
        # Use helper function - automatically uses API layer
        return get_records(
            program_id=self.kwargs.get('program_id'),
            status='active'
        )


class RecordDetailView(DetailView):
    """Detail view using the data access layer."""
    model = YourRecordType
    template_name = "your_app/record_detail.html"

    def get_object(self):
        record_id = self.kwargs['pk']
        record = get_record_by_id(record_id)
        if not record:
            raise Http404("Record not found")
        return record
```

## Migrating an Existing Labs Project

### Before: Direct QuerySet Access

```python
# OLD CODE - Direct database access
def get_queryset(self):
    return MyRecord.objects.filter(
        experiment="my_app",
        type="MyRecord",
        user_id=self.request.user.id
    ).order_by("-date_created")
```

### After: Using API Layer

```python
# NEW CODE - Using API layer
def get_queryset(self):
    from commcare_connect.labs.api_helpers import ExperimentRecordAPI
    api = ExperimentRecordAPI()
    qs = api.get_records(
        experiment="my_app",
        type="MyRecord",
        user_id=self.request.user.id
    )
    return MyRecord.objects.filter(pk__in=qs.values_list('pk', flat=True)).order_by("-date_created")
```

### Migration Checklist

- [ ] Create proxy models (`experiment_models.py`)
- [ ] Create data access layer (`data_access.py`)
- [ ] Update or create helper functions (`experiment_helpers.py`)
- [ ] Update views to use helpers or data access layer
- [ ] Test all CRUD operations
- [ ] Verify filtering and pagination work correctly
- [ ] Check that related objects (parent/children) load properly

## Common Patterns

### Pattern 1: Filtering by JSON Fields

```python
# Filter by status in JSON data
data_filters = {"status": "active", "is_public": True}
qs = api.get_records(
    experiment="my_app",
    type="MyRecord",
    data_filters=data_filters
)
```

### Pattern 2: Hierarchical Records (Parent/Child)

```python
# Get child records
def get_children(parent_record):
    qs = api.get_records(
        experiment="my_app",
        type="ChildRecord",
        parent_id=parent_record.id
    )
    return ChildRecord.objects.filter(pk__in=qs.values_list('pk', flat=True))
```

### Pattern 3: Multiple Organization Filtering

```python
# Filter by multiple organizations
org_slugs = ["org1", "org2", "org3"]
qs = api.get_records(
    experiment="my_app",
    type="MyRecord"
).filter(organization_id__in=org_slugs)
return MyRecord.objects.filter(pk__in=qs.values_list('pk', flat=True))
```

### Pattern 4: Updating Records

```python
# Update existing record
def update_my_record(record_id, new_data):
    data_access = MyAppDataAccess()

    # Get existing record
    record = data_access.get_record_by_id(record_id)

    # Merge new data with existing
    updated_data = {**record.data, **new_data}

    # Update through API
    return data_access.update_record(record_id, updated_data)
```

## ExperimentRecordAPI Reference

### Available Methods

#### `get_records(experiment, type, **filters)`

Query ExperimentRecords with filters.

**Parameters:**

- `experiment` (str, required): Experiment name
- `type` (str, required): Record type
- `user_id` (int, optional): Filter by user ID
- `opportunity_id` (int, optional): Filter by opportunity ID
- `organization_id` (str, optional): Filter by organization slug/ID
- `program_id` (int, optional): Filter by program ID
- `parent_id` (int, optional): Filter by parent record ID
- `data_filters` (dict, optional): Filter by JSON field values

**Returns:** QuerySet of ExperimentRecord instances

**Example:**

```python
api = ExperimentRecordAPI()
records = api.get_records(
    experiment="solicitations",
    type="Solicitation",
    program_id=25,
    data_filters={"status": "active", "is_publicly_listed": True}
)
```

#### `get_record_by_id(record_id, experiment, type)`

Get a single ExperimentRecord by ID.

**Parameters:**

- `record_id` (int, required): Record ID
- `experiment` (str, required): Experiment name (for validation)
- `type` (str, required): Record type (for validation)

**Returns:** ExperimentRecord instance or None

#### `create_record(experiment, type, data, **metadata)`

Create a new ExperimentRecord.

**Parameters:**

- `experiment` (str, required): Experiment name
- `type` (str, required): Record type
- `data` (dict, required): Data to store in JSON field
- `user_id` (int, optional): User ID
- `opportunity_id` (int, optional): Opportunity ID
- `organization_id` (str, optional): Organization slug/ID
- `program_id` (int, optional): Program ID
- `parent_id` (int, optional): Parent record ID

**Returns:** Created ExperimentRecord instance

#### `update_record(record_id, data=None, **metadata)`

Update an existing ExperimentRecord.

**Parameters:**

- `record_id` (int, required): Record ID to update
- `data` (dict, optional): New data (replaces existing)
- `user_id` (int, optional): Update user ID
- `organization_id` (str, optional): Update organization ID
- `program_id` (int, optional): Update program ID

**Returns:** Updated ExperimentRecord instance

## Production API Migration

When production APIs are available, update `ExperimentRecordAPI` methods:

### Before (Database Queries)

```python
def get_records(self, experiment, type, **filters):
    from commcare_connect.labs.models import ExperimentRecord
    qs = ExperimentRecord.objects.filter(experiment=experiment, type=type)
    # Apply filters...
    return qs
```

### After (API Calls)

```python
def get_records(self, experiment, type, **filters):
    import httpx
    from django.conf import settings

    # Get OAuth token from session
    access_token = self._get_access_token()

    # Build query parameters
    params = {"experiment": experiment, "type": type}
    params.update(filters)

    # Make API request
    response = httpx.get(
        f"{settings.CONNECT_PRODUCTION_URL}/api/experiments/records/",
        params=params,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10
    )
    response.raise_for_status()

    # Deserialize response into ExperimentRecord instances
    records_data = response.json()
    return self._deserialize_records(records_data)
```

**No changes needed in:**

- Data access layer
- Helper functions
- Views
- Forms
- Templates

## Testing Your Implementation

### Unit Tests

```python
from django.test import TestCase
from your_app.data_access import YourAppDataAccess
from your_app.experiment_helpers import get_records, create_record


class DataAccessTests(TestCase):
    def setUp(self):
        self.data_access = YourAppDataAccess()

    def test_create_and_retrieve_record(self):
        # Create a record
        record = create_record(
            program_id=1,
            user_id=1,
            data_dict={"title": "Test", "status": "active"}
        )

        # Retrieve it
        retrieved = self.data_access.get_record_by_id(record.id)

        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.title, "Test")
        self.assertEqual(retrieved.status, "active")

    def test_filtering(self):
        # Create test records
        create_record(1, 1, {"status": "active"})
        create_record(1, 1, {"status": "draft"})

        # Filter by status
        active_records = get_records(status="active")

        self.assertEqual(active_records.count(), 1)
```

### Integration Tests

Test through the browser to ensure:

- List views display correctly
- Detail views load
- Filtering works
- Pagination works
- Create/update operations succeed

## Best Practices Summary

### DO:

✅ Use the data access layer for all database queries
✅ Define proxy models with clear properties
✅ Keep experiment name and type consistent
✅ Document expected JSON data structure
✅ Use explicit parameter names in API calls
✅ Handle None/missing data gracefully
✅ Test all CRUD operations

### DON'T:

❌ Access `ExperimentRecord.objects` directly in views
❌ Use `.filter()` on ExperimentRecord without going through API
❌ Mix direct database access with API layer
❌ Return `None` from proxy properties when you can return a default
❌ Put business logic in proxy model properties
❌ Use magic strings for experiment/type names

## Troubleshooting

### Issue: QuerySet operations fail after casting

**Problem:**

```python
qs = api.get_records(...)
typed_qs = qs._clone(model=MyProxy)  # Error: unexpected keyword 'model'
```

**Solution:**
Use the `pk__in` pattern instead:

```python
qs = api.get_records(...)
typed_qs = MyProxy.objects.filter(pk__in=qs.values_list('pk', flat=True))
```

### Issue: Proxy model properties return wrong type

**Problem:**
Date fields stored as strings in JSON aren't being converted.

**Solution:**
Add conversion logic in proxy model properties:

```python
@property
def deadline(self):
    date_str = self.data.get("deadline")
    if date_str:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
    return None
```

### Issue: Parent/child relationships not loading

**Problem:**
`record.children.all()` returns ExperimentRecord instances, not proxy models.

**Solution:**
Use the API layer to get children:

```python
def get_children(parent_record):
    api = ExperimentRecordAPI()
    qs = api.get_records(
        experiment="my_app",
        type="ChildType",
        parent_id=parent_record.id
    )
    return ChildProxy.objects.filter(pk__in=qs.values_list('pk', flat=True))
```

## Examples from Solicitations

See the solicitations app for a complete implementation:

- `commcare_connect/solicitations/experiment_models.py` - Proxy models
- `commcare_connect/solicitations/data_access.py` - Data access layer
- `commcare_connect/solicitations/experiment_helpers.py` - Helper functions
- `commcare_connect/solicitations/views.py` - View implementations

## Questions?

If you run into issues or have questions about implementing this pattern, refer to:

1. This guide
2. The solicitations implementation
3. `commcare_connect/labs/api_helpers.py` source code
4. Ask the team!
