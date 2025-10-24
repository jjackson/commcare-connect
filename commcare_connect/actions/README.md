# Actions App - Prototype Documentation

## Overview

The Actions app is a prototype system for tracking and managing actions taken against Field-Level Workers (FLWs) based on various triggers (currently audit failures, but designed to support other sources like compliance issues, performance flags, or manual interventions).

**Status:** PROTOTYPE - No database models implemented yet. All data is mocked for UI exploration.

## ⭐ Streamlined View (Default)

**URL:** `/actions/<id>/` (default "View" button)

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

**URL:** `/actions/<id>/enhanced/`

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

- `/actions/` - Main list view with filtering and statistics
- `/actions/<id>/` - **Streamlined view (default) - action-focused**
- `/actions/<id>/v2/` - Simplified view with progress bar
- `/actions/<id>/enhanced/` - Enhanced modern UI with advanced features
- `/actions/<id>/timeline/` - Timeline-based prototype
- `/actions/<id>/cards/` - Card-based workflow prototype
- `/actions/<id>/split/` - Split-panel with history sidebar prototype

## View Descriptions

### ⭐ Streamlined View (`/actions/<id>/`) - DEFAULT

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

### Simplified View (`/actions/<id>/v2/`)

**Focus:** Clarity with visual workflow

**Features:**

- Visual progress bar showing workflow stage
- "What Happened" summary card
- Human events highlighted, system events hidden
- Past issues collapsed
- Single scrollable page (no tabs)

**Best For:** Understanding workflow progression, visual learners.

### Enhanced View (`/actions/<id>/enhanced/`) - POWER USERS

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

### 1. Timeline View (`/actions/<id>/timeline/`)

**Focus:** Chronological activity feed

**Features:**

- Vertical timeline showing all events in order
- Color-coded event types (creation, notifications, status changes, comments)
- Activity feed at the center of the interface
- FLW history shown below timeline
- Notification details at bottom

**Best For:** Users who think in terms of "what happened when" and want a clear audit trail.

### 2. Cards View (`/actions/<id>/cards/`)

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

### 3. Split Panel View (`/actions/<id>/split/`)

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

## Files

```
commcare_connect/actions/
├── __init__.py
├── apps.py              # App configuration
├── urls.py              # URL routing
├── views.py             # Mock views with sample data
└── README.md            # This file

commcare_connect/templates/actions/
├── actions_list.html                  # Main list page
├── action_detail_streamlined.html     # ⭐ Streamlined view (default)
├── action_detail_simplified.html      # Simplified view with progress bar
├── action_detail_enhanced.html        # Enhanced modern UI
├── action_detail_timeline.html        # Prototype 1
├── action_detail_cards.html           # Prototype 2
└── action_detail_split.html           # Prototype 3
```

## Next Steps (When Moving to Production)

1. **Create Models:**

   - `Action` model with status, type, priority fields
   - Link to FLW user, opportunity, audit session
   - Track created_by, assigned_to
   - Store timeline as related `ActionEvent` records

2. **Implement Real Notifications:**

   - Email/SMS to FLWs
   - In-app notifications to Network Managers
   - Delivery tracking

3. **Add Permissions:**

   - PM can create/edit/resolve actions
   - NM can comment and request reactivations
   - Admins have full access

4. **Automation:**

   - Auto-create actions from audit failures
   - Auto-close after resolution period
   - Escalation rules based on patterns

5. **Integrate with Existing Systems:**
   - Link to audit sessions
   - Connect to opportunity access management
   - Track in user profiles

## Testing the Prototypes

1. Start the development server: `python manage.py runserver`
2. Navigate to `/actions/`
3. Click the prototype icons (stream/cards/columns) to view different layouts
4. Use filters to see different subsets of actions
5. Gather feedback on which approach works best for your workflows

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
