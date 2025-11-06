import 'tom-select/dist/css/tom-select.min.css';
import TomSelect from 'tom-select';

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-tomselect]').forEach((el) => {
    el.removeAttribute('class');
    let plugings = [];
    if (!el.hasAttribute('data-tomselect:no-remove-button')) {
      plugings.push('remove_button');
    }
    new TomSelect(el, {
      plugins: plugings,
    });
  });
});
