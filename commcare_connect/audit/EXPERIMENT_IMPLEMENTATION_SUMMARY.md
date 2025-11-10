# Experiment-Based Audit Implementation Summary

## Overview

Successfully implemented an API-first data access layer for the Audit app using the ExperimentRecord pattern from Solicitations. This implementation runs in parallel with the existing Audit system, allowing for gradual migration.

## What Was Implemented

### 1. Proxy Models (`audit/experiment_models.py`)

Created 2 proxy models that provide convenient access to ExperimentRecord data:

- **AuditTemplateRecord**: Stores audit configuration (opportunity IDs, audit type, criteria, preview data)
- **AuditSessionRecord**: Stores audit state with nested visit results and assessments
  - Visit results are keyed by visit_id (UserVisit ID from Connect)
  - Each visit result contains xform_id, result, notes, and nested assessments
  - Helper methods for managing nested JSON structure:
    - `get_visit_result(visit_id)`
    - `set_visit_result(visit_id, xform_id, result, notes, user_id, opp_id)`
    - `get_assessments(visit_id)`
    - `set_assessment(visit_id, blob_id, question_id, result, notes)`
    - `get_progress_stats()`

### 2. Blob Metadata API (`audit/blob_api.py`)

Simulates blob metadata availability from Connect APIs by fetching from CommCare HQ:

- **BlobMetadataAPI**: Fetches form data and extracts blob metadata with question IDs
  - `get_blob_metadata_for_visit(xform_id, cc_domain)`: Returns dict mapping blob_id to metadata
  - `download_blob(blob_url)`: Downloads blob content from CommCare
  - Uses recursive search to extract question IDs from form JSON

### 3. Data Access Layer (`audit/data_access.py`)

Main data access class that wraps ExperimentRecordAPI and calls Connect OAuth APIs:

**Template Methods:**

- `create_audit_template(...)`
- `get_audit_template(template_id)`
- `get_audit_templates(user_id)`

**Session Methods:**

- `create_audit_session(template_id, auditor_id, visit_ids, title, tag, opportunity_id)`
- `get_audit_session(session_id)`
- `get_audit_sessions(auditor_id, status)`
- `save_audit_session(session)`
- `complete_audit_session(session, overall_result, notes, kpi_notes)`

**Visit Data Methods** (Fetch from Connect API):

- `get_visit_ids_for_audit(opportunity_ids, audit_type, criteria)`: Returns list of visit IDs
- `get_visit_data(visit_id, opportunity_id, visit_cache)`: Returns visit dict
- `get_visits_batch(visit_ids, opportunity_id)`: Batch fetch visits

**Blob Methods:**

- `get_blob_metadata_for_visit(xform_id, cc_domain)`: Delegates to BlobMetadataAPI
- `download_blob(blob_url)`: Delegates to BlobMetadataAPI

**API Helper Methods:**

- `search_opportunities(query, limit)`
- `get_opportunity_details(opportunity_id)`
- `_fetch_visits_for_opportunity(opportunity_id)`: Downloads CSV and parses

### 4. Experiment Views (`audit/experiment_views.py`)

Django views that reuse existing templates but swap the backend to use ExperimentRecords:

- **ExperimentAuditListView**: List all audit sessions
- **ExperimentAuditDetailView**: Main audit interface for reviewing visits
  - Fetches visit data dynamically from Connect API
  - Gets blob metadata from CommCare
  - Retrieves assessments from session JSON
- **ExperimentAuditResultUpdateView**: AJAX endpoint for updating visit results
- **ExperimentAssessmentUpdateView**: AJAX endpoint for updating image assessments
- **ExperimentAuditCompleteView**: Mark session as completed
- **ExperimentAuditImageView**: Serve images by downloading from CommCare
- **ExperimentAuditCreateAPIView**: Create audit sessions with background processing
- **ExperimentAuditPreviewAPIView**: Preview audit before creation

### 5. URL Routes (`audit/urls.py`)

Added parallel routes under `/audit/experiment/` prefix:

```
/audit/experiment/                            # List sessions
/audit/experiment/<id>/                       # Detail view
/audit/experiment/api/create/                 # Create session
/audit/experiment/api/preview/                # Preview
/audit/experiment/api/<id>/result/update/     # Update visit result
/audit/experiment/api/<id>/assessment/update/ # Update assessment
/audit/experiment/api/<id>/complete/          # Complete session
/audit/experiment/image/<blob_id>/            # Serve image
```

