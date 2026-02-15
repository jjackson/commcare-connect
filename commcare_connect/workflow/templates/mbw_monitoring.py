"""
MBW Monitoring Workflow Template.

Select FLWs for monitoring and launch the MBW Monitoring Dashboard.
FLW assessment (eligible_for_renewal/probation/suspended) happens in the dashboard.
"""

DEFINITION = {
    "name": "MBW Monitoring",
    "description": "Monitor frontline worker performance with GPS analysis, follow-up rates, and FLW assessment",
    "version": 1,
    "templateType": "mbw_monitoring",
    "statuses": [
        {"id": "in_progress", "label": "In Progress", "color": "blue"},
        {"id": "completed", "label": "Completed", "color": "green"},
    ],
    "config": {
        "showSummaryCards": False,
        "showFilters": False,
    },
    "pipeline_sources": [],
}

RENDER_CODE = """function WorkflowUI({ definition, instance, workers, pipelines, links, actions, onUpdateState }) {
    // --- State ---
    const [step, setStep] = React.useState(instance.state?.selected_flws ? 'launched' : 'select');
    const [selectedFlws, setSelectedFlws] = React.useState({});
    const [flwHistory, setFlwHistory] = React.useState({});
    const [historyLoading, setHistoryLoading] = React.useState(false);
    const [title, setTitle] = React.useState('');
    const [tag, setTag] = React.useState('');
    const [launching, setLaunching] = React.useState(false);

    // --- Fetch audit history on mount ---
    React.useEffect(() => {
        if (!instance.opportunity_id) return;
        setHistoryLoading(true);
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value
            || document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
        fetch('/custom_analysis/mbw_monitoring/api/opportunity-flws/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            body: JSON.stringify({ opportunities: [instance.opportunity_id] })
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                const historyMap = {};
                (data.flws || []).forEach(f => { historyMap[f.username] = f.history || {}; });
                setFlwHistory(historyMap);
            }
        })
        .catch(err => console.error('Failed to fetch FLW history:', err))
        .finally(() => setHistoryLoading(false));
    }, [instance.opportunity_id]);

    // --- Already launched: show summary + "Continue in Dashboard" ---
    if (step === 'launched') {
        const flwResults = instance.state?.flw_results || {};
        const selectedCount = (instance.state?.selected_flws || []).length;
        const assessedCount = Object.values(flwResults).filter(r => r.result).length;
        const pct = selectedCount > 0 ? Math.round((assessedCount / selectedCount) * 100) : 0;

        return (
            <div className="space-y-6">
                <div className="bg-white rounded-lg shadow-sm p-6">
                    <h2 className="text-xl font-bold text-gray-900">
                        {instance.state?.title || 'MBW Monitoring'}
                    </h2>
                    {instance.state?.tag && (
                        <span className="text-sm text-gray-500">Tag: {instance.state.tag}</span>
                    )}
                    <div className="mt-4 flex items-center gap-4">
                        <div className="flex-1 bg-gray-200 rounded-full h-3">
                            <div className="bg-indigo-600 h-3 rounded-full"
                                 style={{ width: pct + '%' }}></div>
                        </div>
                        <span className="text-sm font-medium text-gray-700">
                            {assessedCount} / {selectedCount} FLWs ({pct}%)
                        </span>
                    </div>
                    <div className="mt-4 flex gap-3">
                        <a href={'/custom_analysis/mbw_monitoring/?run_id=' + instance.id}
                           className="inline-flex items-center px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700">
                            <i className="fa-solid fa-chart-line mr-2"></i>
                            {instance.status === 'completed' ? 'Review in Dashboard' : 'Continue in Dashboard'}
                        </a>
                    </div>
                </div>
                {/* FLW result summary table */}
                <div className="bg-white rounded-lg shadow-sm overflow-hidden">
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">FLW</th>
                                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Result</th>
                                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Notes</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-200">
                            {(instance.state?.selected_flws || []).map(username => {
                                const r = flwResults[username];
                                const w = workers.find(w => w.username === username);
                                return (
                                    <tr key={username}>
                                        <td className="px-4 py-2 text-sm">{w?.name || username}</td>
                                        <td className="px-4 py-2 text-sm">
                                            {r?.result ? (
                                                <span className={
                                                    r.result === 'eligible_for_renewal' ? 'text-green-700 bg-green-50 px-2 py-0.5 rounded' :
                                                    r.result === 'probation' ? 'text-amber-700 bg-amber-50 px-2 py-0.5 rounded' :
                                                    'text-red-700 bg-red-50 px-2 py-0.5 rounded'
                                                }>{r.result.replace(/_/g, ' ')}</span>
                                            ) : <span className="text-gray-400">Pending</span>}
                                        </td>
                                        <td className="px-4 py-2 text-sm text-gray-500">{r?.notes || '-'}</td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            </div>
        );
    }

    // --- FLW Selection + Launch ---
    const toggleFlw = (username) => {
        setSelectedFlws(prev => ({ ...prev, [username]: !prev[username] }));
    };
    const toggleAll = () => {
        const allSelected = workers.length > 0 && workers.every(w => selectedFlws[w.username]);
        const updated = {};
        workers.forEach(w => { updated[w.username] = !allSelected; });
        setSelectedFlws(updated);
    };
    const selectedCount = Object.values(selectedFlws).filter(Boolean).length;

    const handleLaunch = async () => {
        const selected = Object.entries(selectedFlws).filter(([_, v]) => v).map(([k]) => k);
        if (selected.length === 0) return;
        setLaunching(true);
        await onUpdateState({
            selected_flws: selected,
            title: title || definition.name,
            tag: tag,
            flw_results: {},
            opportunity_name: '',
        });
        window.location.href = '/custom_analysis/mbw_monitoring/?run_id=' + instance.id;
    };

    return (
        <div className="space-y-6">
            {/* Step 1: Select FLWs */}
            <div className="bg-white rounded-lg shadow-sm p-6">
                <h2 className="text-xl font-bold">Select FLWs for Monitoring</h2>
                <p className="text-gray-600 mt-1">Choose which frontline workers to include in this monitoring session.</p>
                {/* Title + Tag inputs */}
                <div className="grid grid-cols-2 gap-4 mt-4">
                    <div>
                        <label className="text-sm font-medium text-gray-700">Session Title</label>
                        <input type="text" value={title} onChange={e => setTitle(e.target.value)}
                               placeholder="e.g., March 2025 Review"
                               className="mt-1 w-full border rounded-md px-3 py-2 text-sm" />
                    </div>
                    <div>
                        <label className="text-sm font-medium text-gray-700">Tag (optional)</label>
                        <input type="text" value={tag} onChange={e => setTag(e.target.value)}
                               placeholder="e.g., monthly-review"
                               className="mt-1 w-full border rounded-md px-3 py-2 text-sm" />
                    </div>
                </div>
            </div>

            {/* FLW list with checkboxes + audit history */}
            <div className="bg-white rounded-lg shadow-sm overflow-hidden">
                <div className="px-4 py-3 bg-gray-50 border-b flex items-center justify-between">
                    <label className="flex items-center gap-2 text-sm">
                        <input type="checkbox"
                               checked={workers.length > 0 && workers.every(w => selectedFlws[w.username])}
                               onChange={toggleAll} />
                        Select All ({workers.length})
                    </label>
                    <span className="text-sm text-gray-500">{selectedCount} selected</span>
                </div>
                {historyLoading && (
                    <div className="px-4 py-2 text-xs text-gray-400 bg-gray-50 border-b">
                        Loading audit history...
                    </div>
                )}
                <div className="max-h-96 overflow-y-auto divide-y">
                    {workers.map(w => {
                        const h = flwHistory[w.username] || {};
                        return (
                            <div key={w.username} className="px-4 py-3 flex items-center gap-3 hover:bg-gray-50">
                                <input type="checkbox" checked={!!selectedFlws[w.username]}
                                       onChange={() => toggleFlw(w.username)} />
                                <div className="flex-1 min-w-0">
                                    <div className="font-medium text-sm">{w.name || w.username}</div>
                                    <div className="text-xs text-gray-500">{w.username}</div>
                                </div>
                                {/* Audit history indicators */}
                                {h.audit_count > 0 && (
                                    <span className="text-xs text-gray-500">
                                        {h.audit_count} past audit(s)
                                        {h.last_audit_result && (
                                            <span className={
                                                h.last_audit_result === 'eligible_for_renewal' ? ' text-green-600' :
                                                h.last_audit_result === 'probation' ? ' text-amber-600' :
                                                h.last_audit_result === 'suspended' ? ' text-red-600' : ''
                                            }> ({h.last_audit_result.replace(/_/g, ' ')})</span>
                                        )}
                                    </span>
                                )}
                                {h.open_task_count > 0 && (
                                    <span className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded">
                                        {h.open_task_count} open task(s)
                                    </span>
                                )}
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* Launch button */}
            <div className="flex justify-end">
                <button onClick={handleLaunch} disabled={selectedCount === 0 || launching}
                        className="px-6 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:opacity-50">
                    {launching ? 'Launching...' : `Launch Dashboard (${selectedCount} FLWs)`}
                </button>
            </div>
        </div>
    );
}"""

# Template export - this is what the registry imports
TEMPLATE = {
    "key": "mbw_monitoring",
    "name": "MBW Monitoring",
    "description": "Monitor FLW performance with GPS analysis, follow-up rates, and assessments",
    "icon": "fa-chart-line",
    "color": "purple",
    "definition": DEFINITION,
    "render_code": RENDER_CODE,
    "pipeline_schema": None,  # MBW has its own data pipeline
}
