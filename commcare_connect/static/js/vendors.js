import '@popperjs/core';
import * as bootstrap from 'bootstrap';
import 'htmx.org';
import Alpine from 'alpinejs';

window.Alpine = Alpine;
Alpine.start();

function refreshTooltips() {
  const tooltipTriggerList = document.querySelectorAll(
    '[data-bs-toggle="tooltip"]',
  );
  const tooltipList = [...tooltipTriggerList].map(
    (tooltipTriggerEl) => new bootstrap.Tooltip(tooltipTriggerEl),
  );
}
window.refreshTooltips = refreshTooltips;

function copyText(event) {
  event.preventDefault();
  navigator.clipboard.writeText(event.target.dataset.copy);
}
window.copyText = copyText;
