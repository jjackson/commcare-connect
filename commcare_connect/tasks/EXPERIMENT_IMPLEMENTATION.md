# ExperimentRecord Implementation Summary - Tasks

## Overview

Successfully converted the tasks app from Django ORM models to the ExperimentRecord-based labs pattern, aligning with the audit and solicitations implementations. This provides OAuth-based API access and makes tasks a proper labs experiment.

**Key Design Decision:** Username is the primary unique identifier for users in Connect, not user_id. The Connect data export API (`/export/opportunity/<id>/user_data/`) provides username but not user_id, so all task operations use username as the main identifier.

## What Was Implemented

### 1. Proxy Models (`tasks/experiment_models.py`)

Created TaskRecord proxy model for convenient access to ExperimentRecord data:

**TaskRecord** - Main task storage with nested events, comments, and AI sessions

- Properties for all task fields (user_id, opportunity_id, task_type, status, priority, etc.)
- Properties for nested data (events, comments, ai_sessions)
- Helper methods:
  - `add_event(event_type, actor, actor_user_id, description, **kwargs)`
  - `add_comment(author_id, author_name, content)`
  - `add_ai_session(ocs_session_id, **kwargs)`
  - `get_timeline()` - Combined events + comments sorted by timestamp
  - `get_status_display()`, `get_task_type_display()`, `get_priority_display()`

**Key data structure:**

```json
{
  "username": "user123",
  "user_id": 123,
  "opportunity_id": 456,
  "task_type": "warning",
  "status": "unassigned",
  "priority": "medium",
  "title": "...",
  "description": "...",
  "learning_assignment_text": "...",
  "audit_session_id": 789,
  "assigned_to_id": 321,
  "created_by_id": 100,
  "events": [
    {
      "event_type": "created",
      "actor": "John Doe",
      "actor_user_id": 100,
      "description": "...",
      "timestamp": "2024-11-10T...",
      "metadata": {},
      "ai_session_id": null
    }
  ],
  "comments": [
    {
      "author_id": 100,
      "author_name": "John Doe",
      "content": "...",
      "timestamp": "2024-11-10T..."
    }
  ],
  "ai_sessions": [
    {
      "session_id": "uuid-here",
      "ocs_session_id": "ocs-123",
      "status": "completed",
      "timestamp": "2024-11-10T...",
      "metadata": {}
    }
  ]
}
```

### 2. Data Access Layer (`tasks/data_access.py`)

Main data access class that wraps ExperimentRecordAPI and integrates with Connect OAuth APIs:

**TaskDataAccess class:**

- Constructor: `__init__(user=None, request=None, access_token=None)` - for OAuth token extraction
- Task CRUD:
  - `create_task(username, opportunity_id, created_by_id, user_id=None, **kwargs)` → TaskRecord
    - **username** is the primary identifier (always available from Connect API)
    - **user_id** is optional (not available from /export/ endpoints)
  - `get_task(task_id)` → TaskRecord | None
  - `get_tasks(username, user_id, opportunity_id, status, assigned_to_id)` → QuerySet
  - `save_task(task_record)` → TaskRecord
- Task operations:
  - `add_event(task, event_type, actor, actor_user_id, description, **kwargs)`
  - `add_comment(task, author_id, author_name, content)`
  - `add_ai_session(task, ocs_session_id, **kwargs)`
  - `update_status(task, new_status, actor, actor_user_id)`
  - `assign_task(task, assigned_to_id, actor, actor_user_id)`
- Connect API integration (via OAuth httpx client):
  - `search_opportunities(query, limit)` → list
  - `get_opportunity_details(opportunity_id)` → dict
  - `get_users_from_opportunity(opportunity_id)` → list[dict]
    - Uses `/export/opportunity/<id>/user_data/` endpoint
    - Returns usernames (user_id not available from this API)

### 3. Views (`tasks/views.py`)

Django views using TaskRecord instead of Django ORM models:

**Class-based views:**

- `TaskListView` - List tasks with filters and statistics
- `TaskDetailView` - Single task detail with streamlined UI
- `TaskCreationWizardView` - Task creation wizard
- `DatabaseStatsAPIView` - Database statistics
- `DatabaseResetAPIView` - Reset tasks database

**API views:**

- `TaskCreateAPIView` - Bulk create tasks
- `TaskUpdateAPIView` - Quick update (status/assignment/priority)
- `TaskAddCommentAPIView` - Add comments
- `TaskInitiateAIAPIView` - Initiate AI conversations via OCS
- `TaskAISessionsAPIView` - Get AI sessions
- `TaskAITranscriptAPIView` - Fetch AI transcript from OCS
- `OpportunitySearchAPIView` - Search opportunities (OAuth)
- `OpportunityFieldWorkersAPIView` - Get field workers (OAuth)

Pattern: Reuse existing template structure, swap backend to TaskDataAccess.

### 4. URL Routes (`tasks/urls.py`)

Replaced all URLs to point to new ExperimentRecord-based views:

```
/tasks/                                          # List tasks
/tasks/create/                                   # Creation wizard
/tasks/<id>/                                     # Task detail
/tasks/api/<id>/update/                          # Quick update
/tasks/api/<id>/comment/                         # Add comment
/tasks/api/<id>/ai/initiate/                     # Initiate AI
/tasks/api/<id>/ai/sessions/                     # Get AI sessions
/tasks/api/<id>/ai/transcript/                   # Get transcript
/tasks/api/opportunities/search/                 # Search opportunities
/tasks/api/opportunities/<id>/field-workers/     # Get field workers
/tasks/api/tasks/bulk-create/                    # Bulk create
/tasks/api/database/stats/                       # Database stats
/tasks/api/database/reset/                       # Reset database
```

