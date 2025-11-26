# Summary of Changes: CHC Nutrition → Audit Integration

## Problem Statement

When clicking "Audit" from the CHC Nutrition dashboard with URL parameters:

```
http://localhost:8000/audit/create/?opportunity_id=814&username=0dcd7433005277b73e32&user_id=30e2feeafefd4951897a1c5c4d5c330e&granularity=per_flw
```

The audit session could not be created because:

1. The wizard required manual preview generation before FLWs could be selected
2. The "Create Session" button was disabled until preview completed
3. User had to wait for preview even though the FLW was already specified in the URL

## Solution

Modified the audit creation wizard to pre-populate FLW selection from URL parameters, allowing users to configure audit parameters and create sessions directly without requiring a preview first.

## Files Changed

### 1. `commcare_connect/templates/custom_analysis/chc_nutrition/analysis.html`

**No changes needed** - The existing URL already includes all required parameters:

```html
<a
  href="{% url 'audit:creation_wizard' %}?opportunity_id={{ opportunity_id }}&username={{ flw.username }}&user_id={{ flw.custom_fields.commcare_userid }}&granularity=per_flw"
></a>
```

### 2. `commcare_connect/templates/audit/audit_creation_wizard.html`

#### Change: Modified `applyQuickParams()` to Pre-populate FLW Selection

**Before:**

```javascript
// For per_flw granularity with username, we'll filter FLWs after preview
// Store the username/user_id for later filtering
if (params.username) {
  this.quickFilterUsername = params.username;
}
if (params.user_id) {
  this.quickFilterUserId = params.user_id;
}

return params.auto_create === 'true';
```

**After:**

```javascript
// Pre-populate selected FLW IDs from URL params
// This allows creating a session without generating a preview first
if (params.username) {
  this.quickFilterUsername = params.username;
  this.selectedFlwUserIds.push(params.username);
}
if (params.user_id) {
  this.quickFilterUserId = params.user_id;
  // Add user_id if it's not already the same as username
  if (params.user_id !== params.username) {
    this.selectedFlwUserIds.push(params.user_id);
  }
}

return false; // Never auto-create
```

## New Flow

### Before Changes

```
CHC Nutrition Dashboard
  → Click "Audit"
  → Audit Creation Wizard loads
  → Opportunity is pre-selected (from URL)
  → User must:
     1. Click "Preview" button
     2. Wait for preview to load FLW list
     3. Select FLW from preview list
     4. Configure audit parameters (date range, count, etc.)
     5. Click "Create Session"
```

### After Changes

```
CHC Nutrition Dashboard
  → Click "Audit"
  → Audit Creation Wizard loads
  → Automatically:
     - Opportunity is pre-selected
     - FLW is pre-selected (from username/user_id in URL)
     - Granularity is set to "per_flw"
  → User can:
     - Configure audit parameters (date range, count, etc.)
     - Optionally click "Preview" to verify FLW selection
     - Click "Create Session" directly (no preview required!)
  → Session created with selected FLW's visits
  → Start auditing!
```

## Technical Details

### URL Parameters Used

| Parameter        | Source                              | Purpose                                            |
| ---------------- | ----------------------------------- | -------------------------------------------------- |
| `opportunity_id` | CHC Nutrition context               | Auto-select opportunity                            |
| `username`       | FLW table row                       | Pre-populate FLW selection                         |
| `user_id`        | `flw.custom_fields.commcare_userid` | Pre-populate FLW selection (additional identifier) |
| `granularity`    | Hardcoded as `per_flw`              | Set audit granularity                              |

### FLW Pre-population Logic

The wizard pre-populates `selectedFlwUserIds` from URL parameters:

```javascript
// Add username as an identifier
if (params.username) {
  this.quickFilterUsername = params.username;
  this.selectedFlwUserIds.push(params.username);
}

// Add user_id as an additional identifier (if different from username)
if (params.user_id) {
  this.quickFilterUserId = params.user_id;
  if (params.user_id !== params.username) {
    this.selectedFlwUserIds.push(params.user_id);
  }
}
```

This allows the create API to filter visits by username or user_id without requiring a preview.

### Backend Filtering

The `selected_flw_user_ids` array is passed to the create API and filters visits:

```python
if selected_flw_user_ids and visit_ids:
    filtered_visit_ids = []
    for opp_id in opportunity_ids:
        visits = data_access.get_visits_batch(visit_ids, opp_id)
        filtered_visit_ids.extend([
            v["id"] for v in visits
            if v.get("username") in selected_flw_user_ids
            or v.get("user_id") in selected_flw_user_ids
        ])
    visit_ids = filtered_visit_ids
```

## Benefits

1. **Skip preview step**: No need to wait for preview to load FLW list
2. **Configure parameters**: User can still adjust date range, visit count, etc.
3. **Direct creation**: "Create Session" button works immediately with pre-selected FLW
4. **Optional preview**: User can still click "Preview" if they want to verify FLW selection
5. **Flexible workflow**: Maintains full control while removing unnecessary steps

## Testing

Quick test:

1. Go to `http://localhost:8000/custom_analysis/chc_nutrition/?opportunity_id=814`
2. Click "Audit" for any FLW
3. Verify wizard loads with:
   - Opportunity pre-selected
   - Granularity set to "per_flw"
   - FLW identifiers pre-populated (check browser console: `Alpine.$data(document.querySelector('[x-data]')).selectedFlwUserIds`)
4. Configure audit parameters (optional - adjust date range, visit count, etc.)
5. Click "Create Session" directly (no need to preview!)
6. Verify session is created and contains only that FLW's visits

## Edge Cases Handled

1. **User adjusts parameters**: Can modify date range, count, etc. before creating
2. **User wants to preview**: Can click "Preview" to verify selection before creating
3. **Backend filtering**: API filters visits by username/user_id to match selected FLW
4. **Multiple identifiers**: Passes both username and user_id for robust matching

## Documentation

Additional documentation files created:

- `AUDIT_INTEGRATION.md` - Detailed integration documentation with flow diagrams
- `TEST_AUDIT_INTEGRATION.md` - Comprehensive test cases and debugging guide
- `CHANGES_SUMMARY.md` - This file
