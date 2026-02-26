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
    const [datePreset, setDatePreset] = React.useState('last_week'); // TODO Task 5: persist date_preset in handleCreate config and restore from instance.state?.config?.date_preset
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

    // ── Placeholder: replaced in Task 5 ─────────────────────────────────────
    const handleCreate = async () => {};

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

    // ── Placeholder inner components (to be replaced in later tasks) ─────────
    const CreatingPhase = () => <div className="bg-white rounded-lg shadow-sm p-6 text-gray-500">Creating...</div>;
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
