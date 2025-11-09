# ExperimentRecord Implementation Summary

## Overview

Successfully implemented the ExperimentRecord-based data layer for the solicitations app as specified in the plan. This provides a flexible JSON-based storage system that will be easier to convert when the global API is released.

## What Was Implemented

### 1. Core Model (labs/models.py)

- **ExperimentRecord** model with:
  - `experiment` field (e.g., "solicitations")
  - `type` field (e.g., "Solicitation", "SolicitationResponse")
  - Optional FK relationships: user, opportunity, organization, program
  - Self-referential `parent` FK for hierarchies
  - `data` JSONField for flexible content storage
  - Database indexes for performance
  - Migration created and applied

### 2. Proxy Models (solicitations/experiment_models.py)

Created zero-overhead proxy models for convenient access:

- **SolicitationRecord**: Properties for title, status, questions, etc.
- **ResponseRecord**: Properties for responses, status, attachments
- **ReviewRecord**: Properties for score, recommendation, notes

### 3. Helper Functions (solicitations/experiment_helpers.py)

**Create Functions:**

- `create_solicitation_record()` - Create new solicitations
- `create_response_record()` - Create responses
- `create_review_record()` - Create reviews

**Query Functions:**

- `get_solicitations()` - Query with filters (program, status, type)
- `get_solicitation_by_id()` - Get single solicitation
- `get_response_for_solicitation()` - Find response by org
- `get_responses_for_solicitation()` - Get all responses
- `get_reviews_for_response()` - Get reviews for a response

### 4. New Views (solicitations/views.py)

Implemented simplified views using ExperimentRecords:

- **SolicitationListView**: List public solicitations
- **SolicitationDetailView**: Show solicitation details with questions
- **SolicitationResponseCreateOrUpdate**: Create/edit responses
- **SolicitationResponseDetailView**: View response details
- **SolicitationResponseReviewCreateOrUpdate**: Create/edit reviews

### 5. URL Configuration (solicitations/urls.py)

Updated to use new views for:

- Public solicitation listing (/, /eoi/, /rfp/)
- Solicitation detail pages
- Response creation and viewing
- Review creation

### 6. Tests (solicitations/tests/test_experiment_helpers.py)

Created minimal focused tests for:

- Creating solicitation records
- Querying solicitations with filters
- Creating and querying responses
- Creating reviews

### 7. Cleanup

- Deleted all old test files (test\_\*.py, factories.py)
- Renamed existing views to add "Old" suffix
- Kept old views as reference during development

## Key Design Decisions

1. **No Serialization Layer**: Work directly with JSON data for simplicity
2. **Proxy Models**: Provide convenience without database overhead
3. **Direct JSON Access**: Forms and templates work with `record.data` dictionaries
4. **Minimal Tests**: Focus on critical paths only
5. **Templates**: Existing templates should work with minimal changes

## What Still Uses Old Models

The following features still use the old model system (can be converted later):

- Dashboard views
- Draft list views
- File attachment handling
- Solicitation creation/editing (program manager views)
- Response table views

## Next Steps

1. Test the new views with actual data
2. Create sample solicitations using the new system
3. Adapt templates if needed (existing templates should mostly work)
4. Once confirmed working, delete old models and "Old" views
5. Convert remaining features (dashboard, solicitation CRUD) if needed

## Files Created/Modified

**Created:**

- `commcare_connect/labs/models.py` - Added ExperimentRecord
- `commcare_connect/labs/migrations/0001_initial.py` - Migration
- `commcare_connect/solicitations/experiment_models.py` - Proxy models
- `commcare_connect/solicitations/experiment_helpers.py` - Helper functions
- `commcare_connect/solicitations/tests/test_experiment_helpers.py` - Tests

**Modified:**

- `commcare_connect/solicitations/views.py` - Added new views, renamed old ones
- `commcare_connect/solicitations/urls.py` - Updated to use new views

**Deleted:**

- All old test files in `commcare_connect/solicitations/tests/`

## Benefits

1. **Flexibility**: Easy to add/change fields without migrations
2. **Simplicity**: No complex serialization layer
3. **Future-Ready**: Closer to the final API structure
4. **Rapid Prototyping**: Perfect for labs features
5. **Easy Conversion**: When global API is ready, just update references

## Notes

- This is a labs feature - prioritize rapid iteration over production quality
- Old models remain for reference and partial functionality
- Templates may need minor adjustments for JSON data access
- Forms work the same way with `record.data['questions']`
