# Solicitations Lab - Architecture Update

## Summary

Successfully implemented **Option A**: Using production IDs as integers without ForeignKeys in the local database. This aligns with the labs philosophy of keeping production data ephemeral and session-based.

## Key Changes

### 1. Data Model Architecture

**Before:**

```python
class ExperimentRecord(BaseModel):
    program = models.ForeignKey('Program', ...)
    organization = models.ForeignKey('Organization', ...)
    user = models.ForeignKey('User', ...)
```

**After:**

```python
class ExperimentRecord(BaseModel):
    program_id = models.IntegerField(null=True, blank=True)
    organization_id = models.IntegerField(null=True, blank=True)
    user_id = models.IntegerField(null=True, blank=True)
```

**Rationale:**

- No dependency on local database organizations/programs/users
- Production IDs stored as integers can easily reference production data via OAuth
- When APIs are built, ForeignKeys can be added in production without changing data structure
- Aligns with labs principle: no sensitive local data, everything ephemeral

### 2. URL Structure Simplified

**Before (with org slugs):**

```
/a/{org_slug}/solicitations/program/{program_pk}/solicitations/create/
```

**After (no org slugs needed):**

```
/solicitations/                              # Home page
/solicitations/program/{program_pk}/create/  # Create (program from OAuth)
/solicitations/opportunities/                # Browse
/solicitations/responses/                    # My responses
```

### 3. New Landing Page & Navigation

Created `LabsHomeView` at `/solicitations/` that:

- Explains the lab project goals and architecture
- Provides clear navigation for Program Managers and Organizations
- Shows statistics (total solicitations, active opportunities, responses)
- Links to key actions: Create, Browse, Manage, Respond

### 4. New Views Added

1. **LabsHomeView** - Landing page with project explanation
2. **ProgramSelectView** - Select which program to create solicitation for (from OAuth data)
3. **ManageSolicitationsListView** - List of solicitations created by user
4. **MyResponsesListView** - List of responses/drafts from user's organization

### 5. Helper Functions Updated

All `experiment_helpers.py` functions now accept production IDs:

```python
# Before
create_solicitation_record(program, data_dict)

# After
create_solicitation_record(program_id, organization_id, user_id, data_dict)
```

### 6. Middleware Architecture

Created `LabsOrganizationMiddleware` that:

- Only runs for `LabsUser` (session-based OAuth users)
- Provides mock `request.org` and `request.org_membership` from OAuth session data
- Doesn't touch production `OrganizationMiddleware` code
- Clean separation of concerns

## How It Works Now

### Data Flow

1. **User logs in via OAuth** → Production Connect API provides orgs/programs/opportunities
2. **Data stored in session** → `LabsUser` object provides access via properties
3. **User creates solicitation** → Production program/org IDs stored as integers in `ExperimentRecord`
4. **Data is JSON-based** → Flexible, no complex ORM, easy to iterate
5. **Future API integration** → IDs can be used to fetch full objects from production API

### Creating a Solicitation

```
/solicitations/                            # Landing page
  ↓
/solicitations/programs/select/            # Choose program from OAuth data
  ↓
/solicitations/program/25/create/          # Create form (25 = production program ID)
  ↓
[Save] → ExperimentRecord created with:
  - program_id = 25 (production ID)
  - organization_id = 123 (production ID)
  - user_id = 456 (production ID)
  - data = {"title": "...", "description": "...", ...}
  ↓
/solicitations/manage/                     # List of user's solicitations
```

### Browsing & Responding

```
/solicitations/opportunities/              # Browse active solicitations
  ↓
/solicitations/opportunities/5/            # View solicitation details
  ↓
/solicitations/opportunities/5/respond/    # Submit response
  ↓
/solicitations/responses/                  # View my responses
```

## Files Modified

### Core Models & Helpers

- `commcare_connect/labs/models.py` - Updated `ExperimentRecord` fields
- `commcare_connect/solicitations/experiment_helpers.py` - Updated function signatures
- `commcare_connect/solicitations/views.py` - Added new views, updated existing
- `commcare_connect/solicitations/urls.py` - Simplified URL structure

### Middleware

- `commcare_connect/labs/organization_middleware.py` - NEW: Labs-specific org middleware
- `config/settings/local.py` - Updated to use labs middleware

### Templates

- `commcare_connect/templates/solicitations/labs_home.html` - NEW: Landing page
- `commcare_connect/templates/solicitations/program_select.html` - NEW: Program selection
- `commcare_connect/templates/solicitations/manage_list.html` - NEW: Manage solicitations
- `commcare_connect/templates/solicitations/my_responses.html` - NEW: View responses

### Migrations

- `commcare_connect/labs/migrations/0002_*.py` - Replaced ForeignKeys with IntegerFields

## Next Steps - Testing

### 1. Test Landing Page

Navigate to: `http://localhost:8000/solicitations/`

- Should see landing page with explanation
- Should see stats (counts)
- Should see links for both Program Managers and Organizations

### 2. Test Creating Solicitation

1. Navigate to `/solicitations/programs/select/`
2. Select a program from production data
3. Fill out solicitation form
4. Submit
5. Should redirect to `/solicitations/manage/` with success message

### 3. Test Browsing

1. Navigate to `/solicitations/opportunities/`
2. Should see active solicitations (if any created)
3. Filter by EOI/RFP
4. Click to view details

### 4. Test Responding

1. From solicitation detail page, click "Respond"
2. Fill out response form
3. Save as draft OR submit
4. View in `/solicitations/responses/`

## Technical Benefits

1. **No Local DB Dependencies** - Pure production data via OAuth
2. **Ephemeral** - Can reset/clear ExperimentRecords without affecting production
3. **Fast Iteration** - JSON data, no complex migrations needed
4. **API-Ready** - IDs are already structured for future API integration
5. **Clean Architecture** - Labs code separated from production middleware

## Production Migration Path

When moving to production APIs:

1. API returns full objects instead of just IDs
2. Replace IntegerFields with ForeignKeys in production
3. Migration script to link existing records (if needed)
4. No change to JSON data structure required

## Questions or Issues?

- **Q:** Why store IDs instead of full objects in JSON?
  **A:** Keeps data normalized and avoids duplication. IDs can be used to fetch current data from OAuth/API.

- **Q:** What if production program is deleted?
  **A:** ExperimentRecord remains with dangling ID. This is acceptable for labs (ephemeral data). Production API would handle this with proper cascade or soft delete.

- **Q:** How do templates display program names?
  **A:** Views fetch program data from `request.user.programs` (OAuth session) by matching IDs.
