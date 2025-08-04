/**
 * Centralized registry for custom Alpine.js components used across the project.
 *
 * All components are initialized within the `alpine:init` event to ensure
 * they are registered before Alpine processes the DOM. This prevents
 * reference errors and ensures reliable initialization of dynamic UI elements.
 */

document.addEventListener('alpine:init', () => {
  // used in user_visit_verification_table.html
  Alpine.data('visitVerification', (initialTab, defaultPage) => ({
    activeTab: initialTab,
    page: defaultPage,
    selected: [],
    showApproveModal: false,
    showRejectModal: false,

    updateUrlAndRequest() {
      const url = new URL(window.location);
      const formData = new FormData(this.$refs.visitForm);
      const params = new URLSearchParams();

      for (let [key, value] of formData.entries()) {
        if (value && String(value).trim() !== '') {
          params.set(key, value);
        }
      }

      url.search = params.toString();
      window.history.pushState({}, '', url.toString());
      this.$dispatch('reload_table');
    },
  }));

  Alpine.data('visitVerificationTable', () => ({
    selectedRow: null,
    selectAll: false,
    toggleSelectAll() {
      this.selectAll = !this.selectAll;
      if (this.selectAll) {
        this.selected = Array.from(
          document.querySelectorAll('input[type=checkbox][x-model=selected]'),
        ).map((cb) => cb.value);
      } else {
        this.selected = [];
      }
    },
    updateSelectAll() {
      const checkboxes = document.querySelectorAll(
        'input[type=checkbox][x-model=selected]',
      );
      this.selectAll =
        checkboxes.length > 0 && this.selected.length === checkboxes.length;
    },
  }));
});
