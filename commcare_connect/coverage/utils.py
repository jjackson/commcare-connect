"""
Utility functions for coverage visualization.
"""

from django.core.cache import cache
from django.db.models import F

from commcare_connect.opportunity.models import OpportunityAccess


def get_flw_names_for_opportunity(opportunity_id: int, cache_timeout: int = 3600) -> dict[str, str]:
    """
    Get FLW display names for an opportunity with caching.

    Retrieves a mapping of username to display name (full name) for all FLWs
    who have access to the specified opportunity. Results are cached to avoid
    repeated database queries.

    Args:
        opportunity_id: The ID of the opportunity
        cache_timeout: Cache timeout in seconds (default: 3600 = 1 hour)

    Returns:
        Dictionary mapping username to display name (user's full name)
        Example: {"e5e685ae3f024fb6848d0d87138d526f": "John Doe"}

    Examples:
        >>> flw_names = get_flw_names_for_opportunity(814)
        >>> flw_names["e5e685ae3f024fb6848d0d87138d526f"]
        'John Doe'
    """
    cache_key = f"flw_names_opp_{opportunity_id}"

    # Try to get from cache first
    cached_names = cache.get(cache_key)
    if cached_names is not None:
        return cached_names

    # Query database if not cached
    flw_data = (
        OpportunityAccess.objects.filter(opportunity_id=opportunity_id)
        .annotate(
            username=F("user__username"),
            display_name=F("user__name"),
        )
        .values("username", "display_name")
    )

    # Build mapping dictionary
    flw_names = {row["username"]: row["display_name"] or row["username"] for row in flw_data if row["username"]}

    # Cache the results
    cache.set(cache_key, flw_names, cache_timeout)

    return flw_names


def extract_gps_from_form_json(form_json: dict) -> tuple[float, float, float | None]:
    """
    Extract lat, lon, accuracy from UserVisit form_json.

    Args:
        form_json: Form JSON dict containing metadata.location

    Returns:
        Tuple of (latitude, longitude, accuracy_in_meters)
    """
    location_str = form_json.get("metadata", {}).get("location", "")
    parts = location_str.split()

    lat = float(parts[0]) if len(parts) > 0 else 0.0
    lon = float(parts[1]) if len(parts) > 1 else 0.0
    accuracy = float(parts[3]) if len(parts) > 3 else None

    return lat, lon, accuracy


def simplify_geometry_for_zoom(wkt_string: str, zoom_level: int) -> str:
    """
    Simplify polygon based on zoom level for better performance.

    Args:
        wkt_string: Well-Known Text geometry string
        zoom_level: Map zoom level (7=country, 10=region, 13=city, 15=street)

    Returns:
        Simplified WKT string
    """
    from shapely import wkt

    geom = wkt.loads(wkt_string)

    # Tolerance increases as zoom decreases
    tolerance_map = {
        7: 0.01,  # Country view
        10: 0.001,  # Region view
        13: 0.0001,  # City view
        15: 0.0,  # Street view (no simplification)
    }

    tolerance = tolerance_map.get(zoom_level, 0.0001)
    simplified = geom.simplify(tolerance, preserve_topology=True)

    return simplified.wkt
