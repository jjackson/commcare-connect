# CHC Nutrition → Audit Integration

## Overview

This document describes how the CHC Nutrition dashboard integrates with the Audit system to enable streamlined audit creation for specific FLWs without requiring a preview step.

## Changes Made

### 1. CHC Nutrition Dashboard Link (analysis.html)

The "Audit" button in the FLW table uses these URL parameters:

```html
<a
  href="{% url 'audit:creation_wizard' %}?opportunity_id={{ opportunity_id }}&username={{ flw.username }}&user_id={{ flw.custom_fields.commcare_userid }}&granularity=per_flw"
></a>
```

**URL Parameters:**

- `opportunity_id`: The current opportunity ID (auto-selected)
- `username`: The FLW's username (pre-populates FLW selection)
- `user_id`: The FLW's CommCare user ID from `form.meta.userID` (additional identifier)
- `granularity=per_flw`: Sets audit granularity to per-FLW mode

### 2. Audit Creation Wizard JavaScript (audit_creation_wizard.html)

#### Modified `applyQuickParams()` Function

When `username` and/or `user_id` are in the URL:

1. Stores them in `quickFilterUsername` and `quickFilterUserId` for reference
2. **Pre-populates `selectedFlwUserIds` array** with both identifiers
3. Returns `false` (no auto-create)

**Previous behavior:** Required preview to populate FLW list before selection
**New behavior:** FLW identifiers are pre-populated from URL, allowing direct session creation

```javascript
// Pre-populate selected FLW IDs from URL params
// This allows creating a session without generating a preview first
if (params.username) {
  this.quickFilterUsername = params.username;
  this.selectedFlwUserIds.push(params.username);
}
if (params.user_id) {
  this.quickFilterUserId = params.user_id;
  if (params.user_id !== params.username) {
    this.selectedFlwUserIds.push(params.user_id);
  }
}
```

## Flow Diagram

```
CHC Nutrition Dashboard
    ↓ Click "Audit" button for FLW
    ↓ Navigate to /audit/create/?opportunity_id=X&username=Y&user_id=Z&granularity=per_flw
    ↓
Audit Creation Wizard (init)
    ↓ Apply quick params:
       - Auto-select opportunity
       - Set granularity to "per_flw"
       - Pre-populate selectedFlwUserIds with [username, user_id]
    ↓
User Configures Audit
    ↓ Adjust date range (optional)
    ↓ Adjust visit count (optional)
    ↓ Set title/tag (optional)
    ↓ Optionally click "Preview" to verify
    ↓ Click "Create Session"
    ↓
Create Session API Call
    ↓ Create audit template and session
    ↓ Filter visits by selected_flw_user_ids (username/user_id)
    ↓ Redirect to audit session detail page
    ↓
Start Auditing!
```

## FLW Pre-population Logic

The wizard pre-populates FLW selection from URL parameters:

```javascript
// Add both username and user_id as identifiers
if (params.username) {
  this.selectedFlwUserIds.push(params.username);
}
if (params.user_id && params.user_id !== params.username) {
  this.selectedFlwUserIds.push(params.user_id);
}
```

This array is passed directly to the create API, which filters visits by these identifiers.

## Backend FLW Filtering

The `ExperimentAuditCreateAPIView` receives `selected_flw_user_ids` in the criteria and filters visits:

```python
selected_flw_user_ids = normalized_criteria.get("selected_flw_user_ids", [])
if selected_flw_user_ids and visit_ids:
    filtered_visit_ids = []
    for opp_id in opportunity_ids:
        visits = data_access.get_visits_batch(visit_ids, opp_id)
        filtered_visit_ids.extend(
            [
                v["id"]
                for v in visits
                if v.get("username") in selected_flw_user_ids or v.get("user_id") in selected_flw_user_ids
            ]
        )
    visit_ids = filtered_visit_ids
```

## Testing

To test the integration:

1. Navigate to CHC Nutrition dashboard: `http://localhost:8000/custom_analysis/chc_nutrition/?opportunity_id=814`
2. Click the "Audit" button for any FLW
3. Verify that:
   - The audit creation wizard opens
   - The opportunity is auto-selected
   - Granularity is set to "per_flw"
   - FLW identifiers are pre-populated (check console: `Alpine.$data(document.querySelector('[x-data]')).selectedFlwUserIds`)
4. Configure audit parameters:
   - Adjust date range (e.g., last 60 days instead of 30)
   - Adjust visit count (e.g., 20 visits per FLW instead of default)
   - Set title/tag if desired
5. Click "Create Session" (no need to preview!)
6. Verify that:
   - Session is created successfully
   - You're redirected to the audit session detail page
   - Only visits from the selected FLW are included

## Benefits

1. **Skip preview step**: No need to wait for preview to populate FLW list
2. **Configure before creating**: Maintain full control over audit parameters
3. **FLW pre-selected**: The specific FLW from CHC Nutrition is automatically selected
4. **Optional preview**: Can still preview if desired to verify FLW selection
5. **Flexible workflow**: Streamlined but not automated - user stays in control

## Fallback Behavior

The wizard maintains full flexibility:

- User can adjust any parameters before creating
- User can click "Preview" to verify FLW selection
- User can change FLW selection if needed
- Standard error handling applies if no visits are found
