import React, { useState, useEffect, useRef } from 'react';
import { Printer, RefreshCw, Terminal, Play, Layout } from 'lucide-react';

const ReportBuilder = () => {
  const [htmlCode, setHtmlCode] = useState(
    `<div class="p-6 bg-white rounded-lg border border-gray-200 shadow-sm">
  <div class="flex justify-between items-center mb-6">
    <div>
      <h1 class="text-2xl font-bold text-gray-800">Q3 Performance Report</h1>
      <p class="text-sm text-gray-500">Generated dynamically via JS</p>
    </div>
    <span class="bg-blue-100 text-blue-800 text-xs font-medium px-2.5 py-0.5 rounded">CONFIDENTIAL</span>
  </div>

  <div id="chart-container" class="h-64 bg-gray-50 rounded flex items-end justify-around p-4 border border-dashed border-gray-300"></div>
</div>`,
  );

  const [jsCode, setJsCode] = useState(
    `// Simple data visualization
const data = [120, 250, 90, 400, 180, 320];
const container = document.getElementById('chart-container');

// Max value for scaling
const max = Math.max(...data);

data.forEach(value => {
  const bar = document.createElement('div');
  // We can now use Tailwind classes inside the JS-generated elements too!
  bar.className = 'w-12 bg-blue-500 hover:bg-blue-600 transition-all duration-300 rounded-t shadow-md relative group';

  // Calculate height percentage
  const heightParams = (value / max) * 100;
  bar.style.height = heightParams + '%';

  // Add tooltip
  bar.innerHTML = \`<div class="absolute -top-8 left-1/2 transform -translate-x-1/2 bg-gray-800 text-white text-xs py-1 px-2 rounded opacity-0 group-hover:opacity-100 transition-opacity">\${value}</div>\`;

  container.appendChild(bar);
});
console.log('Chart generated with ' + data.length + ' items');

// Example: Since we are now "Same Origin", we could do this:
// fetch('/api/user/profile').then(res => res.json()).then(console.log);`,
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
