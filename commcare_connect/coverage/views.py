"""
Views for coverage visualization.
"""

import json
import logging

import httpx
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from shapely.geometry import mapping

from commcare_connect.coverage.analysis import get_coverage_visit_analysis
from commcare_connect.coverage.data_access import CoverageDataAccess
from commcare_connect.coverage.models import CoverageData
from commcare_connect.labs.analysis.config import AnalysisConfig
from commcare_connect.labs.analysis.models import VisitRow

logger = logging.getLogger(__name__)


def generate_flw_colors(flw_dict: dict) -> dict:
    """
    Generate contrasting colors for FLWs using HSV color space.

    Args:
        flw_dict: Dictionary of FLWs {flw_id: FLW object}

    Returns:
        Dictionary mapping flw_id to hex color
    """
    import colorsys
    import random

    flw_ids = list(flw_dict.keys())
    n = len(flw_ids)

    # Predefined high-contrast colors for first few FLWs
    base_colors = [
        "#FF0000",
        "#00FF00",
        "#0000FF",
        "#FFFF00",
        "#FF00FF",
        "#00FFFF",
        "#FF8000",
        "#FF0080",
        "#80FF00",
        "#00FF80",
        "#8000FF",
        "#0080FF",
        "#804000",
        "#FF4080",
        "#8080FF",
        "#80FF80",
        "#804080",
        "#408080",
    ]

    colors = []
    if n <= len(base_colors):
        colors = base_colors[:n]
    else:
        colors = list(base_colors)
        needed = n - len(base_colors)

        # Generate additional colors using HSV for good distribution
        for i in range(needed):
            hue = (i * 0.618033988749895) % 1.0  # Golden ratio
            saturation = 0.7 + (i % 3) * 0.15
            value = 0.6 + (i % 4) * 0.13

            r, g, b = colorsys.hsv_to_rgb(hue, saturation, value)
            color = f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"
            colors.append(color)

    # Shuffle for better adjacent color contrast
    random.shuffle(colors)

    return {flw_id: colors[i] for i, flw_id in enumerate(flw_ids)}


class BaseCoverageView(LoginRequiredMixin, TemplateView):
    """Base view with caching"""

    def check_commcare_oauth(self) -> bool:
        """Check if CommCare OAuth is configured and not expired"""
        from django.utils import timezone

        commcare_oauth = self.request.session.get("commcare_oauth", {})
        access_token = commcare_oauth.get("access_token")

        if not access_token:
            logger.debug("No CommCare OAuth token found in session")
            return False

        # Check expiration
        expires_at = commcare_oauth.get("expires_at", 0)
        if timezone.now().timestamp() >= expires_at:
            logger.warning(f"CommCare OAuth token expired at {expires_at}")
            return False

        return True

    def get_coverage_data(self) -> CoverageData:
        """
        Get or build CoverageData with session caching.

        NOTE: Only fetches DUs (for polygons). Visits are fetched separately
        via the analysis framework for consistent caching.
        """
        opportunity_id = getattr(self.request, "labs_context", {}).get("opportunity_id")

        if not opportunity_id:
            raise ValueError("No opportunity selected in labs context")

        # Always fetch fresh - DU status can change in CommCare, no way to detect changes
        logger.info(f"[Coverage] Fetching fresh DU data from CommCare (opp {opportunity_id})")
        data_access = CoverageDataAccess(self.request)
        coverage = data_access.build_coverage_dus_only()

        return coverage

    def populate_coverage_visits(self, coverage: CoverageData, visit_rows: list[VisitRow]) -> None:
        """
        Populate CoverageData with visits from VisitRows.

        Converts VisitRows to LocalUserVisits and links them to DUs/FLWs.

        Args:
            coverage: CoverageData to populate
            visit_rows: VisitRows from analysis framework
        """
        from commcare_connect.coverage.models import FLW, LocalUserVisit

        for visit_row in visit_rows:
            # Convert VisitRow to dict format expected by LocalUserVisit
            visit_data = {
                "xform_id": visit_row.id,
                "user_id": visit_row.user_id,
                "username": visit_row.username,
                "visit_date": visit_row.visit_date.isoformat() if visit_row.visit_date else None,
                "status": visit_row.status,
                "flagged": visit_row.flagged,
                "deliver_unit": {"name": visit_row.deliver_unit_name, "id": visit_row.deliver_unit_id},
                "form_json": {
                    "metadata": {
                        "location": f"{visit_row.latitude} {visit_row.longitude} 0.0 {visit_row.accuracy_in_m or 0.0}"
                    }
                },
            }

            point = LocalUserVisit(visit_data)
            coverage.service_points.append(point)

            # Update FLW visit tracking (merge with existing FLW from DU data if present)
            username = visit_row.username
            commcare_userid = visit_row.commcare_userid

            if username:
                # Check if FLW already exists under CommCare ID (from DU data)
                if commcare_userid and commcare_userid in coverage.flws:
                    # Re-key existing FLW from CommCare ID to username
                    flw = coverage.flws[commcare_userid]
                    flw.id = username  # Update ID to username
                    flw.name = username
                    coverage.flws[username] = flw
                    del coverage.flws[commcare_userid]
                    logger.debug(f"[Coverage] Re-keyed FLW {commcare_userid} -> {username}")
                elif username not in coverage.flws:
                    # Create new FLW if neither username nor CommCare ID exist
                    coverage.flws[username] = FLW(id=username, name=username)

                # Update FLW with visit data (works for both new and re-keyed FLWs)
                flw = coverage.flws[username]
                flw.total_visits += 1
                flw.service_points.append(point)

                # Track active dates
                if visit_row.visit_date:
                    visit_date = visit_row.visit_date.date()
                    if visit_date not in flw.dates_active:
                        flw.dates_active.append(visit_date)

        # Compute metadata (links visits to DUs)
        coverage._compute_metadata()

        logger.info(f"[Coverage] Populated {len(coverage.service_points)} visits into coverage data")


