import '@popperjs/core';
import Alpine from 'alpinejs';
import './htmx';
import 'htmx.org/dist/ext/loading-states';
import mapboxgl from 'mapbox-gl';

window.Alpine = Alpine;
Alpine.start();

window.mapboxgl = mapboxgl;
