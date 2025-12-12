# KMC Timeline View

A composable, configuration-driven timeline view for tracking Kangaroo Mother Care beneficiaries across multiple visits.

## Overview

This implementation uses the generic configurable UI framework (`labs/configurable_ui/`) which allows creating timeline views for different programs (KMC, nutrition, early childhood) by simply changing configuration files - no code changes needed.

## Architecture

### Generic Framework (`labs/configurable_ui/`)

- **`linking.py`**: Links visits across opportunities to build child timelines
- **`widgets.py`**: Widget configuration system with field extractors
- **`views.py`**: Generic views that work with any timeline config
- **Templates**: Dynamic widget rendering based on configuration

### KMC-Specific (`custom_analysis/kmc/`)

- **`timeline_config.py`**: All KMC-specific configuration
  - Widget definitions (visit_history, weight_chart, map, detail_panel)
  - Layout configuration (which widgets in which columns)
  - Field extractors (how to get data from form JSON)
  - Header fields
- **`views.py`**: Thin wrappers that provide KMC config to generic views
- **`urls.py`**: URL routing

## URLs

- `/custom_analysis/kmc/children/` - List all KMC children
- `/custom_analysis/kmc/children/<child_id>/` - Timeline for specific child
- `/custom_analysis/kmc/api/child/<child_id>/` - API endpoint (JSON)

## Features

### Three-Column Layout

- **Left**: Visit history cards with photos
- **Center**: Weight progression chart + GPS map
- **Right**: Visit details panel

### Widgets

1. **Visit History**: Clickable cards showing visit number, date, weight, photo
2. **Weight Chart**: Line chart with color zones (< 2.5kg yellow, >= 2.5kg green)
3. **Map**: Leaflet map showing GPS location of each visit
4. **Detail Panel**: Structured sections (Anthropometric, KMC Practice, Feeding, Vital Signs, Status)

## Data Source

Links visits using `form.case.@case_id` (registration) or `form.kmc_beneficiary_case_id` (follow-ups).

Currently configured for opportunity 523.

## Adding Another Program

To add a nutrition timeline:

1. Create `custom_analysis/chc_nutrition/timeline_config.py`
2. Define widgets with nutrition-specific fields (MUAC instead of weight)
3. Create thin view wrappers
4. Add URL routing

The same generic framework and templates are reused!

## Testing

To test with the provided KMC data:

1. Ensure opportunity 523 is in labs context
2. Navigate to `/custom_analysis/kmc/children/`
3. Click on a child to view their timeline
4. Verify weight chart, map, and visit details render correctly
