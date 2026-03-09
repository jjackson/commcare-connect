# KMC Longitudinal Tracking — Improvement Plan

**Date:** 2026-03-07
**Status:** Backlog

## Context

Screenshots taken of live KMC workflow with real data (opportunity 874, 1266 children, 5201 visits). Issues identified across dashboard, child list, and timeline views.

## Issues

### Dashboard

#### 1. Second row KPI cards lack color coding
- "Below Avg Gain", "Reached 2.5kg", "Discharged" all have gray borders
- Should have distinct colors: yellow/warning for Below Avg, green for Reached 2.5kg, blue for Discharged
- **Effort:** Small (CSS only)

#### 2. No percentage context on KPI cards
- "362 Overdue" is more meaningful with "29% of total" underneath
- Add small percentage or fraction to help managers gauge severity
- **Effort:** Small

#### 3. Missing "Avg Visits/Child" card
- Design doc spec'd this card. The value is computed (shown in summary text as "4.1 visits/child avg") but not shown as a KPI card
- **Effort:** Small

### Child List

#### 4. FLW column shows raw usernames
- "gitgljfaw80gx37q0sph" is meaningless to users
- If display names aren't available from the pipeline, consider truncating or omitting
- **Effort:** Small — may need pipeline schema change to extract display name

#### 5. Weight gain sign bug — "+-200g"
- Negative weight gains display as "+-200g (+-17%)" instead of "-200g (-17%)"
- The `+` prefix is being prepended regardless of sign
- Seen on child "rahan" (8 visits, current weight 1000g, birth weight 1200g)
- **Effort:** Small (string formatting fix in render code)

#### 6. Last Visit column — no positive color
- Red for overdue (>14 days) is good
- Consider green for <7 days to show children on track
- **Effort:** Small

### Child Timeline

#### 7. Clinical detail panel is mostly empty
- Visit 8 for "waswa" (9 visits) shows Weight: "—", Height: "—", KMC Hours: "—" etc.
- The chart shows data points at those dates, so weight data exists in the pipeline
- **Root cause hypothesis:** The detail panel reads from specific field names that don't match what the pipeline actually extracts. Many pipeline fields may have wrong `path` values that don't match the actual CommCare form structure.
- **Effort:** Medium — need to inspect actual pipeline row data vs. what the detail panel expects

#### 8. No selected-visit highlight on chart
- When clicking a visit in the sidebar, the corresponding chart point should be highlighted (larger dot, different color)
- Currently no visual connection between sidebar selection and chart
- **Effort:** Medium (Chart.js point styling)

#### 9. Map marker legend missing
- Red circles with cross vs blue/green dots — unclear what they represent
- Need a small legend explaining marker colors
- **Effort:** Small

#### 10. Visit sidebar "Visit 8" labeling
- Shows "Visit 8" at top (selected, most recent) but this is confusing — is it the 8th visit chronologically? The most recent?
- Consider showing visit date more prominently or clarifying numbering
- **Effort:** Small

#### 11. "Visit Additional" label in sidebar
- Seen on child "rahan" — sidebar shows "Visit Additional" as form name instead of a visit number
- Should normalize non-standard form names to "Visit N" or display form name + visit number
- **Effort:** Small

#### 12. Flat/negative weight not visually flagged
- "rahan" has weight stuck at ~1,000g across 8 visits over 6 weeks — a red flag for KMC
- Consider visual alert (red border, warning icon) when weight is stagnant below threshold
- **Effort:** Medium

### General / Cross-cutting

#### 13. Header fields mostly empty (DOB, Mother, Village, Subcounty)
- All children viewed show "-" for DOB, Mother, Village, Subcounty
- **Root cause hypothesis:** Same as #7 — pipeline schema `path` values likely don't match actual CommCare form field paths. The data exists in CommCare but isn't being extracted.
- This is probably the biggest systemic issue. Need to:
  1. Inspect a raw form submission to see actual field paths
  2. Compare against PIPELINE_SCHEMAS field definitions
  3. Update paths to match reality
- **Effort:** Medium — requires inspecting raw CommCare data

#### 14. No export/download
- Program managers need to export child lists to Excel/CSV for reporting
- **Effort:** Medium

#### 15. No loading state for child list
- With 1266 children, should show spinner or skeleton while list renders
- **Effort:** Small

## Priority Order

| Priority | Issue | Why |
|----------|-------|-----|
| P0 | #5 Weight gain sign bug | Data accuracy — shows wrong numbers |
| P0 | #7, #13 Pipeline field path mismatch | Core feature gap — most fields empty |
| P1 | #1 KPI card colors | Quick visual win |
| P1 | #2 KPI percentages | Quick context win |
| P1 | #3 Avg visits card | Missing spec'd feature |
| P1 | #8 Chart visit highlight | Core interaction missing |
| P2 | #4 FLW usernames | Display quality |
| P2 | #6 Last visit green color | Visual polish |
| P2 | #9 Map legend | Usability |
| P2 | #10, #11 Visit labeling | Clarity |
| P2 | #12 Stagnant weight alert | Clinical value |
| P3 | #14 Export | Feature request |
| P3 | #15 Loading state | Polish |

## Notes

- Pagination was considered but isn't causing a performance issue yet with 1266 rows — deferred
- The pipeline field path mismatch (#7, #13) is likely the root cause of most "empty data" issues and should be investigated first by inspecting raw CommCare form data against the PIPELINE_SCHEMAS paths
