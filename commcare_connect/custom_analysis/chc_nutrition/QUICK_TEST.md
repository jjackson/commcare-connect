# Quick Test: CHC Nutrition → Audit Integration

## What Was Changed

Modified the audit creation wizard to **pre-populate FLW selection** from URL parameters, allowing you to skip the preview step and create sessions directly.

## Quick Test

### Step 1: Open CHC Nutrition Dashboard

```
http://localhost:8000/custom_analysis/chc_nutrition/?opportunity_id=814
```

### Step 2: Click "Audit" for Any FLW

Click the blue "Audit" button in the Actions column for any FLW.

### Step 3: Verify Pre-population

You should see:

- ✅ Opportunity is already selected (814 or whichever you chose)
- ✅ Granularity is set to "per_flw"
- ✅ FLW is pre-selected (check browser console)

To verify FLW pre-selection, open browser console and run:

```javascript
Alpine.$data(document.querySelector('[x-data]')).selectedFlwUserIds;
```

Should show: `["username", "user_id"]` or similar

### Step 4: Configure Audit Parameters (Optional)

You can now:

- Adjust date range (default: last 30 days)
- Change visit count (default: 100 per FLW)
- Set title/tag
- Or leave defaults and proceed

### Step 5: Create Session Directly

Click **"Create Session"** button (no need to click "Preview"!)

### Step 6: Verify Session

After redirect to session detail page:

- Check visit count matches expectations
- Browse a few visits
- Verify all visits belong to the selected FLW (check username field)

## What Should Work

✅ **Skip preview** - Create button works without previewing first
✅ **Configure parameters** - Can adjust date range, count, etc. before creating
✅ **FLW filtering** - Only selected FLW's visits are included
✅ **Optional preview** - Can still click "Preview" if you want to verify

## What Shouldn't Happen

❌ **Auto-create** - Session should NOT be created automatically
❌ **Required preview** - Should NOT need to click "Preview" before "Create Session"
❌ **Wrong FLW** - Should only include visits from the selected FLW

## Browser Console Debugging

Check if FLW IDs are pre-populated:

```javascript
const data = Alpine.$data(document.querySelector('[x-data]'));
console.log('Selected FLW IDs:', data.selectedFlwUserIds);
console.log('Quick params:', data.quickParams);
```

Expected output:

```javascript
Selected FLW IDs: ["0dcd7433005277b73e32", "30e2feeafefd4951897a1c5c4d5c330e"]
Quick params: {
  "username": "0dcd7433005277b73e32",
  "user_id": "30e2feeafefd4951897a1c5c4d5c330e",
  "granularity": "per_flw"
}
```

## Common Issues

**Issue: "Create Session" button is disabled**

- Check that opportunity is selected
- Check that audit criteria is valid (date range set)
- Should work even without preview

**Issue: Session includes wrong FLW's visits**

- Check that URL has correct username/user_id parameters
- Verify selectedFlwUserIds array has both identifiers
- Check backend filtering logic in create API

**Issue: No visits in session**

- FLW may have no visits in selected date range
- Try expanding date range (e.g., last 60 or 90 days)
- Or adjust audit type/criteria

## Success Criteria

✅ Can create audit session without clicking "Preview"
✅ Session contains only selected FLW's visits
✅ Can configure parameters before creating
✅ URL parameters correctly pre-populate wizard