class CoverageIndexView(BaseCoverageView):
    """Landing page with opportunity selector and summary"""

    template_name = "coverage/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Check if context is selected
        labs_context = getattr(self.request, "labs_context", {})
        context["has_context"] = bool(labs_context.get("opportunity_id"))
        context["has_commcare_oauth"] = self.check_commcare_oauth()

        if context["has_context"]:
            if not context["has_commcare_oauth"]:
                context["error"] = "CommCare OAuth not configured. Please authorize CommCare access."
                context["needs_oauth"] = True
            else:
                try:
                    # Get DU data
                    coverage = self.get_coverage_data()

                    # Get visits via analysis framework (base config, no computed fields)
                    from commcare_connect.coverage.analysis import COVERAGE_BASE_CONFIG, get_coverage_visit_analysis

                    du_lookup = {
                        du.du_name: {"service_area_id": du.service_area_id} for du in coverage.delivery_units.values()
                    }

                    result = get_coverage_visit_analysis(
                        request=self.request, config=COVERAGE_BASE_CONFIG, du_lookup=du_lookup, use_cache=True
                    )

                    # Populate coverage with visits
                    self.populate_coverage_visits(coverage, result.rows)

                    context["coverage"] = coverage
                    context["summary_stats"] = {
                        "total_dus": len(coverage.delivery_units),
                        "total_sas": len(coverage.service_areas),
                        "total_flws": len(coverage.flws),
                        "total_visits": len(coverage.service_points),
                        "completion": round(coverage.completion_percentage, 1),
                    }
                    context["service_points_count"] = len(result.rows)
                except Exception as e:
                    logger.error(f"Failed to load coverage data: {e}", exc_info=True)
                    context["error"] = str(e)
                    # Check if error is about missing OAuth
                    if "CommCare OAuth" in str(e):
                        context["needs_oauth"] = True

        return context


