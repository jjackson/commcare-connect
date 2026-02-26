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

    // ── Review state ─────────────────────────────────────────────────────────
    const [assessments, setAssessments] = React.useState([]);
    const [loadingReview, setLoadingReview] = React.useState(false);
    const [reviewError, setReviewError] = React.useState(null);
    const [isSaving, setIsSaving] = React.useState(false);
    const [aiRunning, setAiRunning] = React.useState({});  // {blob_id: true/false}

    // Load assessment data when entering review phase
    React.useEffect(() => {
        if (phase !== 'reviewing' || !sessionId) return;
        setLoadingReview(true);
        setReviewError(null);
        fetch('/audit/api/' + sessionId + '/bulk-data/')
            .then(r => r.json())
            .then(data => {
                setAssessments(data.assessments || []);
                setLoadingReview(false);
            })
            .catch(err => {
                setReviewError(err.message);
                setLoadingReview(false);
            });
    }, [phase, sessionId]);

    // Update a single assessment field locally
    const updateAssessment = (id, patch) => {
        setAssessments(prev => prev.map(a => a.id === id ? { ...a, ...patch } : a));
    };

    // Build visit_results structure expected by backend
    const buildVisitResults = (asmnts) => {
        const vr = {};
        for (const a of asmnts) {
            const vid = String(a.visit_id);
            if (!vr[vid]) vr[vid] = { assessments: {} };
            vr[vid].assessments[a.blob_id] = {
                question_id: a.question_id,
                result: a.result || '',
                notes: a.notes || '',
                ai_result: a.ai_result || '',
                ai_notes: a.ai_notes || '',
            };
        }
        return vr;
    };

    // Save progress to backend
    const saveProgress = async (updatedAssessments) => {
        if (!sessionId) return;
        const asmnts = updatedAssessments || assessments;
        const visitResults = buildVisitResults(asmnts);
        const fd = new FormData();
        fd.append('visit_results', JSON.stringify(visitResults));
        setIsSaving(true);
        try {
            await fetch('/audit/api/' + sessionId + '/save/', {
                method: 'POST',
                headers: { 'X-CSRFToken': getCsrfToken() },
                body: fd,
            });
        } finally {
            setIsSaving(false);
        }
    };

    // Handle pass/fail button click — update locally and save
    const handleAssessResult = async (id, result) => {
        const updated = assessments.map(a =>
            a.id === id ? { ...a, result, status: result } : a
        );
        setAssessments(updated);
        await saveProgress(updated);
    };

    // Handle notes change — debounced save
    const notesTimeout = React.useRef(null);
    const handleNotesChange = (id, notes) => {
        updateAssessment(id, { notes });
        if (notesTimeout.current) clearTimeout(notesTimeout.current);
        notesTimeout.current = setTimeout(() => saveProgress(), 800);
    };

    // ── FLW summary helper ───────────────────────────────────────────────────
    const buildFlwRows = (asmnts, config) => {
        const byUser = {};
        for (const a of asmnts) {
            if (!byUser[a.username]) {
                byUser[a.username] = {
                    flw_name: a.username,
                    opp_name: (config?.selected_opps || []).find(o => String(o.id) === String(a.opportunity_id))?.name
                        || (config?.selected_opps || [])[0]?.name || '—',
                    passed: 0,
                    total: 0,
                };
            }
            byUser[a.username].total += 1;
            if (a.status === 'pass') byUser[a.username].passed += 1;
        }
        return Object.values(byUser).map(row => ({
            ...row,
            pct: row.total > 0 ? Math.round(row.passed / row.total * 100) : 0,
        }));
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
    // ── Inner component: PhotoCard ───────────────────────────────────────────
    const PhotoCard = ({ assessment: a, isScalePhoto }) => {
        const [expanded, setExpanded] = React.useState(false);
        const isAiRunning = aiRunning[a.blob_id];

        const handleAiReview = async () => {
            if (!isScalePhoto || !sessionId) return;
            setAiRunning(prev => ({ ...prev, [a.blob_id]: true }));
            try {
                const fd = new FormData();
                fd.append('blob_id', a.blob_id);
                fd.append('visit_id', String(a.visit_id));
                const res = await fetch('/audit/api/' + sessionId + '/ai-review/', {
                    method: 'POST',
                    headers: { 'X-CSRFToken': getCsrfToken() },
                    body: fd,
                });
                const data = await res.json();
                if (data.success) {
                    updateAssessment(a.id, {
                        ai_result: data.result || '',
                        ai_notes: data.notes || '',
                    });
                }
            } finally {
                setAiRunning(prev => ({ ...prev, [a.blob_id]: false }));
            }
        };

        const statusBorderColor = a.status === 'pass' ? 'border-green-200'
            : a.status === 'fail' ? 'border-red-200' : 'border-gray-200';

        return (
            <div className={'bg-white rounded-lg shadow-sm border ' + statusBorderColor}>
                <div className="p-4 flex gap-4">
                    {/* Thumbnail */}
                    <div className="flex-shrink-0 w-24 h-24 bg-gray-100 rounded overflow-hidden cursor-pointer"
                        onClick={() => setExpanded(!expanded)}>
                        <img src={a.image_url} alt="visit photo"
                            className="w-full h-full object-cover"
                            loading="lazy" />
                    </div>
                    {/* Meta + controls */}
                    <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                            <span className="text-sm font-medium text-gray-900 truncate">
                                {a.entity_name || 'Unknown'}
                            </span>
                            <span className="text-xs text-gray-400">{a.visit_date}</span>
                        </div>
                        <div className="text-xs text-gray-500 font-mono mb-2">{a.username}</div>

                        {/* Pass / Fail buttons */}
                        <div className="flex items-center gap-2 flex-wrap">
                            <button onClick={() => handleAssessResult(a.id, 'pass')}
                                className={'px-3 py-1 text-sm rounded border transition-colors ' +
                                    (a.status === 'pass'
                                        ? 'bg-green-600 text-white border-green-600'
                                        : 'bg-white text-green-700 border-green-300 hover:bg-green-50')}>
                                <i className="fa-solid fa-check mr-1"></i>Pass
                            </button>
                            <button onClick={() => handleAssessResult(a.id, 'fail')}
                                className={'px-3 py-1 text-sm rounded border transition-colors ' +
                                    (a.status === 'fail'
                                        ? 'bg-red-600 text-white border-red-600'
                                        : 'bg-white text-red-700 border-red-300 hover:bg-red-50')}>
                                <i className="fa-solid fa-times mr-1"></i>Fail
                            </button>

                            {/* AI Review — enabled for scale photos only */}
                            <button
                                onClick={handleAiReview}
                                disabled={!isScalePhoto || isAiRunning}
                                title={!isScalePhoto ? 'AI review is only available for Scale Photos' : 'Run AI review'}
                                className={'px-3 py-1 text-sm rounded border transition-colors ' +
                                    (isScalePhoto
                                        ? 'bg-purple-50 text-purple-700 border-purple-300 hover:bg-purple-100'
                                        : 'bg-gray-50 text-gray-400 border-gray-200 cursor-not-allowed opacity-50')}>
                                {isAiRunning
                                    ? <i className="fa-solid fa-spinner fa-spin mr-1"></i>
                                    : <i className="fa-solid fa-robot mr-1"></i>}
                                AI Review
                            </button>
                        </div>

                        {/* AI result badge */}
                        {a.ai_result && (
                            <div className={'mt-2 text-xs px-2 py-1 rounded inline-flex items-center gap-1 ' +
                                (a.ai_result === 'match' ? 'bg-green-50 text-green-700'
                                    : a.ai_result === 'no_match' ? 'bg-red-50 text-red-700'
                                    : 'bg-yellow-50 text-yellow-700')}>
                                <i className="fa-solid fa-robot"></i>
                                AI: {a.ai_result}{a.ai_notes ? ' — ' + a.ai_notes : ''}
                            </div>
                        )}

                        {/* Notes */}
                        <input
                            type="text"
                            value={a.notes || ''}
                            onChange={e => handleNotesChange(a.id, e.target.value)}
                            placeholder="Add note..."
                            className="mt-2 w-full text-sm border border-gray-200 rounded px-2 py-1 focus:ring-1 focus:ring-blue-500 focus:outline-none"
                        />
                    </div>
                </div>

                {/* Expanded full image */}
                {expanded && (
                    <div className="border-t border-gray-100 p-4">
                        <img src={a.image_url} alt="full visit photo"
                            className="max-w-full rounded shadow-sm" />
                    </div>
                )}
            </div>
        );
    };

    // ── Inner component: Review ──────────────────────────────────────────────
    const ReviewPhase = () => {
        const config = instance.state?.config || {};
        const currentThreshold = config.threshold ?? 80;
        const currentImageType = config.image_type || 'scale_photo';
        const isScalePhoto = currentImageType === 'scale_photo';

        const total = assessments.length;
        const passed = assessments.filter(a => a.status === 'pass').length;
        const failed = assessments.filter(a => a.status === 'fail').length;
        const pending = total - passed - failed;

        if (loadingReview) return (
            <div className="bg-white rounded-lg shadow-sm p-12 text-center">
                <i className="fa-solid fa-spinner fa-spin text-gray-400 text-3xl mb-3"></i>
                <p className="text-gray-500 mt-3">Loading photos...</p>
            </div>
        );
        if (reviewError) return (
            <div className="bg-red-50 border border-red-200 rounded-lg p-6">
                <p className="text-red-700">Error loading review data: {reviewError}</p>
            </div>
        );

        return (
            <div className="space-y-6">
                {/* Stats bar */}
                <div className="grid grid-cols-4 gap-4">
                    {[
                        { label: 'Total', value: total, color: 'blue', icon: 'fa-images' },
                        { label: 'Pending', value: pending, color: 'yellow', icon: 'fa-clock' },
                        { label: 'Passed', value: passed, color: 'green', icon: 'fa-check' },
                        { label: 'Failed', value: failed, color: 'red', icon: 'fa-times' },
                    ].map(card => (
                        <div key={card.label}
                            className={'bg-white rounded-lg shadow-sm p-4 border-l-4 border-' + card.color + '-500'}>
                            <div className={'text-2xl font-bold text-' + card.color + '-600'}>
                                {card.value}
                            </div>
                            <div className="text-sm text-gray-500 flex items-center gap-1 mt-1">
                                <i className={'fa-solid ' + card.icon + ' text-xs'}></i>
                                {card.label}
                            </div>
                        </div>
                    ))}
                </div>

                {/* Save indicator */}
                {isSaving && (
                    <div className="text-sm text-gray-400 flex items-center gap-1">
                        <i className="fa-solid fa-spinner fa-spin text-xs"></i> Saving...
                    </div>
                )}

                {/* Photo list */}
                <div className="space-y-3">
                    {assessments.map(a => (
                        <PhotoCard key={a.id} assessment={a} isScalePhoto={isScalePhoto} />
                    ))}
                    {assessments.length === 0 && (
                        <div className="bg-white rounded-lg shadow-sm p-8 text-center text-gray-500">
                            No photos found for the selected criteria.
                        </div>
                    )}
                </div>

                {/* FLW Summary Table — placeholder, replaced in Task 7 */}
                <div id="flw-summary-placeholder"></div>

                {/* Complete Image Review — placeholder, replaced in Task 8 */}
                <div id="complete-section-placeholder"></div>
            </div>
        );
    };

    // ── Placeholder inner components (to be replaced in later tasks) ─────────
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
