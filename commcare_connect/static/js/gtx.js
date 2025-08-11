(() => {
  // === CONFIG ===
  const ALLOWED_TAG_TYPES = ['google'];
  const BLOCKED_TAG_TYPES = ['jsm', 'html', 'img', 'j', 'k'];

  // === INIT DATA LAYER ===
  window.dataLayer = window.dataLayer || [];

  const setAllowedTagTypes = () => {
    window.dataLayer.push({
      'gtm.allowlist': ALLOWED_TAG_TYPES,
      'gtm.blocklist': BLOCKED_TAG_TYPES,
    });
  };

  // Gather GTM variables into a dictionary
  const gatherVariables = (selector, existing = {}) => {
    document.querySelectorAll(selector).forEach((container) => {
      container.querySelectorAll(':scope > [data-name]').forEach((div) => {
        const name = div.getAttribute('data-name');
        const value = div.getAttribute('data-value');
        if (existing[name] !== undefined) {
          throw new Error(`Duplicate key in initial page data: ${name}`);
        }
        existing[name] = value;
      });
    });
    return existing;
  };

  const GTM_VARS = gatherVariables('.gtm-vars');
  const GTM_ID = GTM_VARS['gtm.apiID'];

  const addInitialVariable = () => {
    const email = GTM_VARS['gtm.userEmail'] ?? '';
    window.dataLayer.push({
      userEmail: email,
      isDimagi: email.endsWith('@dimagi.com'),
    });
  };

  const gtmSendEvent = (eventName, eventData = {}, callbackFn) => {
    const data = { event: eventName, ...eventData };
    window.dataLayer.push(data);
    if (typeof callbackFn === 'function') callbackFn();
  };

  const loadGTM = (id) => {
    const script = document.createElement('script');
    script.async = true;
    script.src = `https://www.googletagmanager.com/gtm.js?id=${id}`;
    document.head.appendChild(script);
  };

  // === INIT ===
  setAllowedTagTypes();
  addInitialVariable();
  loadGTM(GTM_ID);

  // === GLOBAL EXPOSURE ===
  window.gtmSendEvent = gtmSendEvent;
})();
