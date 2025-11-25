# Double API Call Investigation

## Evidence from Logs (16:32:11 - 16:32:14)

### Timeline Analysis

**Multiple Concurrent Requests Detected:**

1. **Request 1** (broken pipe at line 595)

   - Line 576: "Using analysis config with **1 fields**" ❌
   - Line 592: Enriched 0/12958 visits
   - Result: Connection broken before completion

2. **Request 2** - call_id=ujd0ej83z

   - Line 582: "Using analysis config with **1 fields**" ❌
   - Line 607: Completed - 230KB response
   - Result: Wrong config (base config instead of chc_nutrition)

3. **Request 3** - call_id=w2u15rgbc
   - (Config log missing but implied correct based on response size)
   - Line 600: Enriched 12636/12958 visits ✅
   - Line 608: Completed - 5.3MB response
   - Result: Correct config with full data

### Key Observations

1. **Two Different Call IDs from JavaScript:**

   - `ujd0ej83z` (230KB - wrong)
   - `w2u15rgbc` (5.3MB - correct)
   - This proves JavaScript is calling `loadMapData()` TWICE

2. **Config Parameter Not Being Passed:**

   - Some requests show "1 fields" instead of "25 fields"
   - This means `config=chc_nutrition` is missing from URL

3. **Sample Computed Keys Show du_name Present:**
   - Line 566, 593, 600, 620: `[['du_name'], ['du_name'], ['du_name']]`
   - But values are empty when using base config

## Root Cause Hypothesis

The issue is **TWO-FOLD**:

### Problem 1: JavaScript Double Call

Alpine.js `init()` is being called twice, creating two fetch requests with different call_ids.

**Possible causes:**

- HMR/dev server double initialization
- Alpine.js loading/starting twice
- Component mounting twice

### Problem 2: Config Parameter Loss

Some requests are losing the `config=chc_nutrition` parameter.

**This might be because:**

- `window.location.search` is empty or incomplete at call time
- Race condition during page load
- URL not fully loaded when `init()` fires

## Next Steps

1. Add console.log to track when `init()` is called
2. Log `window.location.search` value at fetch time
3. Check if Alpine is loading multiple times
4. Consider delaying `init()` until DOM fully ready