### 5. Helper Functions (`tasks/helpers.py`)

Simplified helpers using TaskDataAccess:

- `get_user_tasks_queryset(user)` - Get tasks user can access (OAuth enforces)
- `create_task_from_audit(...)` - Create task from audit trigger

Note: Removed `user_can_access_task()` - not needed since OAuth API enforces access.

### 6. Integration Test (`tasks/run_experiment_task_integration.py`)

Complete integration test that:

1. Initializes TaskDataAccess with OAuth token
2. Searches for opportunities via Connect API
3. Gets field workers via Connect API
4. Creates a task
5. Adds events
6. Adds comments
7. Updates status
8. Assigns task
9. Adds AI session
10. Verifies nested JSON structure
11. Tests get_timeline() helper
12. Queries tasks with filters
13. Verifies OAuth-enforced permissions

## Architecture Highlights

### Data Flow

1. User creates task → TaskRecord created in ExperimentRecord
2. User adds event/comment → Nested in task.data, single write
3. User updates status → TaskDataAccess updates status + adds event
4. User assigns task → TaskDataAccess updates assignment + adds event
5. User queries tasks → OAuth API enforces access control

### Key Design Points

- **Nested JSON for events/comments/AI sessions**: All stored as arrays in task.data
- **OAuth API is source of truth**: No local permission checks needed
- **No local ForeignKeys**: Store IDs as integers (user_id, opportunity_id, etc.)
- **Single ExperimentRecord per task**: Efficient storage with nested structure
- **In-memory updates, single write on save**: Better performance
- **ConnectAPIFacade for API access**: OAuth-based opportunity/user lookups

### Benefits

1. **API-ready**: Data structure matches future global API
2. **Flexible**: Easy to add fields without migrations
3. **OAuth-native**: Works with Connect API authentication
4. **Correct permissions**: OAuth API enforces access, no local bypass
5. **Rapid iteration**: JSON storage enables quick schema changes
6. **Labs-appropriate**: Perfect for throwaway prototypes
7. **Simplified**: No complex model relationships, just JSON

## Files Created/Modified

**Renamed (for reference only):**

- `tasks/models.py` → `tasks/models_old.py`
- `tasks/views.py` → `tasks/views_old.py`
- `tasks/forms.py` → `tasks/forms_old.py`
- `tasks/helpers.py` → `tasks/helpers_old.py`

**Created:**

- `tasks/experiment_models.py` - TaskRecord proxy model
- `tasks/data_access.py` - TaskDataAccess layer
- `tasks/views.py` (new) - ExperimentRecord-based views
- `tasks/helpers.py` (new) - Simplified helpers
- `tasks/run_experiment_task_integration.py` - Integration test
- `tasks/EXPERIMENT_IMPLEMENTATION.md` - This file

**Modified:**

- `tasks/urls.py` - Updated to use new views
- `labs/models.py` - Fixed LabsUser.is_superuser (changed to False)

## Testing

### Run Integration Test

```bash
# Set OAuth token
python manage.py get_cli_token  # Save token
# OR
export CONNECT_OAUTH_TOKEN="your-token-here"

# Run integration test
python commcare_connect/tasks/run_experiment_task_integration.py
```

The test will:

- Search for opportunities
- Get field workers
- Create a task
- Add events, comments, AI sessions
- Update status and assignment
- Verify data structure
- Test querying and filtering

### Manual Testing

1. Navigate to `/tasks/` to see task list
2. Click "Create Task" to open creation wizard
3. Create a new task
4. View task detail and verify:
   - Events display correctly
   - Comments can be added
   - Status can be updated
   - Assignment works
   - Timeline combines events + comments

## Permission Model

**OAuth API is source of truth:**

- No `can_user_access()` method on TaskRecord
- No local permission checks in views
- TaskDataAccess queries return only tasks user has access to (enforced by OAuth API)
- If you have a TaskRecord reference, you already have access

**LabsUser changes:**

- `is_superuser` changed from `True` to `False`
- Permissions come from OAuth API, not local bypass

## Next Steps

1. **Test thoroughly** - Run integration test and manual testing
2. **Delete old code** - Once confirmed working, delete `*_old.py` files
3. **Add features** - Easy to add new fields to JSON structure
4. **Monitor performance** - Add indexes if needed based on query patterns
5. **Consider caching** - Cache Connect API results if performance becomes an issue

## Troubleshooting

### "OAuth access token required"

- Ensure user has authenticated with Connect
- In labs mode, check session for labs_oauth token
- In normal mode, check SocialAccount/SocialToken exists
- Run `python manage.py get_cli_token` to save token

### "No opportunities/field workers found"

- Verify OAuth token has correct permissions
- Check that Connect API is accessible
- Try with a different search query

### "Task not found"

- Verify task ID exists in ExperimentRecord table
- Check experiment="tasks" and type="Task"
- Verify user has access (OAuth enforced)

### Views not working

- Check that urls.py imports new views (not old)
- Verify templates are compatible with new data structure
- Check TaskDataAccess initialization (needs user/request)

## Migration Notes

This is a labs experiment - the old Django ORM code is kept for reference only:

- Old models in `models_old.py` are NOT used
- Old views in `views_old.py` are NOT accessible via URLs
- Old helpers in `helpers_old.py` are NOT imported
- Old forms in `forms_old.py` are NOT used

The new ExperimentRecord-based implementation is now the primary and only accessible version.
