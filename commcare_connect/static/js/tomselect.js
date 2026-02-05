import 'tom-select/dist/css/tom-select.min.css';
import '../css/tomselect-overrides.css';
import TomSelect from 'tom-select';

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-tomselect]').forEach((el) => {
    el.removeAttribute('class');
    let plugins = [];
    if (!el.hasAttribute('data-tomselect:no-remove-button')) {
      plugins.push('remove_button');
    }
    let settings = {
      plugins: plugins,
    };
    if (el.hasAttribute('data-tomselect:settings')) {
      let data = el.getAttribute('data-tomselect:settings');
      Object.assign(settings, JSON.parse(data));
    }
    new TomSelect(el, settings);
  });
});