### 6. Integration Test (`audit/run_experiment_audit_integration.py`)

Complete integration test script that:

1. Initializes data access with OAuth token
2. Searches for opportunities
3. Previews audit and gets visit IDs
4. Creates template and session
5. Fetches visit data from Connect API
6. Gets blob metadata from CommCare
7. Sets assessments and visit results
8. Saves session
9. Checks progress
10. Verifies data structure (visit_results keyed by visit_id)
11. Completes audit session

## Architecture Highlights

### Data Flow

1. User creates audit → AuditTemplateRecord + AuditSessionRecord with visit_ids
2. User opens visit → Fetch visit from Connect API, fetch blobs from CommCare
3. User marks images → Update session.data["visit_results"] in memory
4. User clicks save → session.save() writes to DB
5. User completes → Final save with status="completed"

### Key Design Points

- **Visit results keyed by UserVisit ID** (from Connect API)
- **xform_id stored as property** within each visit result
- **All assessments nested** under visit result
- **Single ExperimentRecord per session** - efficient storage
- **In-memory updates, single write on save** - better performance
- **No local data syncing** - all data fetched dynamically from APIs

### Benefits

1. **API-first**: Matches production architecture
2. **Secure**: No stale local data, always fresh from APIs
3. **Efficient**: Single record per session with nested JSON
4. **Proven pattern**: Follows Solicitations implementation
5. **Parallel**: Existing audit system continues to work

## Next Steps

### 1. Testing

Run the integration test to verify everything works:

```bash
python commcare_connect/audit/run_experiment_audit_integration.py
```

### 2. Manual Testing

- Navigate to `/audit/experiment/` to see the experiment-based audit list
- Create a new audit session
- Conduct an audit and verify:
  - Visit data loads from Connect API
  - Images load from CommCare
  - Assessments save correctly
  - Progress tracking works
  - Session completion works

### 3. Verify Data Structure

Check that the JSON structure is correct:

```python
from commcare_connect.audit.experiment_models import AuditSessionRecord

session = AuditSessionRecord.objects.get(id=YOUR_SESSION_ID)

# Verify visit_results are keyed by visit_id
print(session.visit_results.keys())  # Should be ['123', '456', ...]

# Verify xform_id is stored
for visit_id, visit_result in session.visit_results.items():
    print(f"Visit {visit_id}: xform_id={visit_result.get('xform_id')}")
```

### 4. Migration Strategy

Once tested and stable:

1. Keep both implementations running in parallel
2. Gradually migrate users to experiment-based views
3. Compare results between old and new systems
4. Once confident, deprecate old system

### 5. Future Enhancements

- Add caching for visit data to reduce API calls
- Implement batch operations for better performance
- Add export functionality for experiment-based sessions
- Create UI for switching between old/new implementations

## Files Created

1. `commcare_connect/audit/experiment_models.py` - Proxy models
2. `commcare_connect/audit/blob_api.py` - Blob metadata API
3. `commcare_connect/audit/data_access.py` - Data access layer
4. `commcare_connect/audit/experiment_views.py` - Django views
5. `commcare_connect/audit/urls.py` - URL routes (modified)
6. `commcare_connect/audit/run_experiment_audit_integration.py` - Integration test
7. `commcare_connect/audit/EXPERIMENT_IMPLEMENTATION_SUMMARY.md` - This file

## Dependencies

### Required Environment Variables

- `COMMCARE_USERNAME` - CommCare API username
- `COMMCARE_API_KEY` - CommCare API key
- `CONNECT_PRODUCTION_URL` - Connect production URL (from settings)

### Required User Setup

- User must have a Connect OAuth token (via labs mode or SocialAccount)
- CommCare credentials must be configured for blob fetching

## Troubleshooting

### "OAuth access token required"

- Ensure user has authenticated with Connect
- In labs mode, check session for labs_oauth token
- In normal mode, check SocialAccount/SocialToken exists

### "No cc_domain found for opportunity"

- The opportunity details API may not return cc_domain
- Check `get_opportunity_details()` implementation
- May need to fetch from a different API endpoint

### "Could not fetch blob metadata"

- Verify COMMCARE_USERNAME and COMMCARE_API_KEY are set
- Check that xform_id is valid
- Verify cc_domain is correct for the opportunity

### "No visits found matching criteria"

- Check that the opportunity has approved visits
- Verify date range or count criteria are appropriate
- Try with a different opportunity or broader criteria
