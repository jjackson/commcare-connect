"""
Service layer for loading admin boundaries from multiple sources.

Supported sources:
- geoBoundaries (https://www.geoboundaries.org/) - CC BY 4.0
- OpenStreetMap (https://www.openstreetmap.org/) - ODbL
- GRID3 (https://grid3.org/) - varies by country
- HDX/OCHA COD (https://data.humdata.org/) - varies by dataset
"""

import io
import json
import logging
import re
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Polygon
from django.core.files.uploadedfile import UploadedFile

from commcare_connect.labs.admin_boundaries.models import (
    AdminBoundary,
    AdminBoundarySourceConfig,
    AdminBoundaryStaticLoadRecord,
)

logger = logging.getLogger(__name__)

# Path to the fixtures directory
FIXTURES_DIR = Path(__file__).parent / "fixtures"


@dataclass
class LoadResult:
    """Result of a boundary loading operation."""

    iso_code: str
    level: int
    success: bool
    count: int = 0
    message: str = ""
    error: str = ""


@dataclass
class CountryLoadResult:
    """Result of loading all levels for a country."""

    iso_code: str
    source: str = ""
    total_loaded: int = 0
    levels: list[LoadResult] = field(default_factory=list)
    cleared: int = 0

    @property
    def success(self) -> bool:
        return any(r.success for r in self.levels)


class GeoBoundariesLoader:
    """
    Service for loading administrative boundaries from geoBoundaries API.

    Usage:
        loader = GeoBoundariesLoader()

        # Load with progress callback
        def on_progress(msg):
            print(msg)

        result = loader.load_country("KEN", levels=[0, 1, 2], on_progress=on_progress)
        print(f"Loaded {result.total_loaded} boundaries")
    """

    GEOBOUNDARIES_API = "https://www.geoboundaries.org/api/current/gbOpen"
    DEFAULT_LEVELS = [0, 1, 2]  # Country, State/Province, District
    MAX_LEVEL = 5  # geoBoundaries goes up to ADM5 for some countries
    SOURCE = AdminBoundary.Source.GEOBOUNDARIES

    def __init__(self):
        self.http_client = httpx.Client(timeout=120.0, follow_redirects=True)

    def __del__(self):
        if hasattr(self, "http_client"):
            self.http_client.close()

    def load_country(
        self,
        iso_code: str,
        levels: list[int] | None = None,
        clear: bool = False,
        on_progress: Callable[[str], None] | None = None,
    ) -> CountryLoadResult:
        """
        Load boundaries for a country at specified admin levels.

        Args:
            iso_code: ISO 3166-1 alpha-3 country code (e.g., "KEN")
            levels: Admin levels to load (default: [0, 1, 2])
            clear: If True, delete existing boundaries before loading
            on_progress: Optional callback for progress messages

        Returns:
            CountryLoadResult with details of what was loaded
        """
        iso_code = iso_code.upper()
        levels = levels if levels is not None else self.DEFAULT_LEVELS

        result = CountryLoadResult(iso_code=iso_code, source=self.SOURCE)

        def progress(msg: str):
            if on_progress:
                on_progress(msg)
            logger.info(f"[geoBoundaries/{iso_code}] {msg}")

        progress(f"Processing {iso_code} from geoBoundaries...")

        # Clear existing data if requested (only for this source)
        if clear:
            deleted, _ = AdminBoundary.objects.filter(iso_code=iso_code, source=self.SOURCE).delete()
            result.cleared = deleted
            progress(f"Cleared {deleted} existing geoBoundaries entries")

        # Load each level
        for level in levels:
            level_result = self.load_boundary_level(iso_code, level, on_progress=on_progress)
            result.levels.append(level_result)
            if level_result.success:
                result.total_loaded += level_result.count

        progress(f"Complete - loaded {result.total_loaded} boundaries for {iso_code}")
        return result

    def load_boundary_level(
        self,
        iso_code: str,
        level: int,
        on_progress: Callable[[str], None] | None = None,
    ) -> LoadResult:
        """Load boundaries for a specific country and admin level."""
        iso_code = iso_code.upper()

        def progress(msg: str):
            if on_progress:
                on_progress(msg)

        api_url = f"{self.GEOBOUNDARIES_API}/{iso_code}/ADM{level}/"

        try:
            # First, get the metadata to find the GeoJSON download URL
            progress(f"ADM{level}: Fetching metadata...")
            response = self.http_client.get(api_url, timeout=30.0)

            if response.status_code == 404:
                return LoadResult(
                    iso_code=iso_code,
                    level=level,
                    success=False,
                    message=f"ADM{level} not available for {iso_code}",
                )

            response.raise_for_status()
            metadata = response.json()

            # Get the simplified GeoJSON URL
            geojson_url = metadata.get("gjDownloadURL")
            if not geojson_url:
                return LoadResult(
                    iso_code=iso_code,
                    level=level,
                    success=False,
                    error="No GeoJSON URL in API response",
                )

            # Download the GeoJSON
            progress(f"ADM{level}: Downloading GeoJSON...")
            geojson_response = self.http_client.get(geojson_url)
            geojson_response.raise_for_status()
            geojson_data = geojson_response.json()

            features = geojson_data.get("features", [])
            if not features:
                return LoadResult(
                    iso_code=iso_code,
                    level=level,
                    success=False,
                    message=f"ADM{level}: No features found",
                )

            # Process and save boundaries
            progress(f"ADM{level}: Processing {len(features)} features...")
            boundaries_to_create = []
            skipped = 0

            for feature in features:
                try:
                    boundary = self._feature_to_boundary(feature, iso_code, level, geojson_url)
                    if boundary:
                        boundaries_to_create.append(boundary)
                except Exception as e:
                    shape_name = feature.get("properties", {}).get("shapeName", "unknown")
                    logger.warning(f"Skipping {shape_name}: {e}")
                    skipped += 1

            # Delete existing for this country/level/source and bulk create
            AdminBoundary.objects.filter(iso_code=iso_code, admin_level=level, source=self.SOURCE).delete()
            AdminBoundary.objects.bulk_create(boundaries_to_create, batch_size=100)

            message = f"ADM{level}: Loaded {len(boundaries_to_create)} boundaries"
            if skipped:
                message += f" (skipped {skipped})"
            progress(message)

            return LoadResult(
                iso_code=iso_code,
                level=level,
                success=True,
                count=len(boundaries_to_create),
                message=message,
            )

        except httpx.HTTPStatusError as e:
            error = f"HTTP error: {e}"
            logger.error(f"[geoBoundaries/{iso_code}] ADM{level}: {error}")
            return LoadResult(iso_code=iso_code, level=level, success=False, error=error)

        except httpx.RequestError as e:
            error = f"Request error: {e}"
            logger.error(f"[geoBoundaries/{iso_code}] ADM{level}: {error}")
            return LoadResult(iso_code=iso_code, level=level, success=False, error=error)

        except Exception as e:
            error = f"Error: {e}"
            logger.error(f"[geoBoundaries/{iso_code}] ADM{level}: {error}")
            return LoadResult(iso_code=iso_code, level=level, success=False, error=error)

    def _feature_to_boundary(self, feature: dict, iso_code: str, level: int, source_url: str) -> AdminBoundary | None:
        """Convert a GeoJSON feature to an AdminBoundary model instance."""
        properties = feature.get("properties", {})
        geometry_data = feature.get("geometry")

        if not geometry_data:
            return None

        geom = GEOSGeometry(json.dumps(geometry_data))

        # Ensure it's a MultiPolygon
        if isinstance(geom, Polygon):
            geom = MultiPolygon(geom)
        elif not isinstance(geom, MultiPolygon):
            raise ValueError(f"Unexpected geometry type: {geom.geom_type}")

        # Extract properties - geoBoundaries uses consistent field names
        shape_id = properties.get("shapeID", "")
        shape_name = properties.get("shapeName", "")

        if not shape_id:
            # Generate an ID if not present
            shape_id = f"gb-{iso_code}-ADM{level}-{shape_name}".replace(" ", "_")

        return AdminBoundary(
            iso_code=iso_code,
            admin_level=level,
            name=shape_name,
            name_local=properties.get("shapeNameLocal", ""),
            boundary_id=shape_id,
            geometry=geom,
            source=self.SOURCE,
            source_url=source_url,
        )


