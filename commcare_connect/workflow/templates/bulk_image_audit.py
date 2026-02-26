"""
Bulk Image Audit Workflow Template.

Multi-opportunity image review with per-FLW pass/fail summary.
Supports Scale Photo, ORS Photo, and MUAC Photo image types.
"""

DEFINITION = {
    "name": "Bulk Image Audit",
    "description": "Review photos across multiple opportunities with per-FLW pass/fail tracking",
    "version": 1,
    "templateType": "bulk_image_audit",
    "statuses": [
        {"id": "config", "label": "Configuring", "color": "gray"},
        {"id": "creating", "label": "Creating Review", "color": "blue"},
        {"id": "reviewing", "label": "In Review", "color": "yellow"},
        {"id": "completed", "label": "Completed", "color": "green"},
        {"id": "failed", "label": "Failed", "color": "red"},
    ],
    "config": {
        "showSummaryCards": True,
    },
    "pipeline_sources": [],
}

RENDER_CODE = """function WorkflowUI({ definition, instance, workers, pipelines, links, actions, onUpdateState }) {

    // ── Image type map ──────────────────────────────────────────────────────
    const IMAGE_TYPES = [
        {
            id: 'scale_photo',
            label: 'Scale Photo',
            path: 'anthropometric/upload_weight_image',
            icon: 'fa-weight-scale',
        },
        {
            id: 'ors_photo',
            label: 'ORS Photo',
            path: 'service_delivery/ors_group/ors_photo',
            icon: 'fa-droplet',
        },
        {
            id: 'muac_photo',
            label: 'MUAC Photo',
            path: 'service_delivery/muac_group/muac_display_1/muac_photo',
            icon: 'fa-ruler',
        },
    ];

    // ── Phase (drives which section renders) ────────────────────────────────
    const [phase, setPhase] = React.useState(instance.state?.phase || 'config');

    // ── CSRF helper ─────────────────────────────────────────────────────────
    function getCsrfToken() {
        return document.cookie.split('; ')
            .find(row => row.startsWith('csrftoken='))
            ?.split('=')[1] || '';
    }

    // ── Config state ────────────────────────────────────────────────────────
    const [selectedOpps, setSelectedOpps] = React.useState(
        instance.state?.config?.selected_opps || []
    );  // [{id, name}]
    const [searchQuery, setSearchQuery] = React.useState('');
    const [searchResults, setSearchResults] = React.useState([]);
    const [isSearching, setIsSearching] = React.useState(false);
    const [imageType, setImageType] = React.useState(
        instance.state?.config?.image_type || 'scale_photo'
    );
    const [auditMode, setAuditMode] = React.useState(
        instance.state?.config?.audit_mode || 'date_range'
    );
    const [startDate, setStartDate] = React.useState(
        instance.state?.config?.start_date || ''
    );
    const [endDate, setEndDate] = React.useState(
        instance.state?.config?.end_date || ''
    );
    const [datePreset, setDatePreset] = React.useState(
        instance.state?.config?.date_preset || 'last_week'
    );
    const [lastNCount, setLastNCount] = React.useState(
        instance.state?.config?.count_per_opp || 10
    );
    const [samplePct, setSamplePct] = React.useState(
        instance.state?.config?.sample_percentage ?? 100
    );
    const [threshold, setThreshold] = React.useState(
        instance.state?.config?.threshold ?? 80
    );

    // ── Opp search ───────────────────────────────────────────────────────────
    const searchTimeout = React.useRef(null);

    const handleOppSearch = (query) => {
        setSearchQuery(query);
        if (searchTimeout.current) clearTimeout(searchTimeout.current);
        if (!query.trim()) { setSearchResults([]); return; }

        searchTimeout.current = setTimeout(() => {
            setIsSearching(true);
            fetch('/audit/api/opportunities/search/?q=' + encodeURIComponent(query))
                .then(r => r.json())
                .then(data => {
                    setSearchResults(data.opportunities || []);
                    setIsSearching(false);
                })
                .catch(() => setIsSearching(false));
        }, 300);
    };

    const addOpp = (opp) => {
        if (!selectedOpps.find(o => o.id === opp.id)) {
            setSelectedOpps(prev => [...prev, { id: opp.id, name: opp.name }]);
        }
        setSearchQuery('');
        setSearchResults([]);
    };

    const removeOpp = (id) => {
        setSelectedOpps(prev => prev.filter(o => o.id !== id));
    };

    // ── Date helpers (copied from audit_with_ai_review.py) ──────────────────
    const calculateDateRange = (preset) => {
        const today = new Date(); today.setHours(0,0,0,0);
        let start, end;
        switch (preset) {
            case 'last_week': {
                const dow = today.getDay();
                const daysToMon = dow === 0 ? 6 : dow - 1;
                const thisMon = new Date(today); thisMon.setDate(today.getDate() - daysToMon);
                start = new Date(thisMon); start.setDate(thisMon.getDate() - 7);
                end = new Date(start); end.setDate(start.getDate() + 6);
                break;
            }
            case 'last_7_days':
                end = new Date(today); end.setDate(today.getDate() - 1);
                start = new Date(end); start.setDate(end.getDate() - 6); break;
            case 'last_14_days':
                end = new Date(today); end.setDate(today.getDate() - 1);
                start = new Date(end); start.setDate(end.getDate() - 13); break;
            case 'last_30_days':
                end = new Date(today); end.setDate(today.getDate() - 1);
                start = new Date(end); start.setDate(end.getDate() - 29); break;
            case 'this_month':
                start = new Date(today.getFullYear(), today.getMonth(), 1);
                end = new Date(today); end.setDate(today.getDate() - 1); break;
            case 'last_month':
                start = new Date(today.getFullYear(), today.getMonth() - 1, 1);
                end = new Date(today.getFullYear(), today.getMonth(), 0); break;
            default: return null;
        }
        return { start: start.toISOString().split('T')[0], end: end.toISOString().split('T')[0] };
    };

    const applyPreset = (preset) => {
        setDatePreset(preset);
        if (preset !== 'custom') {
            const range = calculateDateRange(preset);
            if (range) { setStartDate(range.start); setEndDate(range.end); }
        }
    };

    // Set default date range on mount
    React.useEffect(() => {
        if (!startDate && !endDate) applyPreset('last_week');
    }, []);

    // ── Execution state ──────────────────────────────────────────────────────
    const [isRunning, setIsRunning] = React.useState(false);
    const [isCancelling, setIsCancelling] = React.useState(false);
    const [progress, setProgress] = React.useState(null);
    const [taskId, setTaskId] = React.useState(null);
    const [sessionId, setSessionId] = React.useState(instance.state?.session_id || null);
    const cleanupRef = React.useRef(null);

    // Cleanup SSE on unmount
    React.useEffect(() => {
        return () => { if (cleanupRef.current) cleanupRef.current(); };
    }, []);

    // Reconnect to running job on page load (if user refreshed mid-creation)
    React.useEffect(() => {
        try {
            const activeJob = instance.state?.active_job;
            if (!actions?.streamAuditProgress) return;
            if (activeJob?.status === 'running' && activeJob?.job_id) {
                setIsRunning(true);
                setTaskId(activeJob.job_id);
                setProgress({
                    status: 'running',
                    stage_name: activeJob.stage_name || 'Processing',
                    processed: activeJob.processed || 0,
                    total: activeJob.total || 0,
                });
                const cleanup = actions.streamAuditProgress(
                    activeJob.job_id,
                    (p) => setProgress(p),
                    async (final) => {
                        setIsRunning(false);
                        setProgress({ status: 'completed', ...final });
                        // Try to find session_id from completion payload
                        let sid = final?.session_id || final?.sessions?.[0]?.id;
                        if (!sid) {
                            // Fallback: fetch from workflow sessions API
                            try {
                                const r = await fetch('/audit/api/workflow/' + instance.id + '/sessions/');
                                const d = await r.json();
                                sid = d.sessions?.[0]?.id;
                            } catch (e) { /* ignore */ }
                        }
                        if (sid) {
                            setSessionId(sid);
                            setPhase('reviewing');
                            onUpdateState({
                                phase: 'reviewing',
                                session_id: sid,
                                active_job: {
                                    job_id: activeJob.job_id,
                                    status: 'completed',
                                    completed_at: new Date().toISOString(),
                                },
                            }).catch(() => {});
                        } else {
                            setPhase('config');
                            onUpdateState({ phase: 'config' }).catch(() => {});
                        }
                    },
                    (err) => {
                        setIsRunning(false);
                        setProgress({ status: 'failed', error: err });
                        onUpdateState({
                            active_job: { job_id: activeJob.job_id, status: 'failed', error: err },
                        }).catch(() => {});
                    }
                );
                cleanupRef.current = cleanup;
                return () => { if (cleanup) cleanup(); };
            }
        } catch (err) {
            console.error('[BulkImageAudit] Reconnect error:', err);
        }
    }, []); // Run once on mount

    // ── Create handler ───────────────────────────────────────────────────────
    const handleCreate = async () => {
        if (selectedOpps.length === 0) return;

        const imageTypeObj = IMAGE_TYPES.find(t => t.id === imageType);
        if (!imageTypeObj) {
            setIsRunning(false);
            setProgress({ status: 'failed', error: 'Unknown image type: ' + imageType });
            setPhase('config');
            return;
        }
        const config = {
            selected_opps: selectedOpps,
            image_type: imageType,
            image_path: imageTypeObj.path,
            audit_mode: auditMode,
            start_date: auditMode === 'date_range' ? startDate : null,
            end_date: auditMode === 'date_range' ? endDate : null,
            count_per_opp: auditMode === 'last_n_per_opp' ? lastNCount : null,
            sample_percentage: samplePct,
            threshold: threshold,
            date_preset: datePreset,
        };

        setIsRunning(true);
        setProgress({ status: 'starting', message: 'Initializing...' });
        setPhase('creating');

        await onUpdateState({ phase: 'creating', config });

        const criteria = {
            audit_type: auditMode,
            start_date: auditMode === 'date_range' ? startDate : null,
            end_date: auditMode === 'date_range' ? endDate : null,
            count_per_opp: auditMode === 'last_n_per_opp' ? lastNCount : null,
            sample_percentage: samplePct,
            related_fields: [{ image_path: imageTypeObj.path, filter_by_image: true }],
        };

        try {
            const result = await actions.createAudit({
                opportunities: selectedOpps,
                criteria,
                workflow_run_id: instance.id,
            });

            if (result.success && result.task_id) {
                setTaskId(result.task_id);
                onUpdateState({
                    active_job: {
                        job_id: result.task_id,
                        status: 'running',
                        started_at: new Date().toISOString(),
                    },
                }).catch(() => {});

                const cleanup = actions.streamAuditProgress(
                    result.task_id,
                    (p) => setProgress(p),
                    async (final) => {
                        setIsRunning(false);
                        setProgress({ status: 'completed', ...final });
                        // Try to find session_id from completion payload
                        let sid = final?.session_id || final?.sessions?.[0]?.id;
                        if (!sid) {
                            // Fallback: fetch from workflow sessions API
                            try {
                                const r = await fetch('/audit/api/workflow/' + instance.id + '/sessions/');
                                const d = await r.json();
                                sid = d.sessions?.[0]?.id;
                            } catch (e) { /* ignore */ }
                        }
                        if (sid) {
                            setSessionId(sid);
                            setPhase('reviewing');
                            onUpdateState({
                                phase: 'reviewing',
                                session_id: sid,
                                active_job: {
                                    job_id: result.task_id,
                                    status: 'completed',
                                    completed_at: new Date().toISOString(),
                                },
                            }).catch(() => {});
                        } else {
                            setPhase('config');
                            onUpdateState({ phase: 'config' }).catch(() => {});
                        }
                    },
                    (err) => {
                        setIsRunning(false);
                        setProgress({ status: 'failed', error: err });
                        setPhase('config');
                        onUpdateState({
                            phase: 'config',
                            active_job: { job_id: result.task_id, status: 'failed', error: err },
                        }).catch(() => {});
                    }
                );
                cleanupRef.current = cleanup;
            } else {
                setIsRunning(false);
                setProgress({ status: 'failed', error: result.error || 'Failed to start' });
                setPhase('config');
                onUpdateState({ phase: 'config' }).catch(() => {});
            }
        } catch (err) {
            setIsRunning(false);
            setProgress({ status: 'failed', error: err.message });
            setPhase('config');
            onUpdateState({ phase: 'config' }).catch(() => {});
        }
    };

    // ── Cancel handler ───────────────────────────────────────────────────────
    const handleCancel = async () => {
        if (!taskId || isCancelling) return;
        setIsCancelling(true);
        if (cleanupRef.current) { cleanupRef.current(); cleanupRef.current = null; }
        setIsRunning(false);
        try {
            await actions.cancelAudit(taskId);
        } catch (e) { /* ignore */ }
        setProgress({ status: 'cancelled', message: 'Audit creation cancelled' });
        setPhase('config');
        try {
            await onUpdateState({ phase: 'config' });
        } finally {
            setIsCancelling(false);
        }
    };

    // ── Inner component: Visit Selection ────────────────────────────────────
    const VisitSelectionSection = () => (
        <div>
            <h3 className="text-sm font-medium text-gray-700 mb-3">
                <i className="fa-solid fa-sliders mr-2 text-gray-400"></i>
                Visit Selection
            </h3>
            <div className="flex gap-2 mb-4">
                <button onClick={() => setAuditMode('date_range')}
                    className={
                        'flex-1 px-4 py-3 text-sm rounded-lg border-2 transition-colors ' +
                        (auditMode === 'date_range'
                            ? 'bg-blue-50 text-blue-700 border-blue-500'
                            : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300')
                    }>
                    <i className="fa-solid fa-calendar mr-2"></i>Date Range
                </button>
                <button onClick={() => setAuditMode('last_n_per_opp')}
                    className={
                        'flex-1 px-4 py-3 text-sm rounded-lg border-2 transition-colors ' +
                        (auditMode === 'last_n_per_opp'
                            ? 'bg-blue-50 text-blue-700 border-blue-500'
                            : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300')
                    }>
                    <i className="fa-solid fa-list-ol mr-2"></i>Last N Visits
                </button>
            </div>
            {auditMode === 'date_range' && (
                <div className="p-4 bg-gray-50 rounded-lg border border-gray-200">
                    <div className="flex flex-wrap gap-2 mb-3">
                        {[
                            { id: 'last_week', label: 'Last Week' },
                            { id: 'last_7_days', label: 'Last 7 Days' },
                            { id: 'last_14_days', label: 'Last 14 Days' },
                            { id: 'last_30_days', label: 'Last 30 Days' },
                            { id: 'this_month', label: 'This Month' },
                            { id: 'last_month', label: 'Last Month' },
                            { id: 'custom', label: 'Custom' },
                        ].map(p => (
                            <button key={p.id} onClick={() => applyPreset(p.id)}
                                className={
                                    'px-3 py-1.5 text-sm rounded-full border transition-colors ' +
                                    (datePreset === p.id
                                        ? 'bg-blue-600 text-white border-blue-600'
                                        : 'bg-white text-gray-700 border-gray-300 hover:border-blue-400')
                                }>
                                {p.label}
                            </button>
                        ))}
                    </div>
                    <div className="flex gap-4 items-center">
                        <div>
                            <label className="block text-xs text-gray-500 mb-1">Start</label>
                            <input type="date" value={startDate}
                                onChange={e => { setStartDate(e.target.value); setDatePreset('custom'); }}
                                className="border border-gray-300 rounded px-3 py-2 text-sm" />
                        </div>
                        <div>
                            <label className="block text-xs text-gray-500 mb-1">End</label>
                            <input type="date" value={endDate}
                                onChange={e => { setEndDate(e.target.value); setDatePreset('custom'); }}
                                className="border border-gray-300 rounded px-3 py-2 text-sm" />
                        </div>
                    </div>
                </div>
            )}
            {auditMode === 'last_n_per_opp' && (
                <div className="p-4 bg-gray-50 rounded-lg border border-gray-200">
                    <div className="flex items-center gap-3">
                        <label className="text-sm text-gray-700">Get the last</label>
                        <input type="number" min="1" max="1000" value={lastNCount}
                            onChange={e => setLastNCount(parseInt(e.target.value) || 10)}
                            className="w-20 border border-gray-300 rounded px-3 py-2 text-sm text-center" />
                        <label className="text-sm text-gray-700">visits per opportunity</label>
                    </div>
                </div>
            )}
        </div>
    );

    // ── Inner component: Config ──────────────────────────────────────────────
    const ConfigPhase = () => (
        <div className="bg-white rounded-lg shadow-sm p-6 space-y-6">

            {/* Opportunity selector */}
            <div>
                <h3 className="text-sm font-medium text-gray-700 mb-3">
                    <i className="fa-solid fa-building mr-2 text-gray-400"></i>
                    Opportunities
                </h3>
                <div className="relative">
                    <input
                        type="text"
                        value={searchQuery}
                        onChange={e => handleOppSearch(e.target.value)}
                        placeholder="Search opportunities..."
                        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                    />
                    {isSearching && (
                        <div className="absolute right-3 top-2.5">
                            <i className="fa-solid fa-spinner fa-spin text-gray-400"></i>
                        </div>
                    )}
                    {searchResults.length > 0 && (
                        <div className={'absolute z-10 w-full bg-white border border-gray-200 ' +
                            'rounded-lg shadow-lg mt-1 max-h-48 overflow-y-auto'}>
                            {searchResults.map(opp => (
                                <button
                                    key={opp.id}
                                    onClick={() => addOpp(opp)}
                                    className={'w-full text-left px-4 py-2 text-sm hover:bg-blue-50 ' +
                                        'flex items-center justify-between'}
                                >
                                    <span className="font-medium text-gray-900">{opp.name}</span>
                                    <span className="text-xs text-gray-400 ml-2">ID {opp.id}</span>
                                </button>
                            ))}
                        </div>
                    )}
                </div>
                {selectedOpps.length > 0 && (
                    <div className="flex flex-wrap gap-2 mt-3">
                        {selectedOpps.map(opp => (
                            <span key={opp.id}
                                className={'inline-flex items-center gap-1.5 px-3 py-1 bg-blue-100 ' +
                                    'text-blue-800 rounded-full text-sm font-medium'}>
                                {opp.name}
                                <button onClick={() => removeOpp(opp.id)}
                                    className="text-blue-500 hover:text-blue-800 ml-1">
                                    <i className="fa-solid fa-times text-xs"></i>
                                </button>
                            </span>
                        ))}
                    </div>
                )}
            </div>

            {/* Image type */}
            <div>
                <h3 className="text-sm font-medium text-gray-700 mb-3">
                    <i className="fa-solid fa-image mr-2 text-gray-400"></i>
                    Image Type
                </h3>
                <div className="flex gap-2">
                    {IMAGE_TYPES.map(t => (
                        <button key={t.id} onClick={() => setImageType(t.id)}
                            className={
                                'flex-1 px-4 py-3 text-sm rounded-lg border-2 transition-colors ' +
                                (imageType === t.id
                                    ? 'bg-blue-50 text-blue-700 border-blue-500'
                                    : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300')
                            }>
                            <i className={'fa-solid ' + t.icon + ' mr-2'}></i>
                            {t.label}
                        </button>
                    ))}
                </div>
            </div>

            {/* Visit Selection */}
            <VisitSelectionSection />

            {/* Sampling */}
            <div>
                <h3 className="text-sm font-medium text-gray-700 mb-3">
                    <i className="fa-solid fa-percent mr-2 text-gray-400"></i>
                    Sampling
                </h3>
                <div className="p-4 bg-gray-50 rounded-lg border border-gray-200 flex items-center gap-3">
                    <label className="text-sm text-gray-700">Sample</label>
                    <input type="number" min="1" max="100" value={samplePct}
                        onChange={e => setSamplePct(parseInt(e.target.value) || 100)}
                        className="w-20 border border-gray-300 rounded px-3 py-2 text-sm text-center" />
                    <label className="text-sm text-gray-700">% of matching visits</label>
                </div>
            </div>

            {/* Passing threshold */}
            <div>
                <h3 className="text-sm font-medium text-gray-700 mb-3">
                    <i className="fa-solid fa-gauge mr-2 text-gray-400"></i>
                    Passing Threshold
                </h3>
                <div className="p-4 bg-gray-50 rounded-lg border border-gray-200 flex items-center gap-3">
                    <label className="text-sm text-gray-700">Mark FLW as passing if</label>
                    <input type="number" min="1" max="100" value={threshold}
                        onChange={e => setThreshold(parseInt(e.target.value) || 80)}
                        className="w-20 border border-gray-300 rounded px-3 py-2 text-sm text-center" />
                    <label className="text-sm text-gray-700">% or more of their photos pass</label>
                </div>
            </div>

            {/* Submit */}
            <div className="pt-4 border-t border-gray-200">
                <button
                    onClick={handleCreate}
                    disabled={selectedOpps.length === 0}
                    className={'inline-flex items-center px-6 py-3 bg-blue-600 text-white ' +
                        'rounded-lg hover:bg-blue-700 disabled:bg-gray-400 font-medium'}
                >
                    <i className="fa-solid fa-play mr-2"></i>
                    Create Review
                </button>
                {selectedOpps.length === 0 && (
                    <p className="mt-2 text-sm text-red-600">
                        Select at least one opportunity to continue.
                    </p>
                )}
            </div>
        </div>
    );

    // ── Inner component: Creating ────────────────────────────────────────────
    const CreatingPhase = () => (
        <div className="space-y-4">
            {isRunning && progress && (
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                    <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-3">
                            <i className="fa-solid fa-spinner fa-spin text-blue-600"></i>
                            <span className="font-medium text-blue-800">
                                {progress.stage_name || 'Processing...'}
                            </span>
                        </div>
                        <div className="flex items-center gap-3">
                            {progress.current_stage && progress.total_stages && (
                                <span className="text-sm text-blue-600">
                                    Stage {progress.current_stage}/{progress.total_stages}
                                </span>
                            )}
                            <button onClick={handleCancel} disabled={isCancelling}
                                className={'px-3 py-1 text-sm text-red-600 hover:text-red-800 ' +
                                    'hover:bg-red-100 rounded transition-colors disabled:opacity-50'}>
                                <i className="fa-solid fa-times mr-1"></i>Cancel
                            </button>
                        </div>
                    </div>
                    {progress.total > 0 && (
                        <div className="w-full bg-blue-200 rounded-full h-2">
                            <div className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                                style={{ width: (progress.processed / progress.total * 100) + '%' }}>
                            </div>
                        </div>
                    )}
                    <div className="mt-2 text-sm text-blue-700">{progress.message}</div>
                </div>
            )}
            {progress?.status === 'failed' && !isRunning && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                    <div className="flex items-center gap-2 text-red-800">
                        <i className="fa-solid fa-circle-exclamation"></i>
                        <span className="font-medium">Error: {progress.error}</span>
                    </div>
                    <button onClick={() => setPhase('config')}
                        className="mt-3 text-sm text-blue-600 hover:underline">
                        ← Back to configuration
                    </button>
                </div>
            )}
            {progress?.status === 'cancelled' && !isRunning && (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
                    <div className="flex items-center gap-2 text-amber-800">
                        <i className="fa-solid fa-ban"></i>
                        <span className="font-medium">Audit creation was cancelled</span>
                    </div>
                    <button onClick={() => setPhase('config')}
                        className="mt-3 text-sm text-blue-600 hover:underline">
                        ← Back to configuration
                    </button>
                </div>
            )}
        </div>
    );
    // ── Placeholder inner components (to be replaced in later tasks) ─────────
    const ReviewPhase = () => <div className="bg-white rounded-lg shadow-sm p-6 text-gray-500">Review phase coming soon...</div>;
    const CompletedPhase = () => <div className="bg-white rounded-lg shadow-sm p-6 text-gray-500">Completed.</div>;

    // ── Phase router ────────────────────────────────────────────────────────
    return (
        <div className="space-y-6">
            <div className="bg-white rounded-lg shadow-sm p-6">
                <h1 className="text-2xl font-bold text-gray-900">{definition.name}</h1>
                <p className="text-gray-600 mt-1">{definition.description}</p>
            </div>
            {phase === 'config' && <ConfigPhase />}
            {phase === 'creating' && <CreatingPhase />}
            {phase === 'reviewing' && <ReviewPhase />}
            {phase === 'completed' && <CompletedPhase />}
        </div>
    );
}"""

TEMPLATE = {
    "key": "bulk_image_audit",
    "name": "Bulk Image Audit",
    "description": "Review photos across multiple opportunities with per-FLW pass/fail tracking",
    "icon": "fa-images",
    "color": "blue",
    "definition": DEFINITION,
    "render_code": RENDER_CODE,
    "pipeline_schema": None,
}
