# Tasks App - Documentation

## Overview

The Tasks app is a labs experiment for tracking and managing actions taken against Field-Level Workers (FLWs) based on various triggers (currently audit failures, but designed to support other sources like compliance issues, performance flags, or manual interventions).

**Status:** ✅ LABS EXPERIMENT - Now using ExperimentRecord pattern with OAuth-based API access.

**Implementation:** This app now uses the ExperimentRecord-based architecture (same as audit and solicitations apps). See `EXPERIMENT_IMPLEMENTATION.md` for detailed technical documentation.

**Key Changes:**

- Uses ExperimentRecord for JSON-based storage instead of Django ORM models
- OAuth-based API access via Connect production APIs
- No local permission checks (OAuth API is source of truth)
- Events, comments, and AI sessions stored as nested JSON
- Old Django ORM code preserved in `*_old.py` files for reference only

## ⭐ Streamlined View (Default)

**URL:** `/tasks/<id>/` (default "View" button)

The **Streamlined View** is an action-focused inbox designed for quick decisions. No complex workflows—just **assign or contact** in 2 clicks.

### Key Features:

- **3 big action buttons**: Assign to NM, Assign to PM, Contact Worker (SMS/Call/Email)
- **One-click actions**: Modals open for quick assignment or contact
- **"What Happened" summary**: Understand the issue in plain language instantly
- **FLW header card**: Worker name, issue type, and opportunity in colored banner
- **Collapsible history**: Past issues available when needed (amber warning if present)
- **Simple conversation**: Just notes and comments, no system noise
- **Mark as Resolved**: Green button when issue is complete
- **Mobile-friendly**: Large touch targets, minimal navigation

📖 **See `STREAMLINED_SUMMARY.md` for detailed rationale and user flows.**

---

## Enhanced View (Alternative)

**URL:** `/tasks/<id>/enhanced/`

The **Enhanced Modern UI** incorporates best practices from leading ticketing systems (Linear, Jira, Zendesk). Available for power users who prefer more features.

### Key Features:

- **Clickable workflow buttons**: One-click status changes
- **Inline editing**: Hover over fields to edit
- **Keyboard shortcuts**: C, Ctrl+Enter, ?, Esc, etc.
- **Quick actions bar**: Shortcuts, Assign, Share
- **Tabbed content**: Activity, Details, Notification tabs
- **All events visible**: Full timeline without filtering
- **Compact information density**: More on screen

📖 **See `ENHANCED_UI_PATTERNS.md` and `UI_OBSERVATIONS_AND_IDEAS.md` for detailed documentation.**

## Purpose

This app provides three different UI prototypes to explore how Program Managers and Network Managers can:

- Track actions (warnings, deactivations, etc.) triggered by audit failures
- Review FLW history and context
- Communicate and collaborate on resolutions
- Make decisions about next steps

## Workflow States

Actions flow through these states:

1. **Open** - Newly created action awaiting review
2. **NM Review** - Network Manager is reviewing and responding
3. **PM Review** - Program Manager is reviewing NM input
4. **Resolved** - Issue resolved, FLW back in good standing
5. **Closed** - Action completed (may or may not be resolved)

## Action Types

- **Warning**: System sends notification to FLW, NM is notified (can comment)
- **Deactivation**: User temporarily deactivated from opportunity, NM can request reactivation

## URL Structure

- `/tasks/` - Main list view with filtering and statistics
- `/tasks/<id>/` - **Streamlined view (default) - action-focused**
- `/tasks/<id>/v2/` - Simplified view with progress bar
- `/tasks/<id>/enhanced/` - Enhanced modern UI with advanced features
- `/tasks/<id>/timeline/` - Timeline-based prototype
- `/tasks/<id>/cards/` - Card-based workflow prototype
- `/tasks/<id>/split/` - Split-panel with history sidebar prototype

## View Descriptions

### ⭐ Streamlined View (`/tasks/<id>/`) - DEFAULT

**Focus:** Action-first interface for getting things done

**Features:**

- 3 primary action buttons (Assign NM, Assign PM, Contact Worker)
- Modals for quick assignment or contact (SMS/Call/Email)
- FLW header card with issue context
- "What Happened" summary in plain language
- Collapsible past issues (amber warning)
- Simple conversation thread (human events only)
- "Mark as Resolved" button
- 2 clicks to act

**Best For:** Low-volume usage, quick decisions, users who need to assign or contact. No training needed.

### Simplified View (`/tasks/<id>/v2/`)

**Focus:** Clarity with visual workflow

**Features:**

- Visual progress bar showing workflow stage
- "What Happened" summary card
- Human events highlighted, system events hidden
- Past issues collapsed
- Single scrollable page (no tabs)

**Best For:** Understanding workflow progression, visual learners.

### Enhanced View (`/tasks/<id>/enhanced/`) - POWER USERS

**Focus:** Modern ticketing best practices

**Features:**

- Clickable workflow buttons
- All events always visible
- Inline editing capabilities
- Keyboard shortcuts
- Quick actions bar
- Tabbed content organization
- Compact information density