class OSMLoader:
    """
    Service for loading administrative boundaries from OpenStreetMap via Overpass API.

    OSM admin_level values vary by country. Common mappings:
    - admin_level 2: Country
    - admin_level 4: State/Province/Region
    - admin_level 6: County/District
    - admin_level 8: Municipality/City

    Usage:
        loader = OSMLoader()
        result = loader.load_country("KEN", levels=[0, 1, 2], on_progress=print)
    """

    OVERPASS_API = "https://overpass-api.de/api/interpreter"
    SOURCE = AdminBoundary.Source.OSM

    # Default mapping from our ADM levels to OSM admin_level
    # This can be overridden per-country
    DEFAULT_LEVEL_MAPPING = {
        0: 2,  # ADM0 (country) -> OSM admin_level 2
        1: 4,  # ADM1 (state/province) -> OSM admin_level 4
        2: 6,  # ADM2 (district/county) -> OSM admin_level 6
        3: 8,  # ADM3 (municipality) -> OSM admin_level 8
        4: 10,  # ADM4 (ward/neighborhood) -> OSM admin_level 10
    }

    # Country-specific overrides where OSM levels differ
    COUNTRY_LEVEL_MAPPING = {
        # Some countries use different OSM levels
        # Add overrides here as needed
    }

    def __init__(self):
        self.http_client = httpx.Client(timeout=300.0, follow_redirects=True)

    def __del__(self):
        if hasattr(self, "http_client"):
            self.http_client.close()

    def get_osm_level(self, iso_code: str, adm_level: int) -> int:
        """Get the OSM admin_level for a given ADM level and country."""
        if iso_code in self.COUNTRY_LEVEL_MAPPING:
            mapping = self.COUNTRY_LEVEL_MAPPING[iso_code]
            if adm_level in mapping:
                return mapping[adm_level]
        return self.DEFAULT_LEVEL_MAPPING.get(adm_level, 2 + (adm_level * 2))

    def load_country(
        self,
        iso_code: str,
        levels: list[int] | None = None,
        clear: bool = False,
        on_progress: Callable[[str], None] | None = None,
    ) -> CountryLoadResult:
        """
        Load boundaries for a country at specified admin levels from OSM.

        Args:
            iso_code: ISO 3166-1 alpha-3 country code (e.g., "KEN")
            levels: Admin levels to load (default: [0, 1, 2])
            clear: If True, delete existing OSM boundaries before loading
            on_progress: Optional callback for progress messages

        Returns:
            CountryLoadResult with details of what was loaded
        """
        iso_code = iso_code.upper()
        levels = levels if levels is not None else [0, 1, 2]

        result = CountryLoadResult(iso_code=iso_code, source=self.SOURCE)

        def progress(msg: str):
            if on_progress:
                on_progress(msg)
            logger.info(f"[OSM/{iso_code}] {msg}")

        progress(f"Processing {iso_code} from OpenStreetMap...")

        # Clear existing OSM data if requested
        if clear:
            deleted, _ = AdminBoundary.objects.filter(iso_code=iso_code, source=self.SOURCE).delete()
            result.cleared = deleted
            progress(f"Cleared {deleted} existing OSM entries")

        # Load each level
        for level in levels:
            level_result = self.load_boundary_level(iso_code, level, on_progress=on_progress)
            result.levels.append(level_result)
            if level_result.success:
                result.total_loaded += level_result.count

        progress(f"Complete - loaded {result.total_loaded} boundaries for {iso_code}")
        return result

    def load_boundary_level(
        self,
        iso_code: str,
        level: int,
        on_progress: Callable[[str], None] | None = None,
    ) -> LoadResult:
        """Load boundaries for a specific country and admin level from OSM."""
        iso_code = iso_code.upper()
        osm_level = self.get_osm_level(iso_code, level)

        def progress(msg: str):
            if on_progress:
                on_progress(msg)

        progress(f"ADM{level}: Querying OSM (admin_level={osm_level})...")

        # Build Overpass query
        # We use ISO3166-1:alpha3 tag to find the country area, then query admin boundaries within it
        query = f"""
        [out:json][timeout:180];
        area["ISO3166-1:alpha3"="{iso_code}"]->.country;
        (
          relation["boundary"="administrative"]["admin_level"="{osm_level}"](area.country);
        );
        out geom;
        """

        # Retry logic for flaky Overpass API
        max_retries = 3
        retry_delay = 5  # seconds

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    import time

                    progress(f"ADM{level}: Retry {attempt}/{max_retries - 1} after {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff

                response = self.http_client.post(
                    self.OVERPASS_API,
                    data={"data": query},
                    timeout=180.0,
                )
                response.raise_for_status()
                data = response.json()
                break  # Success, exit retry loop

            except (httpx.RequestError, httpx.TimeoutException) as e:
                logger.warning(f"[OSM/{iso_code}] ADM{level}: Attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    # Last attempt failed
                    if isinstance(e, httpx.TimeoutException):
                        error = "Request timed out after retries - OSM query may be too large"
                    else:
                        error = f"Request error after {max_retries} retries: {e}"
                    logger.error(f"[OSM/{iso_code}] ADM{level}: {error}")
                    return LoadResult(iso_code=iso_code, level=level, success=False, error=error)
                continue

        # Process the response
        try:
            elements = data.get("elements", [])
            if not elements:
                return LoadResult(
                    iso_code=iso_code,
                    level=level,
                    success=False,
                    message=f"ADM{level}: No OSM boundaries found (admin_level={osm_level})",
                )

            progress(f"ADM{level}: Processing {len(elements)} OSM relations...")
            boundaries_to_create = []
            skipped = 0

            for element in elements:
                try:
                    boundary = self._element_to_boundary(element, iso_code, level)
                    if boundary:
                        boundaries_to_create.append(boundary)
                except Exception as e:
                    name = element.get("tags", {}).get("name", f"relation/{element.get('id', 'unknown')}")
                    logger.warning(f"Skipping {name}: {e}")
                    skipped += 1

            # Delete existing for this country/level/source and bulk create
            AdminBoundary.objects.filter(iso_code=iso_code, admin_level=level, source=self.SOURCE).delete()
            AdminBoundary.objects.bulk_create(boundaries_to_create, batch_size=100)

            message = f"ADM{level}: Loaded {len(boundaries_to_create)} boundaries from OSM"
            if skipped:
                message += f" (skipped {skipped})"
            progress(message)

            return LoadResult(
                iso_code=iso_code,
                level=level,
                success=True,
                count=len(boundaries_to_create),
                message=message,
            )

        except Exception as e:
            error = f"Error processing OSM data: {e}"
            logger.error(f"[OSM/{iso_code}] ADM{level}: {error}", exc_info=True)
            return LoadResult(iso_code=iso_code, level=level, success=False, error=error)

    def _element_to_boundary(self, element: dict, iso_code: str, level: int) -> AdminBoundary | None:
        """Convert an OSM relation element to an AdminBoundary model instance."""
        if element.get("type") != "relation":
            return None

        tags = element.get("tags", {})
        osm_id = element.get("id")

        if not osm_id:
            return None

        # Build geometry from members
        geometry = self._build_geometry(element)
        if geometry is None:
            return None

        # Extract name
        name = tags.get("name", tags.get("name:en", f"OSM-{osm_id}"))
        name_local = tags.get("name:local", tags.get("official_name", ""))

        return AdminBoundary(
            iso_code=iso_code,
            admin_level=level,
            name=name,
            name_local=name_local,
            boundary_id=f"osm-{osm_id}",
            geometry=geometry,
            source=self.SOURCE,
            source_url=f"https://www.openstreetmap.org/relation/{osm_id}",
        )

    def _build_geometry(self, element: dict) -> MultiPolygon | None:
        """Build a MultiPolygon geometry from OSM relation members."""
        # When using 'out geom', the geometry is included directly
        members = element.get("members", [])

        # Collect all outer and inner ways
        outer_rings = []
        inner_rings = []

        for member in members:
            role = member.get("role", "")
            geom = member.get("geometry", [])

            if not geom:
                continue

            # Convert geometry points to coordinate list
            coords = [(point["lon"], point["lat"]) for point in geom if "lon" in point and "lat" in point]

            if len(coords) < 4:  # Need at least 4 points for a valid ring
                continue

            # Ensure ring is closed
            if coords[0] != coords[-1]:
                coords.append(coords[0])

            if role == "outer":
                outer_rings.append(coords)
            elif role == "inner":
                inner_rings.append(coords)

        if not outer_rings:
            return None

        # Build polygons - for simplicity, create one polygon per outer ring
        # A more sophisticated approach would match inner rings to their containing outer ring
        polygons = []
        for outer in outer_rings:
            try:
                # Create polygon with just the outer ring
                poly_coords = [outer]
                poly = Polygon(*poly_coords)
                if poly.valid:
                    polygons.append(poly)
            except Exception as e:
                logger.debug(f"Failed to create polygon: {e}")
                continue

        if not polygons:
            return None

        return MultiPolygon(polygons)


class URLBasedLoader:
    """
    Service for loading administrative boundaries from direct GeoJSON URLs.

    Used for sources like GRID3 and HDX that don't have standardized APIs
    but provide downloadable GeoJSON files.

    Usage:
        loader = URLBasedLoader("grid3")
        result = loader.load_boundary_level(
            iso_code="NGA",
            level=3,
            level_config={"url": "https://...", "name_field": "wardname", "id_field": "wardcode"},
            on_progress=print,
        )
    """

    def __init__(self, source: str):
        """Initialize with source identifier.

        Args:
            source: Source identifier ("grid3" or "hdx")
        """
        self.source = source
        self.http_client = httpx.Client(timeout=300.0, follow_redirects=True)

    def __del__(self):
        if hasattr(self, "http_client"):
            self.http_client.close()

    def load_boundary_level(
        self,
        iso_code: str,
        level: int,
        level_config: dict,
        on_progress: Callable[[str], None] | None = None,
    ) -> LoadResult:
        """Load boundaries for a specific country and admin level from a URL.

        Args:
            iso_code: ISO 3166-1 alpha-3 country code
            level: Admin level to load
            level_config: Configuration dict with url, name_field, id_field
            on_progress: Optional callback for progress messages

        Returns:
            LoadResult with details of what was loaded
        """
        iso_code = iso_code.upper()

        def progress(msg: str):
            if on_progress:
                on_progress(msg)
            logger.info(f"[{self.source}/{iso_code}] {msg}")

        url = level_config.get("url", "")
        name_field = level_config.get("name_field", "name")
        id_field = level_config.get("id_field", "id")

        if not url:
            return LoadResult(
                iso_code=iso_code,
                level=level,
                success=False,
                error=f"No URL configured for ADM{level}",
            )

        # Check if this is a placeholder URL
        if "PLACEHOLDER" in level_config.get("note", "") or not url.endswith(".geojson"):
            return LoadResult(
                iso_code=iso_code,
                level=level,
                success=False,
                error=f"ADM{level} URL not yet configured for {self.source}",
            )

        progress(f"ADM{level}: Downloading from {self.source}...")

        try:
            response = self.http_client.get(url, timeout=180.0)
            response.raise_for_status()
            geojson_data = response.json()

            features = geojson_data.get("features", [])
            if not features:
                return LoadResult(
                    iso_code=iso_code,
                    level=level,
                    success=False,
                    message=f"ADM{level}: No features found in GeoJSON",
                )

            progress(f"ADM{level}: Processing {len(features)} features...")
            boundaries_to_create = []
            skipped = 0

            for feature in features:
                try:
                    boundary = self._feature_to_boundary(feature, iso_code, level, url, name_field, id_field)
                    if boundary:
                        boundaries_to_create.append(boundary)
                except Exception as e:
                    props = feature.get("properties", {})
                    name = props.get(name_field, props.get("name", "unknown"))
                    logger.warning(f"Skipping {name}: {e}")
                    skipped += 1

            # Delete existing for this country/level/source and bulk create
            AdminBoundary.objects.filter(iso_code=iso_code, admin_level=level, source=self.source).delete()
            AdminBoundary.objects.bulk_create(boundaries_to_create, batch_size=100)

            message = f"ADM{level}: Loaded {len(boundaries_to_create)} boundaries from {self.source}"
            if skipped:
                message += f" (skipped {skipped})"
            progress(message)

            return LoadResult(
                iso_code=iso_code,
                level=level,
                success=True,
                count=len(boundaries_to_create),
                message=message,
            )

        except httpx.HTTPStatusError as e:
            error = f"HTTP error: {e}"
            logger.error(f"[{self.source}/{iso_code}] ADM{level}: {error}")
            return LoadResult(iso_code=iso_code, level=level, success=False, error=error)

        except httpx.RequestError as e:
            error = f"Request error: {e}"
            logger.error(f"[{self.source}/{iso_code}] ADM{level}: {error}")
            return LoadResult(iso_code=iso_code, level=level, success=False, error=error)

        except Exception as e:
            error = f"Error: {e}"
            logger.error(f"[{self.source}/{iso_code}] ADM{level}: {error}", exc_info=True)
            return LoadResult(iso_code=iso_code, level=level, success=False, error=error)

    def _feature_to_boundary(
        self,
        feature: dict,
        iso_code: str,
        level: int,
        source_url: str,
        name_field: str,
        id_field: str,
    ) -> AdminBoundary | None:
        """Convert a GeoJSON feature to an AdminBoundary model instance."""
        properties = feature.get("properties", {})
        geometry_data = feature.get("geometry")

        if not geometry_data:
            return None

        geom = GEOSGeometry(json.dumps(geometry_data))

        # Ensure it's a MultiPolygon
        if isinstance(geom, Polygon):
            geom = MultiPolygon(geom)
        elif not isinstance(geom, MultiPolygon):
            raise ValueError(f"Unexpected geometry type: {geom.geom_type}")

        # Extract name and ID from configured fields
        name = properties.get(name_field, properties.get("name", ""))
        feature_id = properties.get(id_field, properties.get("id", ""))

        if not feature_id:
            # Generate an ID if not present
            feature_id = f"{self.source}-{iso_code}-ADM{level}-{name}".replace(" ", "_")

        boundary_id = f"{self.source}-{feature_id}"

        return AdminBoundary(
            iso_code=iso_code,
            admin_level=level,
            name=name,
            name_local=properties.get("name_local", ""),
            boundary_id=boundary_id,
            geometry=geom,
            source=self.source,
            source_url=source_url,
        )


class GeoPoDELoader:
    """
    Service for loading administrative boundaries from GeoPoDe file uploads.

    GeoPoDe (https://geopode.world/) provides high-quality admin boundary data
    exported as ZIP files containing GeoJSON files per admin level.

    File naming pattern: boundary_{level}_{source}.json
    Level names vary by country:
    - country -> ADM0
    - state/districts/counties/provinces/regions -> ADM1
    - lga/regions/subcounties/districts/departments -> ADM2
    - ward/communes/subdistricts -> ADM3

    Usage:
        loader = GeoPoDELoader()

        # Load from uploaded ZIP file
        result = loader.load_from_zip(uploaded_file, on_progress=print)

        # Load from individual GeoJSON file
        result = loader.load_from_geojson(json_content, "NGA", 1, on_progress=print)
    """

    SOURCE = AdminBoundary.Source.GEOPODE

    # Map level names from filenames to admin levels
    # Only used for unambiguous cases - hierarchical inference takes priority
    LEVEL_NAME_MAPPING = {
        # ADM0 - only country is unambiguous
        "country": 0,
        # ADM3 - these are usually the deepest level
        "ward": 3,
        "wards": 3,
        "communes": 3,
        "villages": 3,
        # ADM4
        "settlements": 4,
    }
    # Note: districts, regions, counties, provinces, subcounties, lga, etc.
    # are ambiguous - their level depends on context (hierarchy depth)

    def __init__(self):
        pass

    def load_from_zip(
        self,
        zip_file: UploadedFile | io.BytesIO,
        clear: bool = False,
        on_progress: Callable[[str], None] | None = None,
        filename: str = "",
    ) -> CountryLoadResult:
        """
        Load boundaries from a GeoPoDe ZIP file.

        Args:
            zip_file: Uploaded ZIP file or BytesIO containing GeoJSON files
            clear: If True, delete existing GeoPoDe boundaries before loading
            on_progress: Optional callback for progress messages
            filename: Optional filename to use for ISO extraction (if zip_file.name not available)

        Returns:
            CountryLoadResult with details of what was loaded
        """

        def progress(msg: str):
            if on_progress:
                on_progress(msg)
            logger.info(f"[GeoPoDe] {msg}")

        progress("Opening ZIP file...")

        try:
            # Try to extract ISO code from filename (e.g., GeoPoDe_NGA_Geometry_*.zip)
            zip_filename = filename
            if not zip_filename and hasattr(zip_file, "name"):
                zip_filename = str(zip_file.name)
            iso_from_filename = self._extract_iso_from_filename(zip_filename)

            # Handle both UploadedFile and BytesIO
            if hasattr(zip_file, "read"):
                zip_content = zip_file.read()
                if hasattr(zip_file, "seek"):
                    zip_file.seek(0)
            else:
                zip_content = zip_file

            with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
                # Find all JSON files
                json_files = [name for name in zf.namelist() if name.endswith(".json")]

                if not json_files:
                    return CountryLoadResult(
                        iso_code="",
                        source=self.SOURCE,
                        levels=[LoadResult(iso_code="", level=0, success=False, error="No JSON files found in ZIP")],
                    )

                progress(f"Found {len(json_files)} JSON files in ZIP")

                # Process each JSON file
                all_results = []
                iso_code = iso_from_filename  # Start with filename-derived ISO
                total_loaded = 0

                for json_filename in sorted(json_files):
                    progress(f"Processing {json_filename}...")

                    try:
                        with zf.open(json_filename) as jf:
                            geojson_data = json.load(jf)

                        result = self._process_geojson(
                            geojson_data,
                            json_filename,
                            fallback_iso=iso_code,  # Pass fallback ISO from filename
                            clear=clear and len(all_results) == 0,  # Only clear on first file
                            on_progress=on_progress,
                        )

                        all_results.append(result)

                        if result.success:
                            total_loaded += result.count
                            # Use ISO from data if better than filename-derived
                            if result.iso_code and len(result.iso_code) == 3:
                                iso_code = result.iso_code

                    except Exception as e:
                        logger.error(f"[GeoPoDe] Error processing {json_filename}: {e}")
                        all_results.append(
                            LoadResult(
                                iso_code=iso_code or "",
                                level=-1,
                                success=False,
                                error=f"Error processing {json_filename}: {e}",
                            )
                        )

                progress(f"Complete - loaded {total_loaded} boundaries from {len(json_files)} files")

                return CountryLoadResult(
                    iso_code=iso_code or "",
                    source=self.SOURCE,
                    total_loaded=total_loaded,
                    levels=all_results,
                )

        except zipfile.BadZipFile:
            return CountryLoadResult(
                iso_code="",
                source=self.SOURCE,
                levels=[LoadResult(iso_code="", level=0, success=False, error="Invalid ZIP file")],
            )
        except Exception as e:
            logger.error(f"[GeoPoDe] Error loading ZIP: {e}", exc_info=True)
            return CountryLoadResult(
                iso_code="",
                source=self.SOURCE,
                levels=[LoadResult(iso_code="", level=0, success=False, error=f"Error: {e}")],
            )

    def _process_geojson(
        self,
        geojson_data: dict,
        filename: str,
        fallback_iso: str = "",
        clear: bool = False,
        on_progress: Callable[[str], None] | None = None,
    ) -> LoadResult:
        """Process a single GeoJSON file from GeoPoDe."""

        def progress(msg: str):
            if on_progress:
                on_progress(msg)

        features = geojson_data.get("features", [])
        if not features:
            return LoadResult(iso_code="", level=0, success=False, message=f"No features in {filename}")

        # Extract level from filename: boundary_{level}_{source}.json
        level_name = self._extract_level_from_filename(filename)

        # Get ISO code and infer admin level from first feature
        first_props = features[0].get("properties", {})

        # Try to get ISO code from nested properties (WHO data has this)
        nested_props = first_props.get("properties", {})
        iso_code = nested_props.get("Iso_3_code", "")

        # Infer admin level from the level name and property structure
        admin_level = self._infer_admin_level(level_name, first_props)

        # If no ISO from nested properties, use fallback from ZIP filename
        if not iso_code and fallback_iso:
            iso_code = fallback_iso

        progress(f"{filename}: {len(features)} features, ADM{admin_level}, ISO={iso_code}")

        if clear:
            deleted, _ = AdminBoundary.objects.filter(
                iso_code=iso_code, admin_level=admin_level, source=self.SOURCE
            ).delete()
            if deleted:
                progress(f"Cleared {deleted} existing GeoPoDe entries for {iso_code} ADM{admin_level}")

        # Determine the name field based on level_name
        name_field = f"{level_name}_name"

        # Process features
        boundaries_to_create = []
        skipped = 0

        for feature in features:
            try:
                boundary = self._feature_to_boundary(feature, iso_code, admin_level, level_name, filename)
                if boundary:
                    boundaries_to_create.append(boundary)
            except Exception as e:
                props = feature.get("properties", {})
                name = props.get(name_field, props.get("global_id", "unknown"))
                logger.warning(f"[GeoPoDe] Skipping {name}: {e}")
                skipped += 1

        # Delete existing for this country/level/source and bulk create
        AdminBoundary.objects.filter(iso_code=iso_code, admin_level=admin_level, source=self.SOURCE).delete()
        AdminBoundary.objects.bulk_create(boundaries_to_create, batch_size=100)

        message = f"ADM{admin_level}: Loaded {len(boundaries_to_create)} boundaries"
        if skipped:
            message += f" (skipped {skipped})"

        return LoadResult(
            iso_code=iso_code,
            level=admin_level,
            success=True,
            count=len(boundaries_to_create),
            message=message,
        )

    def _extract_iso_from_filename(self, filename: str) -> str:
        """Extract ISO code from GeoPoDe ZIP filename.

        Pattern: GeoPoDe_{ISO}_Geometry_*.zip
        """
        if not filename:
            return ""

        basename = filename.split("/")[-1].split("\\")[-1]  # Handle paths

        # Try to match GeoPoDe_{ISO}_Geometry pattern
        match = re.search(r"GeoPoDe_([A-Z]{3})_", basename)
        if match:
            return match.group(1)

        return ""

    def _extract_level_from_filename(self, filename: str) -> str:
        """Extract the level name from a GeoPoDe filename."""
        # Pattern: boundary_{level}_{source}.json or just {level}.json
        basename = filename.split("/")[-1]  # Handle paths in ZIP
        basename = basename.replace(".json", "")

        # Try to match boundary_{level}_{source} pattern
        match = re.match(r"boundary_([^_]+)_", basename)
        if match:
            return match.group(1)

        # Fallback: split by underscore and take second part
        parts = basename.split("_")
        if len(parts) >= 2:
            return parts[1]

        return basename

    def _infer_admin_level(self, level_name: str, properties: dict) -> int:
        """Infer admin level from level name and property structure.

        The hierarchy is determined by counting *_name fields in the properties.
        GeoPoDe includes all parent levels' names, so deeper levels have more fields:
        - country file: 0 non-country _name fields -> ADM0
        - state/province/counties file: 1 field -> ADM1
        - district/lga/subcounties file: 2 fields -> ADM2
        - ward file: 3 fields -> ADM3
        """
        # First, check for unambiguous level names (country, ward, etc.)
        if level_name.lower() in self.LEVEL_NAME_MAPPING:
            return self.LEVEL_NAME_MAPPING[level_name.lower()]

        # Count *_name fields to infer depth from hierarchy
        # More _name fields = deeper level
        name_fields = [k for k in properties.keys() if k.endswith("_name") and k != "country_name"]
        if len(name_fields) == 0:
            return 0  # Country level
        elif len(name_fields) == 1:
            return 1  # ADM1
        elif len(name_fields) == 2:
            return 2  # ADM2
        elif len(name_fields) >= 3:
            return 3  # ADM3+

        return 1  # Default to ADM1

    def _feature_to_boundary(
        self,
        feature: dict,
        iso_code: str,
        level: int,
        level_name: str,
        source_filename: str,
    ) -> AdminBoundary | None:
        """Convert a GeoPoDe GeoJSON feature to an AdminBoundary."""
        properties = feature.get("properties", {})
        geometry_data = feature.get("geometry")

        if not geometry_data:
            return None

        geom = GEOSGeometry(json.dumps(geometry_data))

        # Ensure it's a MultiPolygon
        if isinstance(geom, Polygon):
            geom = MultiPolygon(geom)
        elif not isinstance(geom, MultiPolygon):
            raise ValueError(f"Unexpected geometry type: {geom.geom_type}")

        # Get the name from the level-specific field
        name_field = f"{level_name}_name"
        name = properties.get(name_field, "")

        # Fallback to other name patterns
        if not name:
            # Try common patterns
            for key in properties.keys():
                if key.endswith("_name") and key != "country_name":
                    name = properties[key]
                    break

        # Get global_id as boundary ID
        global_id = properties.get("global_id", "")
        if not global_id:
            # Generate one
            global_id = f"geopode-{iso_code}-{level}-{name}".replace(" ", "_")

        boundary_id = f"geopode-{global_id}"

        # Get local name from nested properties if available
        nested_props = properties.get("properties", {})
        name_local = ""
        if nested_props:
            # Look for viz_n (visualization name) which is often the local name
            for key in nested_props.keys():
                if "_viz_n" in key.lower() and key != "Adm0_viz_n":
                    name_local = nested_props.get(key, "")
                    break

        return AdminBoundary(
            iso_code=iso_code,
            admin_level=level,
            name=name,
            name_local=name_local,
            boundary_id=boundary_id,
            geometry=geom,
            source=self.SOURCE,
            source_url=f"geopode:{source_filename}",
        )


class CountrySourceRegistry:
    """
    Registry of available data sources per country.

    Loads country configurations from the JSON fixture and provides
    access to source configurations.

    Usage:
        registry = CountrySourceRegistry()

        # Get all configured countries
        countries = registry.get_all_countries()

        # Get config for a specific country
        nigeria = registry.get_country("NGA")
        if nigeria:
            sources = nigeria.get_available_sources()
            recommended = nigeria.get_recommended_source(3)

        # Check if a country supports a source/level
        config = registry.get_source_config("NGA", "grid3")
    """

    _instance = None
    _records: dict[str, AdminBoundaryStaticLoadRecord]

    def __new__(cls):
        """Singleton pattern to avoid reloading fixture multiple times."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._records = {}
            cls._instance._load_fixture()
        return cls._instance

    def _load_fixture(self):
        """Load country configurations from JSON fixture."""
        fixture_path = FIXTURES_DIR / "country_sources.json"

        if not fixture_path.exists():
            logger.warning(f"Country sources fixture not found: {fixture_path}")
            return

        try:
            with open(fixture_path) as f:
                data = json.load(f)

            for country_data in data:
                record = AdminBoundaryStaticLoadRecord(country_data)
                self._records[record.iso_code] = record

            logger.info(f"Loaded {len(self._records)} country configurations from fixture")

        except Exception as e:
            logger.error(f"Failed to load country sources fixture: {e}", exc_info=True)

    def reload(self):
        """Force reload of fixture data."""
        self._records = {}
        self._load_fixture()

    def get_country(self, iso_code: str) -> AdminBoundaryStaticLoadRecord | None:
        """Get configuration for a country by ISO code."""
        return self._records.get(iso_code.upper())

    def get_all_countries(self) -> list[AdminBoundaryStaticLoadRecord]:
        """Get all configured countries."""
        return list(self._records.values())

    def get_all_iso_codes(self) -> list[str]:
        """Get list of all configured ISO codes."""
        return sorted(self._records.keys())

    def get_source_config(self, iso_code: str, source: str) -> AdminBoundarySourceConfig | None:
        """Get source configuration for a country."""
        country = self.get_country(iso_code)
        if country:
            return country.get_source_config(source)
        return None

    def is_country_configured(self, iso_code: str) -> bool:
        """Check if a country has any configuration."""
        return iso_code.upper() in self._records


# Convenience function to get the appropriate loader
def get_loader(source: str):
    """Get the appropriate loader for the given source."""
    if source == AdminBoundary.Source.OSM or source == "osm":
        return OSMLoader()
    elif source == AdminBoundary.Source.GRID3 or source == "grid3":
        return URLBasedLoader("grid3")
    elif source == AdminBoundary.Source.HDX or source == "hdx":
        return URLBasedLoader("hdx")
    else:
        return GeoBoundariesLoader()


def get_source_display_name(source: str) -> str:
    """Get human-readable name for a source."""
    names = {
        "geoboundaries": "geoBoundaries",
        "osm": "OpenStreetMap",
        "grid3": "GRID3",
        "hdx": "HDX (OCHA COD)",
        "geopode": "GeoPoDe",
    }
    return names.get(source, source)


def stream_load_country(
    iso_code: str,
    levels: list[int],
    source: str,
    clear: bool = False,
):
    """
    Generator that yields progress events while loading boundaries for a single country.

    This is the primary loading function for the single-country UI workflow.
    It uses the CountrySourceRegistry to get configuration for URL-based sources.

    Event types:
    - "status": Progress message {"message": str}
    - "result": Final result {"total_loaded": int, ...}
    - "error": Error occurred {"error": str}

    Args:
        iso_code: ISO 3166-1 alpha-3 country code
        levels: List of admin levels to load
        source: Data source ("geoboundaries", "osm", "grid3", "hdx")
        clear: Whether to clear existing data first

    Yields:
        Tuples of (event_type, event_data)
    """
    EVENT_STATUS = "status"
    EVENT_RESULT = "result"
    EVENT_ERROR = "error"

    iso_code = iso_code.upper()
    source_name = get_source_display_name(source)

    try:
        yield EVENT_STATUS, {"message": f"Starting download from {source_name}..."}

        # Get registry and source config for URL-based sources
        registry = CountrySourceRegistry()
        source_config = registry.get_source_config(iso_code, source)

        # Get the loader
        loader = get_loader(source)
        is_url_based = isinstance(loader, URLBasedLoader)

        yield EVENT_STATUS, {"message": f"[{iso_code}] Processing {iso_code} from {source_name}..."}

        # Clear if requested
        if clear:
            deleted, _ = AdminBoundary.objects.filter(iso_code=iso_code, source=source).delete()
            if deleted:
                yield EVENT_STATUS, {"message": f"[{iso_code}] Cleared {deleted} existing entries"}

        result = {
            "iso_code": iso_code,
            "source": source,
            "total_loaded": 0,
            "cleared": 0,
            "success": False,
            "levels": [],
        }

        # Load each level
        for level in levels:
            yield EVENT_STATUS, {"message": f"[{iso_code}] ADM{level}: Fetching data..."}

            # For URL-based loaders, we need to get the level config from registry
            if is_url_based:
                if source_config:
                    level_config = source_config.get_level_config(level)
                    if level_config:
                        level_result = loader.load_boundary_level(
                            iso_code,
                            level,
                            level_config,
                            on_progress=lambda msg: None,
                        )
                    else:
                        level_result = LoadResult(
                            iso_code=iso_code,
                            level=level,
                            success=False,
                            error=f"ADM{level} not configured for {source} in {iso_code}",
                        )
                else:
                    level_result = LoadResult(
                        iso_code=iso_code,
                        level=level,
                        success=False,
                        error=f"{source} not configured for {iso_code}",
                    )
            else:
                # API-based loaders (geoBoundaries, OSM)
                level_result = loader.load_boundary_level(
                    iso_code,
                    level,
                    on_progress=lambda msg: None,
                )

            level_data = {
                "level": level_result.level,
                "success": level_result.success,
                "count": level_result.count,
                "message": level_result.message,
                "error": level_result.error,
            }
            result["levels"].append(level_data)

            if level_result.success:
                result["total_loaded"] += level_result.count
                yield EVENT_STATUS, {"message": f"[{iso_code}] {level_result.message}"}
            elif level_result.error:
                yield EVENT_STATUS, {"message": f"[{iso_code}] ADM{level}: {level_result.error}"}
            else:
                yield EVENT_STATUS, {"message": f"[{iso_code}] {level_result.message}"}

        result["success"] = result["total_loaded"] > 0

        yield EVENT_STATUS, {"message": f"[{iso_code}] Complete - loaded {result['total_loaded']} boundaries"}

        yield EVENT_STATUS, {"message": f"All done! Loaded {result['total_loaded']} boundaries from {source_name}"}

        yield EVENT_RESULT, {
            "success": True,
            "source": source,
            "total_loaded": result["total_loaded"],
            "result": result,
        }

    except Exception as e:
        logger.error(f"[stream_load_country] Error: {e}", exc_info=True)
        yield EVENT_ERROR, {"error": str(e)}


def stream_load_boundaries(
    iso_codes: list[str],
    levels: list[int],
    source: str,
    clear: bool = False,
):
    """
    Generator that yields progress events while loading boundaries.

    This is designed for SSE streaming - yields tuples of (event_type, data).
    For single-country loading, prefer stream_load_country() instead.

    Event types:
    - "status": Progress message {"message": str}
    - "result": Final result {"results": list, "total_loaded": int}
    - "error": Error occurred {"error": str}

    Usage:
        for event_type, data in stream_load_boundaries(["KEN"], [0,1,2], "geoboundaries"):
            if event_type == "status":
                print(data["message"])
            elif event_type == "result":
                print(f"Loaded {data['total_loaded']} boundaries")

    Args:
        iso_codes: List of ISO 3166-1 alpha-3 country codes
        levels: List of admin levels to load
        source: Data source ("geoboundaries", "osm", "grid3", "hdx")
        clear: Whether to clear existing data first

    Yields:
        Tuples of (event_type, event_data)
    """
    EVENT_STATUS = "status"
    EVENT_RESULT = "result"
    EVENT_ERROR = "error"

    try:
        source_name = get_source_display_name(source)
        registry = CountrySourceRegistry()
        loader = get_loader(source)
        is_url_based = isinstance(loader, URLBasedLoader)

        yield EVENT_STATUS, {"message": f"Starting download from {source_name}..."}

        results = []
        total_loaded = 0

        for iso_code in iso_codes:
            iso_code = iso_code.upper()
            yield EVENT_STATUS, {"message": f"[{iso_code}] Processing {iso_code} from {source_name}..."}

            # Get source config for URL-based sources
            source_config = registry.get_source_config(iso_code, source) if is_url_based else None

            # Clear if requested
            if clear:
                deleted, _ = AdminBoundary.objects.filter(iso_code=iso_code, source=source).delete()
                if deleted:
                    yield EVENT_STATUS, {"message": f"[{iso_code}] Cleared {deleted} existing entries"}

            country_result = {
                "iso_code": iso_code,
                "source": source,
                "total_loaded": 0,
                "cleared": 0,
                "success": False,
                "levels": [],
            }

            # Load each level
            for level in levels:
                yield EVENT_STATUS, {"message": f"[{iso_code}] ADM{level}: Fetching data..."}

                # For URL-based loaders, we need level config from registry
                if is_url_based:
                    if source_config:
                        level_config = source_config.get_level_config(level)
                        if level_config:
                            level_result = loader.load_boundary_level(
                                iso_code,
                                level,
                                level_config,
                                on_progress=lambda msg: None,
                            )
                        else:
                            level_result = LoadResult(
                                iso_code=iso_code,
                                level=level,
                                success=False,
                                error=f"ADM{level} not configured for {source}",
                            )
                    else:
                        level_result = LoadResult(
                            iso_code=iso_code,
                            level=level,
                            success=False,
                            error=f"{source} not configured for {iso_code}",
                        )
                else:
                    level_result = loader.load_boundary_level(
                        iso_code,
                        level,
                        on_progress=lambda msg: None,
                    )

                level_data = {
                    "level": level_result.level,
                    "success": level_result.success,
                    "count": level_result.count,
                    "message": level_result.message,
                    "error": level_result.error,
                }
                country_result["levels"].append(level_data)

                if level_result.success:
                    country_result["total_loaded"] += level_result.count
                    yield EVENT_STATUS, {"message": f"[{iso_code}] {level_result.message}"}
                elif level_result.error:
                    yield EVENT_STATUS, {"message": f"[{iso_code}] ADM{level}: {level_result.error}"}
                else:
                    yield EVENT_STATUS, {"message": f"[{iso_code}] {level_result.message}"}

            country_result["success"] = country_result["total_loaded"] > 0
            results.append(country_result)
            total_loaded += country_result["total_loaded"]

            yield EVENT_STATUS, {
                "message": f"[{iso_code}] Complete - loaded {country_result['total_loaded']} boundaries"
            }

        yield EVENT_STATUS, {"message": f"All done! Loaded {total_loaded} total boundaries from {source_name}"}

        yield EVENT_RESULT, {
            "success": True,
            "source": source,
            "total_loaded": total_loaded,
            "results": results,
        }

    except Exception as e:
        logger.error(f"[stream_load_boundaries] Error: {e}", exc_info=True)
        yield EVENT_ERROR, {"error": str(e)}


def stream_load_geopode(
    zip_file: UploadedFile | io.BytesIO,
    clear: bool = False,
):
    """
    Generator that yields progress events while loading GeoPoDe boundaries from a ZIP file.

    This is designed for SSE streaming - yields tuples of (event_type, data).

    Event types:
    - "status": Progress message {"message": str}
    - "result": Final result {"total_loaded": int, ...}
    - "error": Error occurred {"error": str}

    Args:
        zip_file: Uploaded ZIP file containing GeoPoDe GeoJSON files
        clear: Whether to clear existing GeoPoDe data first

    Yields:
        Tuples of (event_type, event_data)
    """
    EVENT_STATUS = "status"
    EVENT_RESULT = "result"
    EVENT_ERROR = "error"

    try:
        yield EVENT_STATUS, {"message": "Processing GeoPoDe ZIP file..."}

        loader = GeoPoDELoader()
        messages = []

        def on_progress(msg: str):
            messages.append(msg)

        result = loader.load_from_zip(zip_file, clear=clear, on_progress=on_progress)

        # Yield all progress messages
        for msg in messages:
            yield EVENT_STATUS, {"message": msg}

        if result.total_loaded > 0:
            yield EVENT_STATUS, {"message": f"Complete! Loaded {result.total_loaded} boundaries for {result.iso_code}"}
        else:
            # Check if there were any errors
            errors = [r.error for r in result.levels if r.error]
            if errors:
                yield EVENT_STATUS, {"message": f"Completed with errors: {errors[0]}"}

        yield EVENT_RESULT, {
            "success": result.success,
            "source": "geopode",
            "iso_code": result.iso_code,
            "total_loaded": result.total_loaded,
            "levels": [
                {
                    "level": r.level,
                    "success": r.success,
                    "count": r.count,
                    "message": r.message,
                    "error": r.error,
                }
                for r in result.levels
            ],
        }

    except Exception as e:
        logger.error(f"[stream_load_geopode] Error: {e}", exc_info=True)
        yield EVENT_ERROR, {"error": str(e)}


# Backwards compatibility alias
BoundaryLoader = GeoBoundariesLoader
