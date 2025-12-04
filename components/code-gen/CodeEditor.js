import React, { useState, useEffect, useRef } from 'react';
import {
  Printer,
  RefreshCw,
  Terminal,
  Play,
  Layout,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';

const ReportBuilder = () => {
  const [editorExpanded, setEditorExpanded] = useState(true);
  const [jsCode, setJsCode] = useState(
    `// Example: Using the built-in useFLWData hook
function FLWTable() {
  // Use the pre-built hook - handles API calls automatically
  const { loading, error, data } = window.hooks.useFLWData();

  const flws = data?.flws || [];
  const summary = data?.summary;

  if (loading) {
    return <div className="text-center py-8 text-gray-500">Loading...</div>;
  }

  if (error) {
    return <div className="text-center py-8 text-red-600">Error: {error}</div>;
  }

  return (
    <div className="p-6 bg-white rounded-lg border border-gray-200 shadow-sm">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">FLW Performance Report</h1>
          <p className="text-sm text-gray-500">FLW-level analysis summary</p>
        </div>
        <span className="bg-blue-100 text-blue-800 text-xs font-medium px-2.5 py-0.5 rounded">LIVE DATA</span>
      </div>

      <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200 bg-gray-50">
          <h2 className="text-xl font-semibold text-gray-900">
            FLW Analysis ({flws.length} FLWs)
          </h2>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">FLW Name</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Total Visits</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Approved</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Days Active</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {flws.map((flw) => (
                <tr key={flw.username} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-sm">
                    <div className="font-medium text-gray-900">{flw.flw_name || flw.username}</div>
                    {flw.flw_name !== flw.username && (
                      <div className="text-xs text-gray-500">{flw.username}</div>
                    )}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900">{flw.total_visits}</td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900">
                    {flw.approval_rate}% <span className="text-gray-500">({flw.approved_visits})</span>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900">{flw.days_active || 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {summary && (
        <div className="mt-4 text-sm text-gray-600 text-center">
          {summary.total_flws} FLWs • {summary.total_visits} total visits • Opportunity: {summary.opportunity_name}
        </div>
      )}
    </div>
  );
}

// Render the React component
const root = ReactDOM.createRoot(document.getElementById('react-root'));
root.render(<FLWTable />);`,
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

    // Inject React, ReactDOM, and Babel Standalone for JSX support
    // Babel Standalone automatically transforms JSX when script type="text/babel" is used
    const reactInjection = `
      <script crossorigin src="https://unpkg.com/react@18/umd/react.development.js"></script>
      <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"></script>
      <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
    `;

    // Inject Tailwind CDN script
    const stylesInjection = `
      <script src="https://cdn.tailwindcss.com"></script>
    `;

    // Load library from separate static file
    // This keeps the library code separate and maintainable
    const libraryInjection = `
      <script src="/static/js/report-builder-library.js"></script>
    `;

    // Use type="text/babel" to enable automatic JSX transformation
    // This works for both regular JS and JSX - Babel only transforms if it detects JSX
    const fullHtml = `
      <!DOCTYPE html>
      <html>
        <head>
          ${reactInjection}
          ${stylesInjection}
          ${logInterceptor}
          ${urlParamsInjection}
          ${libraryInjection}
        </head>
        <body>
          <div id="react-root"></div>
          <script type="text/babel">
            // React and ReactDOM are available globally
            const { React, ReactDOM } = window;
            // Helper functions available via window.labsApi and window.hooks

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
          <h1 className="text-xl font-bold text-gray-800">Report Builder</h1>
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
        {/* JS Editor Column */}
        {editorExpanded && (
          <div className="w-1/3 flex flex-col border-r border-gray-300 bg-gray-50">
            <div className="px-4 py-2 bg-gray-200 text-xs font-semibold text-gray-600 uppercase flex justify-between items-center">
              <span>Code Editor</span>
              <button
                onClick={() => setEditorExpanded(false)}
                className="p-1 hover:bg-gray-300 rounded transition-colors"
                title="Collapse editor"
              >
                <ChevronLeft size={16} />
              </button>
            </div>
            <textarea
              className="flex-1 p-4 font-mono text-sm resize-none focus:outline-none focus:ring-2 focus:ring-inset focus:ring-blue-500"
              value={jsCode}
              onChange={(e) => setJsCode(e.target.value)}
              spellCheck="false"
            />
          </div>
        )}

        {/* Preview Column */}
        <div
          className={`flex flex-col bg-white ${
            editorExpanded ? 'flex-1' : 'w-full'
          } relative`}
        >
          {!editorExpanded && (
            <div className="absolute top-2 left-2 z-10">
              <button
                onClick={() => setEditorExpanded(true)}
                className="p-2 bg-white border border-gray-300 rounded shadow-sm hover:bg-gray-50 transition-colors flex items-center gap-2"
                title="Expand editor"
              >
                <ChevronRight size={16} />
                <span className="text-xs font-medium">Code</span>
              </button>
            </div>
          )}
          <div className="flex-1 relative bg-white">
            <div className="absolute top-0 left-0 right-0 px-4 py-2 bg-gray-100 border-b border-gray-200 text-xs font-semibold text-gray-600 uppercase">
              <span>Preview</span>
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
