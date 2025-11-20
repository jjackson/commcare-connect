# Labs Context Selection Implementation

## Overview

Implemented a unified context selection system for CommCare Connect Labs that allows users to select organization, program, or opportunity context across all labs projects (tasks, solicitations, audit).

## Key Features

1. **Single Global Context**: One context applies across all labs projects
2. **URL-Based**: Context represented as query parameters (`?opportunity_id=123&program_id=456`)
3. **Session Backup**: Context stored in session for convenience
4. **Auto-Selection**: Automatically selects context when user has exactly one option
5. **Header Integration**: Context selector integrated into main header navigation
6. **Validation**: Ensures user has access to selected context

## Implementation Details

### 1. Middleware (`commcare_connect/labs/context.py`)

**LabsContextMiddleware** handles:

- Extracting context from URL parameters
- Loading context from session when URL params absent
- **Redirecting to add session context to URL** (makes context visible and bookmarkable)
- Validating user access to selected context
- Auto-selecting when user has exactly one relevant context
- Updating session with current context

**Key Functions**:

- `extract_context_from_url()` - Parse context params from URL
- `validate_context_access()` - Verify user has access to context
- `try_auto_select_context()` - Auto-select if user has exactly one option
- `add_context_to_url()` - Add context params to any URL

### 2. Header Component (`commcare_connect/templates/labs/context_selector.html`)

**Features**:

- Dropdown selector in header (where "Connect Labs" branding is)
- Shows current context (e.g., "Opp: CHW Training | Program: Health Workers")
- Lists all available organizations, programs, and opportunities
- "Clear Context" option to remove selection
- Groups opportunities by program for better organization
- Uses Alpine.js for dropdown interactivity

**Display States**:

- No context: Yellow "Select Context" button
- Context selected: Shows current context with change option

### 3. Template Tags (`commcare_connect/labs/templatetags/labs_context.py`)

**Available Template Tags**:

```django
{% load labs_context %}

{# Get context as query string #}
{% context_url_params %}

{# Add context to a URL #}
{% url_with_context "/tasks/" %}

{# Filter to add context #}
<a href="{{ '/tasks/'|with_context:request }}">Tasks</a>

{# Check if context is set #}
{% has_context as context_set %}
```

### 4. Data Access Integration

Updated all data access classes to use `request.labs_context`:

- **TaskDataAccess** (`commcare_connect/tasks/data_access.py`)
- **AuditDataAccess** (`commcare_connect/audit/data_access.py`)
- **SolicitationDataAccess** (`commcare_connect/solicitations/data_access.py`)

Each class now checks `request.labs_context` first before falling back to other methods.

### 5. Configuration

Updated `config/settings/labs.py` to register middleware:

```python
MIDDLEWARE.insert(_auth_idx + 2, "commcare_connect.labs.context.LabsContextMiddleware")
```

## User Experience

### Example 1: User with Multiple Opportunities

1. User goes to `/tasks/`
2. No context in URL or session
3. Header shows yellow "Select Context" button
4. User clicks dropdown, sees list of opportunities grouped by program
5. Selects "CHW Training"
6. Redirected to `/tasks/?opportunity_id=456`
7. Session stores context
8. Header now shows "Opp: CHW Training"
9. All subsequent navigation maintains context in URL

### Example 2: User with One Opportunity (Auto-Select)

1. User goes to `/tasks/`
2. No context in URL or session
3. Middleware detects user has exactly 1 opportunity
4. Automatically redirects to `/tasks/?opportunity_id=456`
5. Session stores context
6. Header shows "Opp: CHW Training"
7. User never sees selector (seamless experience)

### Example 3: Session-Based Context

1. User has context in session from previous visit
2. User goes to `/audit/` without URL params
3. Middleware detects session context but no URL params
4. **Redirects to `/audit/?opportunity_id=456`** (makes context visible)
5. User sees context in URL bar
6. Can bookmark or share URL with context

## Context Parameters

### Supported Parameters

- `opportunity_id` - Integer (e.g., `?opportunity_id=123`)
- `program_id` - Integer (e.g., `?program_id=456`)
- `organization_id` - String slug (e.g., `?organization_id=dimagi`)

### Can Be Combined

Multiple context parameters can be used simultaneously:

```
/solicitations/?program_id=123&organization_id=dimagi
```

## Auto-Selection Logic

**Priority Order**:

1. If user has exactly **1 opportunity** → auto-select opportunity
2. If user has exactly **1 program** (and no opportunities) → auto-select program
3. If user has exactly **1 organization** (and no programs/opps) → auto-select organization
4. Otherwise → show selector, don't auto-redirect

## Session Storage

**Structure**:

```python
request.session['labs_context'] = {
    'organization_id': 'dimagi',
    'program_id': 123,
    'opportunity_id': 456
}
```

**Behavior**:

- URL params **always** take precedence over session
- Session updated when URL params change
- If session has context but URL doesn't, **redirect to add params to URL**
- Context cleared if user loses access or manually clears

## Request Attribute

All views have access to:

```python
request.labs_context = {
    'organization_id': 'dimagi',
    'program_id': 123,
    'opportunity_id': 456,
    'organization': {...},  # Full org data from OAuth
    'program': {...},       # Full program data from OAuth
    'opportunity': {...}    # Full opportunity data from OAuth
}
```

## Files Created/Modified

### New Files

1. `commcare_connect/labs/context.py` - Context middleware and utilities
2. `commcare_connect/templates/labs/context_selector.html` - Header component
3. `commcare_connect/labs/templatetags/__init__.py` - Template tags module init
4. `commcare_connect/labs/templatetags/labs_context.py` - Template tags
5. `commcare_connect/labs/tests/test_context.py` - Unit tests (9 tests, all passing)

### Modified Files

1. `config/settings/labs.py` - Registered middleware
2. `commcare_connect/templates/layouts/header.html` - Integrated context selector
3. `commcare_connect/tasks/data_access.py` - Use request.labs_context
4. `commcare_connect/audit/data_access.py` - Use request.labs_context
5. `commcare_connect/solicitations/data_access.py` - Use request.labs_context

## Testing

Created comprehensive test suite (`test_context.py`) with 9 tests covering:

- Context extraction from URLs
- Context validation and access control
- URL parameter generation
- Auto-selection logic for single/multiple contexts

**All tests pass** ✅

## Future Enhancements

Potential future improvements:

1. Remember last-used context per project (separate session keys)
2. Add context breadcrumbs for multi-level navigation
3. Add keyboard shortcuts for context switching
4. Show context-specific statistics in header
5. Add "Recently Used" contexts for quick switching

## Security Considerations

1. **Validation**: All context selections validated against user's OAuth data
2. **No Privilege Escalation**: Users can only select contexts they have access to
3. **Session Security**: Context stored in encrypted Django session
4. **Invalid Context**: Automatically cleared and redirected if user loses access
5. **URL Tampering**: Invalid IDs in URL params are rejected and cleared

## Performance

- **Minimal Overhead**: Single middleware check per request
- **No Database Queries**: All validation uses OAuth data from session
- **Efficient Caching**: Context stored in session, not re-fetched
- **Smart Redirects**: Only redirects when necessary (session→URL)

## Browser Compatibility

- Uses Alpine.js for dropdown (modern browsers)
- Graceful degradation for older browsers
- JavaScript required for dropdown interaction
- URL parameters work without JavaScript
