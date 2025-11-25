# Bug Fix: Duplicate Data Loading in Coverage Maps

## Issue

Coverage maps were loading data multiple times, causing:

1. Slow page loads (duplicate API processing)
2. Double FLW entries (one set with proper names, one with CommCare IDs)
3. Duplicate `compute_visit_analysis` calls within a single API request

## Root Cause

In `CoverageMapDataView.get()`, visit data was being fetched **twice**:

1. **Line 777**: `visit_rows, field_metadata = map_view.get_enriched_visits(config, coverage)`

   - This internally calls `get_coverage_visit_analysis()` to fetch visit data

2. **Line 802** (REMOVED): `result = get_coverage_visit_analysis(request=request, config=config, du_lookup=du_lookup, use_cache=use_cache)`
   - This was a duplicate call fetching the same data again
   - This second call was only needed to build the `commcare_userid → username` mapping

## Fix Applied

Removed the duplicate `get_coverage_visit_analysis()` call and instead reused the `visit_rows` already fetched:

### Before (lines 784-812):

```python
# Generate FLW colors
flw_colors = generate_flw_colors(coverage.flws)

# Build du_lookup for mapping
du_lookup = {}
for du in coverage.delivery_units.values():
    du_info = {"service_area_id": du.service_area_id}
    du_lookup[du.du_name] = du_info
    du_lookup[du.id] = du_info
    try:
        du_lookup[int(du.id)] = du_info
    except (ValueError, TypeError):
        pass

# Get visit data for CommCare ID mapping
from commcare_connect.coverage.analysis import get_coverage_visit_analysis

use_cache = request.GET.get("refresh") != "1"
result = get_coverage_visit_analysis(request=request, config=config, du_lookup=du_lookup, use_cache=use_cache)

# Build mapping: commcare_userid → username
commcare_to_username = {}
for visit in result.rows:
    if visit.commcare_userid and visit.username:
        commcare_to_username[visit.commcare_userid] = visit.username

# Build GeoJSON data
delivery_units_geojson = map_view.build_colored_du_geojson(coverage, flw_colors, commcare_to_username)
service_points_geojson = map_view.build_colored_points_geojson(result.rows, coverage.flws, flw_colors)
```

### After (lines 784-795):

```python
# Generate FLW colors
flw_colors = generate_flw_colors(coverage.flws)

# Build mapping: commcare_userid → username from already-fetched visit_rows
commcare_to_username = {}
for visit in visit_rows:
    if visit.commcare_userid and visit.username:
        commcare_to_username[visit.commcare_userid] = visit.username

# Build GeoJSON data
delivery_units_geojson = map_view.build_colored_du_geojson(coverage, flw_colors, commcare_to_username)
service_points_geojson = map_view.build_colored_points_geojson(visit_rows, coverage.flws, flw_colors)
```

Also updated references from `result.rows` to `visit_rows` in:

- Line 820: `service_points_count`
- Line 824: Log message

## Impact

- **Performance**: Cuts API processing time roughly in half (eliminates duplicate visit analysis)
- **Cache hits**: Reduces redundant cache lookups
- **FLW duplication**: Should resolve double FLW entries issue
- **Cleaner code**: Removed unnecessary `du_lookup` building and duplicate API calls

## Testing

After this fix, you should see in the logs:

- Only ONE call to `compute_visit_analysis` per API request (not two)
- Only ONE "Enriched X/Y visits with DU context" message per API request
- FLWs should appear once in the UI with correct names

## Note on Frontend Double Calls

The terminal logs show the `/coverage/api/map-data/` endpoint being called twice. Analysis shows:

### Timing Evidence

```
[25/Nov/2025 16:21:18] First API call completes (16.5 MB response)
[25/Nov/2025 16:21:18] Debug toolbar history_sidebar request
[25/Nov/2025 16:21:18,075] Second API call starts (75ms later, 233 KB response)
```

### Potential Causes

1. **Django Debug Toolbar**: The timing suggests the debug toolbar might be triggering a duplicate request
2. **Browser behavior**: Some browsers pre-fetch or retry large responses
3. **Alpine.js double initialization**: Though the code looks correct

### Investigation Steps

Added logging to track request sources:

- User-Agent header
- Referer header

This will help identify if it's the debug toolbar, a browser extension, or actual double initialization.

### FLW Duplication

The duplicate FLWs with 0 visits issue is related to the multiple API calls:

- First call: Properly enriches visits with DU context (12636/12958)
- Second call: Enriches 0/12958 visits with DU context (bug!)

Added filter to only show FLWs with visits > 0 in the UI (line 813).
