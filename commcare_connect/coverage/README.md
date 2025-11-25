# Coverage Module

This module provides coverage visualization and analysis tools for mapping FLW (Field Worker) activities across delivery units and service areas.

## FLW Name Helper

The `get_flw_names_for_opportunity()` helper function retrieves human-readable names for FLWs based on opportunity access.

### Usage

```python
from commcare_connect.coverage.utils import get_flw_names_for_opportunity

# Get FLW display names for an opportunity
flw_names = get_flw_names_for_opportunity(opportunity_id=814)

# Returns a dictionary mapping username to display name:
# {
#     "e5e685ae3f024fb6848d0d87138d526f": "John Doe",
#     "f7g797bf4g135gc7959e1e98249e637g": "Jane Smith",
# }

# Use in your views
username = "e5e685ae3f024fb6848d0d87138d526f"
display_name = flw_names.get(username, username)  # Falls back to username if not found
```

### Caching

Results are cached for 1 hour by default to avoid repeated database queries. You can customize the cache timeout:

```python
# Cache for 30 minutes
flw_names = get_flw_names_for_opportunity(opportunity_id=814, cache_timeout=1800)
```

### Integration with Labs Projects

This helper is useful in any labs project that needs to display FLW names instead of usernames. It uses the data export API's user profile data that was recently added to retrieve human names.

Example usage in a labs view:

```python
from commcare_connect.coverage.utils import get_flw_names_for_opportunity

def my_labs_view(request, opportunity_id):
    # Get FLW names
    flw_names = get_flw_names_for_opportunity(opportunity_id)

    # Use them to enrich your data
    for visit in visits:
        visit.display_name = flw_names.get(visit.username, visit.username)

    return render(request, 'my_template.html', {'visits': visits})
```
