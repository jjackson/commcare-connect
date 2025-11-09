# Labs Data Access Quick Start

Quick reference for implementing the data access pattern in labs projects.

## 3-Minute Setup

### 1. Create Proxy Model (`experiment_models.py`)

```python
from commcare_connect.labs.models import ExperimentRecord

class MyRecord(ExperimentRecord):
    class Meta:
        proxy = True

    @property
    def title(self):
        return self.data.get("title", "")
```

### 2. Create Data Access (`data_access.py`)

```python
from commcare_connect.labs.api_helpers import ExperimentRecordAPI
from .experiment_models import MyRecord

class MyDataAccess:
    def __init__(self):
        self.api = ExperimentRecordAPI()

    def get_records(self, **filters):
        qs = self.api.get_records(experiment="my_app", type="MyRecord", **filters)
        return MyRecord.objects.filter(pk__in=qs.values_list('pk', flat=True))

    def get_by_id(self, record_id):
        record = self.api.get_record_by_id(record_id, "my_app", "MyRecord")
        if record:
            record.__class__ = MyRecord
        return record

    def create(self, data):
        record = self.api.create_record(experiment="my_app", type="MyRecord", data=data)
        record.__class__ = MyRecord
        return record
```

### 3. Create Helpers (`experiment_helpers.py`)

```python
from .data_access import MyDataAccess

_data_access = MyDataAccess()

def get_records(**filters):
    return _data_access.get_records(**filters)

def get_by_id(record_id):
    return _data_access.get_by_id(record_id)

def create(data):
    return _data_access.create(data)
```

### 4. Use in Views

```python
from .experiment_helpers import get_records, get_by_id

class MyListView(ListView):
    def get_queryset(self):
        return get_records(program_id=self.kwargs['program_id'])
```

## Common Snippets

### Filter by JSON field:

```python
qs = api.get_records(
    experiment="my_app",
    type="MyRecord",
    data_filters={"status": "active"}
)
```

### Filter by user:

```python
qs = api.get_records(
    experiment="my_app",
    type="MyRecord",
    user_id=request.user.id
)
```

### Get children:

```python
qs = api.get_records(
    experiment="my_app",
    type="ChildRecord",
    parent_id=parent.id
)
```

### Update record:

```python
record = api.update_record(
    record_id=record.id,
    data={"status": "completed"}
)
```

## Remember

- ✅ Always use `pk__in` pattern for QuerySet casting
- ✅ Cast individual records with `record.__class__ = ProxyModel`
- ✅ Use `data_filters` for JSON field queries
- ❌ Don't use `.objects.filter()` directly in views
- ❌ Don't use `._clone(model=...)` (not supported)

## Full Guide

See `DATA_ACCESS_GUIDE.md` for complete documentation.
