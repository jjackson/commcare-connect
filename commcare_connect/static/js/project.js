import '../sass/project.scss';
import * as bootstrap from 'bootstrap';
import mapboxgl from 'mapbox-gl';
import circle from '@turf/circle';

/* Project specific Javascript goes here. */

function refreshTooltips() {
  const tooltipTriggerList = document.querySelectorAll(
    '[data-bs-toggle="tooltip"]',
  );
  const tooltipList = [...tooltipTriggerList].map(
    (tooltipTriggerEl) => new bootstrap.Tooltip(tooltipTriggerEl),
  );
}
window.refreshTooltips = refreshTooltips;

window.mapboxgl = mapboxgl;
window.circle = circle;

/**
 * Add gps data accuracy circles on the visit markers on a mapbox map.
 * @param {mapboxgl.Map} map - Mapbox Map
 * @param {Array.<{lng: float, lat: float, precision: float}> visit_data - Visit location data for User
 */
function addAccuracyCircles(map, visit_data) {
  map.on('load', () => {
    const visit_accuracy_circles = [];
    visit_data.forEach((loc) => {
      visit_accuracy_circles.push(
        circle([loc.lng, loc.lat], loc.precision, { units: 'meters' }),
      );
    });
    map.addSource('visit_accuracy_circles', {
      type: 'geojson',
      data: {
        type: 'FeatureCollection',
        features: visit_accuracy_circles,
      },
    });

    map.addLayer({
      id: 'visit-accuracy-circles-layer',
      source: 'visit_accuracy_circles',
      type: 'fill',
      paint: {
        'fill-antialias': true,
        'fill-opacity': 0.3,
      },
    });

    map.addLayer({
      id: 'visit-accuracy-circle-outlines-layer',
      source: 'visit_accuracy_circles',
      type: 'line',
      paint: {
        'line-color': '#fcbf49',
        'line-width': 3,
        'line-opacity': 0.5,
      },
    });
  });
}

window.addAccuracyCircles = addAccuracyCircles;

function addCatchmentAreas(map, catchments) {
  map.on('load', () => {
    const ACTIVE_COLOR = '#3366ff';
    const INACTIVE_COLOR = '#ff4d4d';
    const CIRCLE_OPACITY = 0.3;
    const SQUARE_BOX_STYLE = 'width: 20px; height: 20px; opacity: 0.3;';

    const geojsonData = {
      type: 'FeatureCollection',
      features: catchments.map((catchment) => ({
        type: 'Feature',
        geometry: {
          type: 'Point',
          coordinates: [catchment.lng, catchment.lat],
        },
        properties: {
          name: catchment.name,
          active: catchment.active,
          radius: catchment.radius,
        },
      })),
    };

    map.addSource('catchments', {
      type: 'geojson',
      data: geojsonData,
    });

    map.addLayer({
      id: 'catchment-circles',
      type: 'circle',
      source: 'catchments',
      paint: {
        'circle-radius': ['/', ['get', 'radius'], 100],
        'circle-color': [
          'case',
          ['get', 'active'],
          ACTIVE_COLOR,
          INACTIVE_COLOR,
        ],
        'circle-opacity': CIRCLE_OPACITY,
      },
    });

    const legend = document.createElement('div');
    legend.className = 'card position-absolute bottom-0 end-0 m-3';

    const activeStyle = `${SQUARE_BOX_STYLE} background-color: ${ACTIVE_COLOR};`;
    const inactiveStyle = `${SQUARE_BOX_STYLE} background-color: ${INACTIVE_COLOR};`;

    legend.innerHTML = `
      <div class="card-body">
        <h6 class="card-title">Catchment Areas</h6>
        <div class="mb-2 d-flex align-items-center">
          <span class="d-inline-block me-2" style="${activeStyle}"></span>
          <span>Active</span>
        </div>
        <div class="d-flex align-items-center">
          <span class="d-inline-block me-2" style="${inactiveStyle}"></span>
          <span>Inactive</span>
        </div>
      </div>
    `;
    map.getContainer().appendChild(legend);
  });
}

window.addCatchmentAreas = addCatchmentAreas;
