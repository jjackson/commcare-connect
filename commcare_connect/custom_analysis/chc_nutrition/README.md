# CHC Nutrition Analysis

FLW-level analysis of nutrition and health metrics for CHC (Community Health Center) programs.

## Features

- **One row per FLW** with aggregated metrics across all their visits
- **Nutrition indicators**: MUAC measurements, malnutrition diagnosis and treatment
- **Health status**: Children unwell, recovery tracking
- **Diligence checks**: Vitamin A doses, ORS treatment, immunization records
- **Session caching**: 10-minute cache for fast repeated views
- **Summary statistics**: Aggregate metrics across all FLWs

## Access

1. **Navigate to**: `/custom_analysis/chc_nutrition/`
2. **Select opportunity** from the labs context selector
3. **View results** - automatically fetches and analyzes UserVisit data

**Direct URL with context:**

```
/custom_analysis/chc_nutrition/?opportunity_id=575
```

## Data Sources

- **UserVisits**: Fetched from Connect API (`/export/opportunity/{opp_id}/user_visits/`)
- **Form JSON fields**: Extracted using declarative configuration
- **Filters**: Only approved visits included

## Metrics Tracked

### Standard FLW Metrics (from framework)

- Total visits
- Approved/pending/rejected visits
- Days active
- Approval rate
- Date range (first/last visit)

### Nutrition-Specific Metrics

1. **Demographics**

   - Child age (first visit)
   - Child gender (first visit)
   - Household phone

2. **MUAC Measurements**

   - Count of MUAC consents
   - Count of measurements taken
   - Average MUAC (cm)
   - MUAC colors observed (list)

3. **Health Status**

   - Children unwell count
   - Malnutrition diagnosed count
   - Under treatment count

4. **Vitamin A (Diligence)**

   - Received VA dose before count
   - Recent VA dose count
   - VA consent count
   - VA knowledge shared/confirmed count

5. **ORS Treatment (Diligence)**

   - Children recovered with ORS count
   - Still facing symptoms count

6. **Immunization (Diligence)**

   - Received any vaccine count
   - Reasons for no immunization photo
   - Reasons vaccine not provided

7. **Other**
   - Children with glasses count
   - Households with children count

## Configuration

Analysis configuration is in `analysis_config.py`:

- **27 field computations** covering all SQL query fields
- **Aggregations**: count, avg, list, first
- **Transforms**: Type coercion, boolean checks
- **Filters**: Approved visits only

## Caching

- **Automatic**: Results cached in session for 10 minutes
- **Refresh**: Add `?refresh=1` to URL to force recomputation
- **Cache indicator**: Badge shows if results are from cache

## Example SQL to Framework Mapping

**SQL:**

```sql
form_json -> 'form' -> 'additional_case_info' ->> 'childs_age_in_month' AS child_age_months
```

**Framework:**

```python
FieldComputation(
    name="child_age_months",
    path="form.additional_case_info.childs_age_in_month",
    aggregation="first"
)
```

## Extending

To add new metrics:

1. Edit `analysis_config.py`
2. Add `FieldComputation` to `CHC_NUTRITION_CONFIG.fields`
3. Refresh page to see new field
4. Update template to display if desired

Example:

```python
FieldComputation(
    name="new_metric",
    path="form.my_field",
    aggregation="count",
    transform=lambda x: 1 if x == "yes" else None,
    description="Count of yes responses"
)
```

## Template

Main template: `templates/custom_analysis/chc_nutrition/analysis.html`

Features:

- Summary cards
- Nutrition metrics summary
- Main table with key metrics
- Expandable "Show All Fields" table with Alpine.js toggle
- Tailwind CSS styling
- Responsive design

## Implementation Details

- **Framework**: Uses `labs/analysis/` framework
- **View**: `CHCNutritionAnalysisView` in `views.py`
- **Compute function**: `compute_flw_analysis()` with automatic caching
- **Result type**: `FLWAnalysisResult` with `FLWRow` instances
- **Context integration**: Uses labs context middleware for opportunity selection

## Future Enhancements

- [ ] Export to CSV/Excel
- [ ] Drill-down to individual FLW details
- [ ] Date range filtering
- [ ] Charts and visualizations
- [ ] Comparison across time periods
- [ ] Entity-level analysis (one row per child/household)
