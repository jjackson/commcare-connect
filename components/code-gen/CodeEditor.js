import React, { useState, useEffect, useRef } from 'react';
import { Printer, RefreshCw, Terminal, Play, Layout } from 'lucide-react';

const ReportBuilder = () => {
  const [htmlCode, setHtmlCode] = useState(
    `<div class="p-6 bg-white rounded-lg border border-gray-200 shadow-sm">
  <div class="flex justify-between items-center mb-6">
    <div>
      <h1 class="text-2xl font-bold text-gray-800">FLW Performance Report</h1>
      <p class="text-sm text-gray-500">FLW-level analysis summary</p>
    </div>
    <span class="bg-blue-100 text-blue-800 text-xs font-medium px-2.5 py-0.5 rounded">LIVE DATA</span>
  </div>

  <div id="loading" class="text-center py-8 text-gray-500">
    <p>Loading FLW data...</p>
  </div>

  <div id="error" class="hidden text-center py-8 text-red-600">
    <p id="error-message"></p>
  </div>

  <div id="table-container" class="hidden">
    <div class="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden">
      <div class="px-6 py-4 border-b border-gray-200 bg-gray-50">
        <h2 class="text-xl font-semibold text-gray-900">
          FLW Analysis
          <span class="text-sm text-gray-600 font-normal" id="flw-count"></span>
        </h2>
      </div>
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">FLW Name</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Total Visits</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Approved</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Days Active</th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200" id="table-body">
          </tbody>
        </table>
      </div>
    </div>
    <div id="table-info" class="mt-4 text-sm text-gray-600 text-center"></div>
  </div>
</div>`,
  );

  const [jsCode, setJsCode] = useState(
    `// Fetch FLW analysis data from API
async function loadFLWData() {
  const loadingEl = document.getElementById('loading');
  const errorEl = document.getElementById('error');
  const errorMsgEl = document.getElementById('error-message');
  const tableContainer = document.getElementById('table-container');
  const tableBody = document.getElementById('table-body');
  const tableInfo = document.getElementById('table-info');
  const flwCount = document.getElementById('flw-count');

  try {
    console.log('Fetching FLW analysis data...');

    // Extract opportunity_id from parent page URL (injected by parent component)
    // Since iframe uses srcDoc, window.location is the blob URL, not the parent page
    // The parent component injects PARENT_URL_PARAMS and PARENT_OPPORTUNITY_ID
    let opportunityId = window.PARENT_OPPORTUNITY_ID;
    let urlParams = window.PARENT_URL_PARAMS;

    // Fallback: try to get from window.location if available (shouldn't work in iframe, but just in case)
    if (!opportunityId && window.location.search) {
      const localParams = new URLSearchParams(window.location.search);
      opportunityId = localParams.get('opportunity_id');
      urlParams = localParams;
    }

    if (!opportunityId) {
      throw new Error('No opportunity_id found. The CodeEditor must be accessed from a page with ?opportunity_id=123 in the URL.');
    }

    // Build API URL with opportunity_id and any other query params
    const apiParams = new URLSearchParams();
    apiParams.set('opportunity_id', opportunityId);

    // Preserve other query params from parent (like config, refresh, etc.)
    if (urlParams) {
      urlParams.forEach((value, key) => {
        if (key !== 'opportunity_id') {
          apiParams.set(key, value);
        }
      });
    }

    const apiUrl = '/labs/api/analysis/flw/?' + apiParams.toString();
    console.log('API URL:', apiUrl);

    const response = await fetch(apiUrl);

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(errorData.error || \`HTTP \${response.status}: \${response.statusText}\`);
    }

    const data = await response.json();
    console.log('Data received:', data);

    if (!data.rows || data.rows.length === 0) {
      throw new Error('No FLW data available');
    }

    // Hide loading, show table
    loadingEl.classList.add('hidden');
    errorEl.classList.add('hidden');
    tableContainer.classList.remove('hidden');

    // Clear existing table rows
    tableBody.innerHTML = '';

    // Extract FLW data and sort by total_visits (descending)
    const flws = data.rows
      .map(row => ({
        username: row.username || 'Unknown',
        flw_name: row.flw_name || row.username || 'Unknown',
        total_visits: row.total_visits || 0,
        approved_visits: row.approved_visits || 0,
        pending_visits: row.pending_visits || 0,
        days_active: row.days_active || 0,
        approval_rate: row.total_visits > 0 ? Math.round((row.approved_visits / row.total_visits) * 100) : 0,
      }))
      .sort((a, b) => b.total_visits - a.total_visits);

    console.log(\`Processing \${flws.length} FLWs\`);

    // Create table rows for each FLW
    flws.forEach((flw) => {
      const row = document.createElement('tr');
      row.className = 'hover:bg-gray-50';

      // FLW Name
      const nameCell = document.createElement('td');
      nameCell.className = 'px-4 py-3 text-sm';
      const nameDiv = document.createElement('div');
      nameDiv.className = 'font-medium text-gray-900';
      nameDiv.textContent = flw.flw_name;
      nameCell.appendChild(nameDiv);
      if (flw.flw_name !== flw.username) {
        const usernameDiv = document.createElement('div');
        usernameDiv.className = 'text-xs text-gray-500';
        usernameDiv.textContent = flw.username;
        nameCell.appendChild(usernameDiv);
      }
      row.appendChild(nameCell);

      // Total Visits
      const visitsCell = document.createElement('td');
      visitsCell.className = 'px-4 py-3 whitespace-nowrap text-sm text-gray-900';
      visitsCell.textContent = flw.total_visits;
      row.appendChild(visitsCell);

      // Approved (with percentage)
      const approvedCell = document.createElement('td');
      approvedCell.className = 'px-4 py-3 whitespace-nowrap text-sm text-gray-900';
      approvedCell.innerHTML = \`<span>\${flw.approval_rate}%</span> <span class="text-gray-500">(\${flw.approved_visits})</span>\`;
      row.appendChild(approvedCell);

      // Days Active
      const daysCell = document.createElement('td');
      daysCell.className = 'px-4 py-3 whitespace-nowrap text-sm text-gray-900';
      daysCell.textContent = flw.days_active;
      row.appendChild(daysCell);

      tableBody.appendChild(row);
    });

    // Update header count and info
    flwCount.textContent = \`(\${flws.length} FLWs)\`;
    const totalVisits = flws.reduce((sum, f) => sum + f.total_visits, 0);
    tableInfo.textContent = \`\${flws.length} FLWs • \${totalVisits} total visits • Opportunity: \${data.opportunity_name || data.opportunity_id || 'N/A'}\`;

    console.log(\`Table generated with \${flws.length} FLWs, \${totalVisits} total visits\`);

  } catch (error) {
    console.error('Error loading FLW data:', error);
    loadingEl.classList.add('hidden');
    tableContainer.classList.add('hidden');
    errorEl.classList.remove('hidden');
    errorMsgEl.textContent = \`Error: \${error.message}\`;
  }
}

// Load data when page loads
loadFLWData();`,
  );

  const [cssCode, setCssCode] = useState(
    `/* Since we injected Tailwind, we only need custom CSS
   for things Tailwind can't easily do.
*/
body {
  background-color: #f3f4f6; /* matches bg-gray-100 */
}

/* Custom scrollbar to match app feel */
::-webkit-scrollbar {
  width: 8px;
}
::-webkit-scrollbar-track {
  background: #f1f1f1;
}
::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}`,
  );

  const [logs, setLogs] = useState([]);
  const [srcDoc, setSrcDoc] = useState('');
  const iframeRef = useRef(null);

  // Function to build the HTML blob for the iframe
  const generatePreview = () => {
    setLogs([]); // Clear logs on run

    // Extract opportunity_id from parent page URL to inject into iframe
    const parentUrlParams = new URLSearchParams(window.location.search);
    const opportunityId = parentUrlParams.get('opportunity_id');

    // We inject a script to catch console logs and send them to the parent
    const logInterceptor = `
      <script>
        const originalLog = console.log;
        const originalError = console.error;

        function sendToParent(type, args) {
          try {
            window.parent.postMessage({
              type: 'CONSOLE_LOG',
              level: type,
              message: args.map(a => String(a)).join(' ')
            }, '*');
          } catch (e) {}
        }

        console.log = (...args) => {
          originalLog.apply(console, args);
          sendToParent('info', args);
        };

        console.error = (...args) => {
          originalError.apply(console, args);
          sendToParent('error', args);
        };

        window.onerror = function(message, source, lineno, colno, error) {
           sendToParent('error', [message]);
        };
      </script>
    `;

    // Inject parent page URL params into iframe's JavaScript context
    // This allows the iframe code to access opportunity_id from the parent page
    const urlParamsInjection = `
      <script>
        // Inject parent page URL params into iframe context
        // Since iframe uses srcDoc, window.location is the blob URL, not the parent
        // So we inject the parent's URL params here
        window.PARENT_URL_PARAMS = new URLSearchParams('${
          window.location.search
        }');
        ${
          opportunityId
            ? `window.PARENT_OPPORTUNITY_ID = '${opportunityId}';`
            : ''
        }
      </script>
    `;

    // HERE IS THE CHANGE: We inject the Tailwind CDN script
    // In a real app, you might link to your local '/styles/main.css' instead
    const stylesInjection = `
      <script src="https://cdn.tailwindcss.com"></script>
      <style>${cssCode}</style>
    `;

    const fullHtml = `
      <!DOCTYPE html>
      <html>
        <head>
          ${stylesInjection}
          ${logInterceptor}
          ${urlParamsInjection}
        </head>
        <body>
          ${htmlCode}
          <script>
            try {
              ${jsCode}
            } catch (err) {
              console.error(err.toString());
            }
          </script>
        </body>
      </html>
    `;

    setSrcDoc(fullHtml);
  };

  // Run initial preview
  useEffect(() => {
    generatePreview();
  }, []);

  // Listen for messages from the iframe (console logs)
  useEffect(() => {
    const handleMessage = (event) => {
      if (event.data && event.data.type === 'CONSOLE_LOG') {
        setLogs((prev) => [
          ...prev,
          { level: event.data.level, msg: event.data.message },
        ]);
      }
    };
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, []);

  // Handle Printing the Iframe
  const handlePrint = () => {
    if (iframeRef.current && iframeRef.current.contentWindow) {
      iframeRef.current.contentWindow.focus();
      iframeRef.current.contentWindow.print();
    }
  };

  return (
    <div className="flex h-screen bg-gray-100 flex-col font-sans">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 p-4 flex justify-between items-center shadow-sm">
        <div className="flex items-center gap-2">
          <Layout className="w-6 h-6 text-blue-600" />
          <h1 className="text-xl font-bold text-gray-800">
            Report Builder Playground
          </h1>
        </div>
        <div className="flex gap-2">
          <button
            onClick={generatePreview}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
          >
            <Play size={16} /> Run Code
          </button>
          <button
            onClick={handlePrint}
            className="flex items-center gap-2 px-4 py-2 bg-gray-800 text-white rounded hover:bg-gray-900 transition-colors"
          >
            <Printer size={16} /> Print Report
          </button>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Editors Column */}
        <div className="w-1/3 flex flex-col border-r border-gray-300 bg-gray-50">
          {/* HTML Editor */}
          <div className="flex-1 flex flex-col min-h-0 border-b border-gray-200">
            <div className="px-4 py-2 bg-gray-200 text-xs font-semibold text-gray-600 uppercase flex justify-between">
              <span>HTML Structure</span>
            </div>
            <textarea
              className="flex-1 p-4 font-mono text-sm resize-none focus:outline-none focus:ring-2 focus:ring-inset focus:ring-blue-500"
              value={htmlCode}
              onChange={(e) => setHtmlCode(e.target.value)}
              spellCheck="false"
            />
          </div>

          {/* CSS Editor */}
          <div className="flex-1 flex flex-col min-h-0 border-b border-gray-200">
            <div className="px-4 py-2 bg-gray-200 text-xs font-semibold text-gray-600 uppercase">
              <span>CSS Styles</span>
            </div>
            <textarea
              className="flex-1 p-4 font-mono text-sm resize-none focus:outline-none focus:ring-2 focus:ring-inset focus:ring-blue-500"
              value={cssCode}
              onChange={(e) => setCssCode(e.target.value)}
              spellCheck="false"
            />
          </div>

          {/* JS Editor */}
          <div className="flex-1 flex flex-col min-h-0">
            <div className="px-4 py-2 bg-gray-200 text-xs font-semibold text-gray-600 uppercase">
              <span>JavaScript Logic</span>
            </div>
            <textarea
              className="flex-1 p-4 font-mono text-sm resize-none focus:outline-none focus:ring-2 focus:ring-inset focus:ring-blue-500"
              value={jsCode}
              onChange={(e) => setJsCode(e.target.value)}
              spellCheck="false"
            />
          </div>
        </div>

        {/* Preview Column */}
        <div className="flex-1 flex flex-col bg-white">
          <div className="flex-1 relative bg-white">
            <div className="absolute top-0 left-0 right-0 px-4 py-2 bg-gray-100 border-b border-gray-200 text-xs font-semibold text-gray-600 uppercase flex justify-between items-center">
              <span>Report Preview</span>
              <span className="text-gray-400 text-[10px]">
                Trusted Iframe (Tailwind Injected)
              </span>
            </div>

            <iframe
              ref={iframeRef}
              title="Report Preview"
              srcDoc={srcDoc}
              className="w-full h-full pt-10 border-none"
              sandbox="allow-scripts allow-modals allow-same-origin"
              // Note: 'allow-same-origin' is included to allow trusted code
              // to share cookies/session with the parent app.
            />
          </div>

          {/* Console Output Panel */}
          <div className="h-32 bg-gray-900 border-t border-gray-700 flex flex-col">
            <div className="px-4 py-1 bg-gray-800 text-xs font-semibold text-gray-400 uppercase flex items-center gap-2">
              <Terminal size={12} /> Console Output
            </div>
            <div className="flex-1 p-2 font-mono text-xs overflow-auto text-gray-300">
              {logs.length === 0 ? (
                <span className="text-gray-600 italic">
                  Console is empty...
                </span>
              ) : (
                logs.map((log, i) => (
                  <div
                    key={i}
                    className={`mb-1 ${
                      log.level === 'error' ? 'text-red-400' : 'text-green-400'
                    }`}
                  >
                    <span className="opacity-50 mr-2">
                      [{new Date().toLocaleTimeString()}]
                    </span>
                    {log.msg}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ReportBuilder;