class BaseCoverageMapView(BaseCoverageView):
    """Base interactive Leaflet map with optional analysis config for computed fields.

    Note: This is a base class. Use CoverageMapView instead, which adds FLW color-coding.
    """

    template_name = "coverage/map.html"

    # Override in subclass to use a specific analysis config
    analysis_config: AnalysisConfig | None = None

    def get_analysis_config(self) -> AnalysisConfig | None:
        """
        Get the analysis config to use for computing visit fields.

        Checks URL parameter first (?config=chc_nutrition), then falls back
        to class attribute. Returns None for basic coverage view (no computed fields).
        """
        # Check URL parameter first
        config_name = self.request.GET.get("config")
        if config_name:
            from commcare_connect.coverage.config_registry import get_config

            config = get_config(config_name)
            if config:
                logger.info(f"[Coverage] Using analysis config: {config_name} ({len(config.fields)} fields)")
                # Log first few field names
                field_names = [f.name for f in config.fields[:5]]
                logger.info(f"[Coverage] Config fields (first 5): {field_names}")
                return config
            # Log warning if config name not found
            logger.warning(f"[Coverage] Config '{config_name}' not found in registry")

        # Fall back to class attribute
        return self.analysis_config

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["has_commcare_oauth"] = self.check_commcare_oauth()

        if not context["has_commcare_oauth"]:
            context["error"] = "CommCare OAuth not configured. Please authorize CommCare access."
            context["needs_oauth"] = True
            context["delivery_units_geojson"] = json.dumps({"type": "FeatureCollection", "features": []})
            context["service_points_geojson"] = json.dumps({"type": "FeatureCollection", "features": []})
            context["flw_list"] = []
            context["service_area_list"] = []
            context["computed_field_metadata"] = []
        else:
            try:
                # Get DU data (polygons)
                coverage = self.get_coverage_data()
                logger.info(f"[Coverage] Loaded {len(coverage.delivery_units)} DUs, {len(coverage.service_areas)} SAs")
                if coverage.delivery_units:
                    sample_dus = list(coverage.delivery_units.keys())[:5]
                    logger.info(f"[Coverage] Sample DU names from CommCare: {sample_dus}")
                if coverage.service_areas:
                    sample_sas = list(coverage.service_areas.keys())[:5]
                    logger.info(f"[Coverage] Sample SA IDs from CommCare: {sample_sas}")
                else:
                    logger.warning("[Coverage] No service areas found in DU data!")

                # Get analysis config (use base if none specified)
                config = self.get_analysis_config()
                if not config:
                    from commcare_connect.coverage.analysis import COVERAGE_BASE_CONFIG

                    config = COVERAGE_BASE_CONFIG
                    logger.error(
                        "[Coverage] ERROR: Using fallback base config! "
                        "No proper config specified. Pass ?config=chc_nutrition in URL."
                    )

                # ALWAYS use analysis framework for visits (consistent caching)
                visit_rows, field_metadata = self.get_enriched_visits(config, coverage)

                # Populate coverage with visits from analysis
                self.populate_coverage_visits(coverage, visit_rows)

                context["coverage"] = coverage

                # Build GeoJSON for map
                context["delivery_units_geojson"] = self.build_du_geojson(coverage)
                context["service_points_geojson"] = self.build_enriched_points_geojson(visit_rows)
                context["computed_field_metadata"] = field_metadata

                context["flw_list"] = [
                    {"id": flw.id, "name": flw.name, "visits": flw.total_visits} for flw in coverage.flws.values()
                ]
                context["service_area_list"] = sorted(list(coverage.service_areas.keys()))
                context["service_points_count"] = len(visit_rows)
            except Exception as e:
                logger.error(f"Failed to load coverage data for map: {e}", exc_info=True)
                context["error"] = str(e)
                context["delivery_units_geojson"] = json.dumps({"type": "FeatureCollection", "features": []})
                context["service_points_geojson"] = json.dumps({"type": "FeatureCollection", "features": []})
                context["flw_list"] = []
                context["service_area_list"] = []
                context["computed_field_metadata"] = []
                # Check if error is about missing OAuth
                if "CommCare OAuth" in str(e):
                    context["needs_oauth"] = True

        return context

    def get_enriched_visits(self, config: AnalysisConfig, coverage: CoverageData) -> tuple[list[VisitRow], list[dict]]:
        """
        Get visit analysis with coverage context, using cached data.

        Uses the pipeline pattern:
        1. Get cached VisitAnalysisResult (shared with CHC Nutrition and other views)
        2. Enrich with DU/SA geographic context

        Args:
            config: AnalysisConfig defining field computations
            coverage: CoverageData with DU info for service area lookup

        Returns:
            Tuple of (visit_rows, field_metadata)
        """
        # Build DU lookup for service area enrichment
        # Add BOTH id and name as keys since visits might use either
        du_lookup = {}
        for du in coverage.delivery_units.values():
            du_info = {"service_area_id": du.service_area_id}
            du_lookup[du.du_name] = du_info  # Add by name
            du_lookup[du.id] = du_info  # Add by case_id
            try:
                du_lookup[int(du.id)] = du_info  # Add as integer if possible
            except (ValueError, TypeError):
                pass

        # Get cached visit analysis with coverage enrichment
        result = get_coverage_visit_analysis(request=self.request, config=config, du_lookup=du_lookup, use_cache=True)

        return result.rows, result.field_metadata

    def build_du_geojson(self, coverage: CoverageData) -> str:
        """Convert DUs to GeoJSON"""
        features = []

        for du in coverage.delivery_units.values():
            try:
                # Skip DUs without valid WKT
                if not du.wkt or du.wkt == "":
                    continue

                geometry = du.geometry
                features.append(
                    {
                        "type": "Feature",
                        "geometry": mapping(geometry),
                        "properties": {
                            "name": du.du_name,
                            "service_area": du.service_area_id,
                            "status": du.status or "unvisited",
                            "buildings": du.buildings,
                            "visits": len(du.service_points),
                            "flw_id": du.flw_commcare_id,
                        },
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to process DU {du.du_name} for GeoJSON: {e}")
                continue

        return json.dumps({"type": "FeatureCollection", "features": features})

    def build_points_geojson(self, coverage: CoverageData) -> str:
        """Convert service points to GeoJSON (original, no computed fields)"""
        features = []

        for point in coverage.service_points:
            try:
                # Skip points with invalid coordinates
                if point.latitude == 0.0 and point.longitude == 0.0:
                    continue

                features.append(
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [point.longitude, point.latitude]},
                        "properties": {
                            "id": point.id,
                            "username": point.username,
                            "du_name": point.deliver_unit_name,
                            "status": point.status,
                            "date": point.visit_date.isoformat() if point.visit_date else "",
                            "flagged": point.flagged,
                            "accuracy": point.accuracy_in_m,
                        },
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to process visit point {point.id} for GeoJSON: {e}")
                continue

        return json.dumps({"type": "FeatureCollection", "features": features})

    def build_enriched_points_geojson(self, visit_rows: list[VisitRow]) -> str:
        """Convert visit rows to GeoJSON with computed fields"""
        features = []

        for visit in visit_rows:
            try:
                # Skip visits without valid GPS
                if not visit.has_gps:
                    continue

                features.append(
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [visit.longitude, visit.latitude]},
                        "properties": visit.to_geojson_properties(),
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to process enriched visit {visit.id} for GeoJSON: {e}")
                continue

        return json.dumps({"type": "FeatureCollection", "features": features})


class CoverageMapView(BaseCoverageMapView):
    """
    Enhanced coverage map with FLW color-coding.

    Extends BaseCoverageMapView to add:
    - Unique colors for each FLW
    - Colored delivery unit polygons
    - Colored service point markers
    - FLW filter with color swatches
    """

    template_name = "coverage/map.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # If we have coverage data, add FLW colors
        if "coverage" in context and not context.get("error"):
            coverage = context["coverage"]

            # Generate colors for FLWs
            flw_colors = generate_flw_colors(coverage.flws)
            context["flw_colors"] = flw_colors

            # Get analysis config for visit data access
            config = self.get_analysis_config()
            if not config:
                from commcare_connect.coverage.analysis import COVERAGE_BASE_CONFIG

                config = COVERAGE_BASE_CONFIG

            # Build du_lookup
            du_lookup = {}
            for du in coverage.delivery_units.values():
                du_info = {"service_area_id": du.service_area_id}
                du_lookup[du.du_name] = du_info
                du_lookup[du.id] = du_info
                try:
                    du_lookup[int(du.id)] = du_info
                except (ValueError, TypeError):
                    pass

            # Get visit data to build CommCare ID → username mapping
            from commcare_connect.coverage.analysis import get_coverage_visit_analysis

            use_cache = self.request.GET.get("refresh") != "1"
            result = get_coverage_visit_analysis(
                request=self.request, config=config, du_lookup=du_lookup, use_cache=use_cache
            )

            # Build mapping: commcare_userid → username
            commcare_to_username = {}
            for visit in result.rows:
                if visit.commcare_userid and visit.username:
                    commcare_to_username[visit.commcare_userid] = visit.username

            logger.info(f"[Coverage Map] Built FLW ID mapping with {len(commcare_to_username)} entries")
            logger.info(f"[Coverage Map] FLWs after loading: {len(coverage.flws)}")

            # Build colored GeoJSON with username mapping
            context["delivery_units_geojson"] = self.build_colored_du_geojson(
                coverage, flw_colors, commcare_to_username
            )

            # Build colored service points (using already-fetched result)
            context["service_points_geojson"] = self.build_colored_points_geojson(
                result.rows, coverage.flws, flw_colors
            )

            # Build FLW list with colors for UI
            # FLWs are now properly merged during loading, so we just need to format them
            context["flw_list_colored"] = [
                {
                    "id": flw_id,
                    "name": flw.name,
                    "visits": flw.total_visits,
                    "color": flw_colors.get(flw_id, "#999999"),
                }
                for flw_id, flw in coverage.flws.items()
            ]

            # Add service area list
            service_area_list = sorted(list(coverage.service_areas.keys()))
            logger.info(f"[Coverage Map2] Found {len(service_area_list)} service areas: {service_area_list}")
            context["service_area_list"] = service_area_list
            context["service_points_count"] = len(result.rows)

        return context

    def build_colored_du_geojson(self, coverage: CoverageData, flw_colors: dict, commcare_to_username: dict) -> str:
        """Build DU GeoJSON with FLW colors and username mapping"""
        features = []

        for du in coverage.delivery_units.values():
            try:
                if not du.wkt or du.wkt == "":
                    continue

                geometry = du.geometry

                # Map CommCare owner ID to username for consistent filtering
                flw_username = commcare_to_username.get(du.flw_commcare_id, du.flw_commcare_id)
                flw_color = flw_colors.get(flw_username, "#999999")

                features.append(
                    {
                        "type": "Feature",
                        "geometry": mapping(geometry),
                        "properties": {
                            "name": du.du_name,
                            "service_area": du.service_area_id,
                            "status": du.status or "unvisited",
                            "buildings": du.buildings,
                            "visits": len(du.service_points),
                            "flw_id": du.flw_commcare_id,  # Keep original for reference
                            "username": flw_username,  # Add username for filtering
                            "color": flw_color,
                        },
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to process DU {du.du_name}: {e}")
                continue

        return json.dumps({"type": "FeatureCollection", "features": features})

    def build_colored_points_geojson(self, visit_rows: list[VisitRow], flws: dict, flw_colors: dict) -> str:
        """Build service points GeoJSON with FLW colors"""
        features = []

        for visit in visit_rows:
            try:
                if not visit.has_gps:
                    continue

                # Match by username (CommCare username hash), not user_id
                flw_color = flw_colors.get(visit.username, "#999999")

                props = visit.to_geojson_properties()
                props["color"] = flw_color
                props["username"] = visit.username  # Use username consistently for filtering

                features.append(
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [visit.longitude, visit.latitude]},
                        "properties": props,
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to process visit {visit.id}: {e}")
                continue

        return json.dumps({"type": "FeatureCollection", "features": features})


class CoverageTokenStatusView(LoginRequiredMixin, TemplateView):
    """Debug view to check OAuth token status"""

    template_name = "coverage/token_status.html"

    def get_context_data(self, **kwargs):
        from django.utils import timezone

        context = super().get_context_data(**kwargs)

        # Check Connect OAuth
        labs_oauth = self.request.session.get("labs_oauth", {})
        context["has_connect_token"] = bool(labs_oauth.get("access_token"))
        context["connect_expires_at"] = labs_oauth.get("expires_at", 0)

        # Check CommCare OAuth
        commcare_oauth = self.request.session.get("commcare_oauth", {})
        context["has_commcare_token"] = bool(commcare_oauth.get("access_token"))
        context["commcare_expires_at"] = commcare_oauth.get("expires_at", 0)

        # Check if expired
        now = timezone.now().timestamp()
        context["connect_expired"] = context["connect_expires_at"] < now if context["connect_expires_at"] else True
        context["commcare_expired"] = context["commcare_expires_at"] < now if context["commcare_expires_at"] else True

        return context


class CoverageDebugView(LoginRequiredMixin, TemplateView):
    """Debug view to list accessible opportunities"""

    template_name = "coverage/debug.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get access token
        access_token = self.request.session.get("labs_oauth", {}).get("access_token")

        if not access_token:
            context["error"] = "No OAuth token found"
            context["opportunities"] = []
            return context

        try:
            # Fetch all opportunities from API
            url = f"{settings.CONNECT_PRODUCTION_URL}/export/opp_org_program_list/"
            response = httpx.get(url, headers={"Authorization": f"Bearer {access_token}"}, timeout=30.0)
            response.raise_for_status()

            data = response.json()
            opportunities = data.get("opportunities", [])

            # Format for display
            context["opportunities"] = [
                {
                    "id": opp.get("id"),
                    "name": opp.get("name"),
                    "program": opp.get("program_name"),
                    "organization": opp.get("organization"),
                    "has_deliver_app": bool(opp.get("deliver_app")),
                    "cc_domain": opp.get("deliver_app", {}).get("cc_domain") if opp.get("deliver_app") else None,
                }
                for opp in opportunities
            ]

            context["total_count"] = len(context["opportunities"])
        except Exception as e:
            logger.error(f"Failed to fetch opportunities: {e}", exc_info=True)
            context["error"] = str(e)
            context["opportunities"] = []

        return context