**Best For:** Power users who want more control and faster workflows.

## Original Prototype Descriptions

### 1. Timeline View (`/tasks/<id>/timeline/`)

**Focus:** Chronological activity feed

**Features:**

- Vertical timeline showing all events in order
- Color-coded event types (creation, notifications, status changes, comments)
- Activity feed at the center of the interface
- FLW history shown below timeline
- Notification details at bottom

**Best For:** Users who think in terms of "what happened when" and want a clear audit trail.

### 2. Cards View (`/tasks/<id>/cards/`)

**Focus:** Modular, task-oriented layout

**Features:**

- Grid of cards, each with a specific purpose:
  - Current Status card with quick actions
  - Assignment & Team card
  - Audit Context card
  - FLW History card
  - NM Response card
  - PM Actions card
  - Full-width Notification card
- Self-contained sections
- Clear visual separation of concerns

**Best For:** Users who want to see all relevant information at once and prefer to navigate between different aspects visually.

### 3. Split Panel View (`/tasks/<id>/split/`)

**Focus:** Historical context alongside current details

**Features:**

- Left sidebar (40%): FLW profile with scrollable history of all past actions
- Right panel (60%): Current action details with tabbed interface
  - Details tab
  - Activity tab
  - Notification tab
  - Actions tab
- Easy comparison with past incidents
- Context always visible

**Best For:** Users who need to frequently reference FLW history when making decisions about current actions.

## Mock Data

The views generate comprehensive mock data including:

- 15 sample action tickets with varying statuses, types, and dates
- Multiple FLWs across different opportunities
- Timeline events with timestamps and actors
- Sample notifications sent to FLWs
- Historical tickets for context

## Technology Stack

- **Backend:** Django views with Python-generated mock data
- **Frontend:**
  - TailwindCSS for styling (following existing Connect patterns)
  - Alpine.js for interactive elements (filters, tabs)
  - Font Awesome icons
- **Templates:** Django templates extending `base.html`

## Styling Consistency

All templates follow existing CommCare Connect patterns:

- Brand colors: `bg-brand-indigo`, `bg-brand-deep-purple`
- Button styles: `button button-md primary-dark`
- Stats cards layout from `audit/bulk_assessment.html`
- Table patterns from `opportunity/opportunities_list.html`

## Architecture

### ExperimentRecord Pattern

This app uses the ExperimentRecord pattern for data storage:

- **TaskRecord** proxy model provides convenient access to JSON data
- **TaskDataAccess** layer wraps ExperimentRecordAPI and ConnectAPIFacade
- All task data stored in single JSON field with nested events/comments/AI sessions
- OAuth-based access control (no local permission checks)

### Data Flow

1. User creates task → TaskRecord stored in ExperimentRecord table
2. User adds event/comment → Nested in task.data JSON, single DB write
3. User queries tasks → OAuth API enforces access control
4. User gets opportunities/FLWs → Fetched from Connect API via OAuth

## Files

### Active Implementation (ExperimentRecord-based)

```
commcare_connect/tasks/
├── experiment_models.py              # TaskRecord proxy model
├── data_access.py                    # TaskDataAccess layer
├── views.py                          # ExperimentRecord-based views
├── helpers.py                        # Simplified helper functions
├── urls.py                           # URL routing (points to new views)
├── run_experiment_task_integration.py # Integration test
├── EXPERIMENT_IMPLEMENTATION.md      # Technical documentation
└── README.md                         # This file
```

### Reference Only (Old Django ORM code)

```
commcare_connect/tasks/
├── models_old.py          # Old Django models (not used)
├── views_old.py           # Old views (not accessible)
├── forms_old.py           # Old forms (not used)
└── helpers_old.py         # Old helpers (not used)
```

### Templates (Reused with new backend)

```
commcare_connect/templates/tasks/
├── tasks_list.html                   # Main list page
├── task_detail_streamlined.html      # ⭐ Streamlined view (default)
├── task_creation_wizard.html         # Creation wizard
└── (other prototype templates)       # Various UI experiments
```

## Data Model (ExperimentRecord-based)

### Core Structure

**TaskRecord** - Single ExperimentRecord with nested JSON data:

- Fields: user_id, opportunity_id, task_type, status, priority, title, description
- Nested arrays: events[], comments[], ai_sessions[]
- All data stored in single `data` JSON field
- No separate tables for events/comments/AI sessions

### Data Structure

```json
{
  "user_id": 123,
  "opportunity_id": 456,
  "task_type": "warning",
  "status": "unassigned",
  "priority": "medium",
  "title": "Task Title",
  "description": "Task Description",
  "events": [
    {
      "event_type": "created",
      "actor": "John Doe",
      "actor_user_id": 100,
      "description": "Task created",
      "timestamp": "2024-11-10T12:00:00",
      "metadata": {}
    }
  ],
  "comments": [
    {
      "author_id": 100,
      "author_name": "John Doe",
      "content": "Comment text",
      "timestamp": "2024-11-10T12:05:00"
    }
  ],
  "ai_sessions": [
    {
      "ocs_session_id": "session-123",
      "status": "completed",
      "timestamp": "2024-11-10T12:10:00",
      "metadata": {}
    }
  ]
}
```

