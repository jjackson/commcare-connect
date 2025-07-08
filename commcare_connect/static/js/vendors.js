import './htmx';
import 'htmx.org/dist/ext/loading-states';

import flatpickr from 'flatpickr';
import monthSelectPlugin from 'flatpickr/dist/esm/plugins/monthSelect';
import 'flatpickr/dist/flatpickr.css';
import 'flatpickr/dist/plugins/monthSelect/style.css';
window.monthPickr = (id, flatPickrConfig = {}, monthPluginConfig = {}) =>
  flatpickr(id, {
    plugins: [new monthSelectPlugin({ ...monthPluginConfig })],
    ...flatPickrConfig,
  });

import Alpine from 'alpinejs';
import Tooltip from '@ryangjchandler/alpine-tooltip';
Alpine.plugin(Tooltip);
window.Alpine = Alpine;
window.Alpine.start();
import 'tippy.js/dist/tippy.css';
