import '@popperjs/core';
import 'bootstrap';
import Alpine from 'alpinejs';
import './htmx';
import 'htmx.org/dist/ext/loading-states';
import mapboxgl from 'mapbox-gl';

window.Alpine = Alpine;
Alpine.start();

mapboxgl.accessToken = '<your token here>';
window.mapboxgl = mapboxgl;