### Features Implemented

✅ **OAuth-based access control** (no local permission checks)
✅ **CRUD operations** via TaskDataAccess layer
✅ **Event tracking** for audit trail (nested JSON)
✅ **AI assistant integration** via OCS API
✅ **Comment system** for collaboration (nested JSON)
✅ **Connect API integration** for opportunities/FLWs
✅ **Integration test** for full workflow
✅ **Helper API** for automation (create_task_from_audit)

### Quick Start

Create a task programmatically using the new ExperimentRecord pattern:

```python
from commcare_connect.tasks.helpers import create_task_from_audit

# Create task from audit trigger
task = create_task_from_audit(
    audit_session_id=2058,
    user_id=123,  # FLW user ID
    opportunity_id=456,  # Opportunity ID
    task_type="warning",
    description="Photo quality issues detected",
    created_by_id=100,  # PM user ID
    priority="high",
    title="Photo Quality Issue",
)
```

Or use TaskDataAccess directly:

```python
from commcare_connect.tasks.data_access import TaskDataAccess

data_access = TaskDataAccess(user=request.user, request=request)

task = data_access.create_task(
    user_id=123,
    opportunity_id=456,
    created_by_id=100,
    task_type="warning",
    priority="high",
    title="Photo Quality Issue",
    description="Photos show poor lighting",
    creator_name="Program Manager",
)

# Add event
data_access.add_event(
    task,
    event_type="pattern_detected",
    actor="System",
    actor_user_id=100,
    description="3rd quality issue in 2 weeks",
)

# Add comment
data_access.add_comment(
    task,
    author_id=100,
    author_name="PM Name",
    content="Following up with Network Manager",
)

data_access.close()
```

Or create via the web interface at `/tasks/create/`.

## Testing

### Run Integration Test

```bash
# Get OAuth token
python manage.py get_cli_token

# Run integration test
python commcare_connect/tasks/run_experiment_task_integration.py
```

The test will create a task, add events/comments, update status, and verify the data structure.

## Next Steps

1. **Test the new implementation**: Run integration test and manual testing
2. **Configure OCS**: Add OCS_BASE_URL, OCS_API_KEY, OCS_BOT_ID to settings for AI assistant
3. **Integrate with Audit**: Hook up `create_task_from_audit()` to audit failures
4. **Delete old code**: Once confirmed working, delete `*_old.py` files
5. **Monitor Performance**: Add indexes if needed based on query patterns

## Technical Documentation

For detailed technical documentation about the ExperimentRecord implementation, see:

- **`EXPERIMENT_IMPLEMENTATION.md`** - Complete implementation details, architecture, data flow
- **`run_experiment_task_integration.py`** - Integration test showing complete workflow

## Testing and Development

### Create Sample Tasks

Use the task creation script to create realistic sample data:

```bash
# Create Task #1001 (Reading Glasses Nigeria)
python commcare_connect/tasks/run_task_creation.py readers_nigeria

# Create multiple warning tasks
python commcare_connect/tasks/run_task_creation.py multiple_warnings

# Create escalation pattern
python commcare_connect/tasks/run_task_creation.py escalation_pattern

# Create AI interaction tasks
python commcare_connect/tasks/run_task_creation.py ai_interactions
```

See [MANAGEMENT_COMMANDS.md](MANAGEMENT_COMMANDS.md) for detailed documentation.

### Clear Tasks Data

To reset the database:

```bash
python manage.py clear_tasks --yes
```

### View Tasks

1. Start the development server: `python manage.py runserver`
2. Navigate to `/tasks/` for the list view
3. Click on any task to see the streamlined detail view
4. Use filters to see different subsets of tasks
5. Test create/update forms at `/tasks/create/`

### Database Status Panel

The tasks list page includes a "Database Status" panel at the bottom showing:

- Number of tasks
- Number of events
- Number of comments
- Number of AI sessions

Click the "Clear Tasks Database" button to remove all tasks data (with confirmation prompt). This is useful for:

- Resetting test data
- Cleaning up after development
- Starting fresh with new sample data

The clear operation preserves users, organizations, and opportunities - only task-specific data is removed.

## Design Decisions

- **No Database:** Keeping prototypes separate from production data allows free exploration
- **Three Approaches:** Each prototype emphasizes different aspects (chronology, modularity, context)
- **Realistic Data:** Mock data includes edge cases and various scenarios
- **Consistent Styling:** Follows existing patterns for seamless integration later
- **Alpine.js:** Lightweight interactivity without separate JS files (per project standards)

## Feedback Questions

When testing these prototypes, consider:

1. Which layout makes it easiest to understand the current situation?
2. Which view best supports decision-making about next actions?
3. Is historical context prominent enough (or too prominent)?
4. Are the action buttons clear and appropriately placed?
5. What additional information would be helpful?
