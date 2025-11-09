<!-- fb323adc-5e90-4461-9ac6-8ae3da511865 1e149d72-8c9d-4bdb-9f1a-6f4b78759411 -->

# API Helper Layer for Labs Projects

## Overview

Create a two-layer architecture to simulate production API access:

1. **Generic API layer** (`labs/api_helpers.py`) - reads/writes ExperimentRecords
2. **Solicitations wrapper** (`solicitations/data_access.py`) - converts ExperimentRecords to typed proxy models

This prepares for eventual production API integration while keeping current functionality intact.

## Implementation Steps

### 1. Create Generic ExperimentRecordAPI in labs/api_helpers.py

Add a new `ExperimentRecordAPI` class that provides CRUD operations:

**Methods to implement:**

- `get_records(experiment, type, **filters)` - Query with filters for all ExperimentRecord fields
- Filters: `user_id`, `opportunity_id`, `organization_id`, `program_id`, `parent_id`, `data_filters` (dict for JSON field lookups)
- Returns: QuerySet of ExperimentRecord instances (not cast to proxy types)

- `get_record_by_id(record_id, experiment, type)` - Get single record
- Returns: ExperimentRecord instance or None

- `create_record(experiment, type, data, **metadata)` - Create new record
- Metadata: `user_id`, `organization_id`, `program_id`, `parent_id`
- Returns: Created ExperimentRecord instance

- `update_record(record_id, data=None, **metadata)` - Update existing record
- Returns: Updated ExperimentRecord instance

### 2. Create Solicitations Data Access Layer

Create `commcare_connect/solicitations/data_access.py` with:

**Classes:**

- `SolicitationDataAccess` - Wraps ExperimentRecordAPI for solicitations-specific operations
- Internally uses ExperimentRecordAPI
- Casts returned ExperimentRecords to SolicitationRecord/ResponseRecord/ReviewRecord proxy types
- Provides same method signatures as current `experiment_helpers.py` functions

**Methods (mirror existing helpers):**

- `get_solicitations(program_id=None, status=None, solicitation_type=None, is_publicly_listed=None)` → QuerySet[SolicitationRecord]
- `get_solicitation_by_id(solicitation_id)` → Optional[SolicitationRecord]
- `create_solicitation(program_id, organization_id, user_id, data_dict)` → SolicitationRecord
- `get_responses_for_solicitation(solicitation_record, status=None)` → QuerySet[ResponseRecord]
- `get_response_for_solicitation(solicitation_record, organization_id, user_id=None, status=None)` → Optional[ResponseRecord]
- `get_response_by_id(response_id)` → Optional[ResponseRecord]
- `create_response(solicitation_record, organization_id, user_id, data_dict)` → ResponseRecord
- `get_review_by_user(response_record, user)` → Optional[ReviewRecord]
- `create_review(response_record, reviewer_id, data_dict)` → ReviewRecord

### 3. Update solicitations/experiment_helpers.py

Refactor all functions to use the new `SolicitationDataAccess` class instead of direct queryset access. The function signatures remain the same, but internals delegate to the data access layer.

**Key files to modify:**

- `commcare_connect/solicitations/experiment_helpers.py` - Replace QuerySet operations with `SolicitationDataAccess` calls

### 4. Update Views to Use Data Access Layer

Update `commcare_connect/solicitations/views.py` to import from `data_access` instead of `experiment_helpers`:

- Replace direct `.objects.filter()` calls with data access methods
- Update imports to use new data access layer
- Ensure all queryset operations go through the abstraction

**Key views to update:**

- `ManageSolicitationsListView.get_queryset()`
- `MyResponsesListView.get_queryset()`
- `SolicitationListView.get_queryset()`
- `SolicitationResponsesListView.get_queryset()`
- Any other views with direct ExperimentRecord queries

### 5. Testing

Manually test the solicitations features to ensure:

- Creating solicitations works
- Viewing solicitation lists works
- Creating/editing responses works
- All queries return the correct data
- No functionality is broken by the refactoring

## Key Design Decisions

- **Generic API returns untyped ExperimentRecords** - Solicitations layer handles casting to proxy types
- **Simple query interface** - Pass specific arguments for each field (easy to refactor later)
- **No changes to templates/forms** - Only internal data access changes
- **Maintain existing function signatures** - Minimize changes to calling code

### To-dos

- [ ] Create ExperimentRecordAPI class in labs/api_helpers.py with CRUD methods
- [ ] Create SolicitationDataAccess class in solicitations/data_access.py
- [ ] Refactor experiment_helpers.py to use SolicitationDataAccess
- [ ] Update views.py to use data access layer instead of direct queries
- [ ] Test solicitations features to ensure everything works
