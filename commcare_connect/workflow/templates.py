"""
Workflow Templates - Pre-built workflow definitions and render code.

This module provides template definitions that can be used to create
new workflows. Both the views and integration tests import from here.
"""

# =============================================================================
# Template: Performance Review
# =============================================================================

# Pipeline schema for extracting worker performance data
PERFORMANCE_REVIEW_PIPELINE_SCHEMA = {
    "name": "Worker Performance Data",
    "description": "Extract performance metrics from form submissions for each worker",
    "version": 1,
    "grouping_key": "username",
    "terminal_stage": "aggregated",
    "fields": [
        {
            "name": "visit_count",
            "path": "form.meta.instanceID",
            "aggregation": "count",
            "description": "Total form submissions",
        },
        {
            "name": "last_visit_date",
            "path": "form.meta.timeEnd",
            "aggregation": "last",
            "description": "Date of most recent submission",
        },
        {
            "name": "first_visit_date",
            "path": "form.meta.timeEnd",
            "aggregation": "first",
            "description": "Date of first submission",
        },
        {
            "name": "app_version",
            "path": "form.meta.appVersion",
            "aggregation": "last",
            "description": "Application version used",
        },
    ],
    "histograms": [],
    "filters": {},
}

PERFORMANCE_REVIEW_DEFINITION = {
    "name": "Weekly Performance Review",
    "description": "Review each worker's performance and mark as confirmed, needs audit, or create a task",
    "version": 1,
    "templateType": "performance_review",
    "statuses": [
        {"id": "pending", "label": "Pending Review", "color": "gray"},
        {"id": "confirmed", "label": "Confirmed Good", "color": "green"},
        {"id": "needs_audit", "label": "Needs Audit", "color": "yellow"},
        {"id": "task_created", "label": "Task Created", "color": "blue"},
    ],
    "config": {
        "showSummaryCards": True,
        "showFilters": True,
    },
    "pipeline_sources": [],  # Will be populated when pipeline is created
}

PERFORMANCE_REVIEW_RENDER_CODE = """function WorkflowUI({ definition, instance, workers, pipelines, links, actions, onUpdateState }) {
    const [sortBy, setSortBy] = React.useState('name');
    const [filterStatus, setFilterStatus] = React.useState('all');

    const statuses = definition.statuses || [];
    const workerStates = instance.state?.worker_states || {};
    const config = definition.config || {};

    // Calculate stats
    const stats = React.useMemo(() => {
        const counts = {};
        statuses.forEach(s => { counts[s.id] = 0; });
        workers.forEach(w => {
            const status = workerStates[w.username]?.status || 'pending';
            counts[status] = (counts[status] || 0) + 1;
        });
        return {
            total: workers.length,
            reviewed: workers.length - (counts['pending'] || 0),
            counts
        };
    }, [workers, workerStates, statuses]);

    // Filter workers
    const displayWorkers = React.useMemo(() => {
        let filtered = workers;
        if (filterStatus !== 'all') {
            filtered = workers.filter(w =>
                (workerStates[w.username]?.status || 'pending') === filterStatus
            );
        }
        return [...filtered].sort((a, b) => {
            if (sortBy === 'name') return (a.name || a.username).localeCompare(b.name || b.username);
            if (sortBy === 'visits') return b.visit_count - a.visit_count;
            return 0;
        });
    }, [workers, workerStates, filterStatus, sortBy]);

    const handleStatusChange = async (username, newStatus) => {
        await onUpdateState({
            worker_states: {
                ...workerStates,
                [username]: { ...workerStates[username], status: newStatus }
            }
        });
    };

    const getStatusColor = (statusId) => {
        const colorMap = {
            gray: 'bg-gray-100 text-gray-800',
            green: 'bg-green-100 text-green-800',
            yellow: 'bg-yellow-100 text-yellow-800',
            blue: 'bg-blue-100 text-blue-800',
            red: 'bg-red-100 text-red-800',
            purple: 'bg-purple-100 text-purple-800',
            orange: 'bg-orange-100 text-orange-800',
            pink: 'bg-pink-100 text-pink-800'
        };
        const status = statuses.find(s => s.id === statusId);
        return colorMap[status?.color] || colorMap.gray;
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="bg-white rounded-lg shadow-sm p-6">
                <div className="flex justify-between items-start">
                    <div>
                        <h1 className="text-2xl font-bold text-gray-900">{definition.name}</h1>
                        <p className="text-gray-600 mt-1">{definition.description}</p>
                    </div>
                    <div className="text-sm text-gray-500">
                        {instance.state?.period_start} - {instance.state?.period_end}
                    </div>
                </div>
            </div>

            {/* Summary Cards */}
            {config.showSummaryCards !== false && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="bg-white p-4 rounded-lg shadow-sm">
                        <div className="text-3xl font-bold text-gray-900">{stats.total}</div>
                        <div className="text-gray-600">Total Workers</div>
                    </div>
                    <div className="bg-green-50 p-4 rounded-lg shadow-sm border border-green-200">
                        <div className="text-3xl font-bold text-green-700">{stats.reviewed}</div>
                        <div className="text-gray-600">Reviewed</div>
                    </div>
                    {statuses.slice(0, 2).map(status => (
                        <div key={status.id} className={"p-4 rounded-lg shadow-sm " + getStatusColor(status.id)}>
                            <div className="text-2xl font-bold">{stats.counts[status.id] || 0}</div>
                            <div className="text-sm">{status.label}</div>
                        </div>
                    ))}
                </div>
            )}

            {/* Filters */}
            {config.showFilters !== false && (
                <div className="bg-white rounded-lg shadow-sm p-4">
                    <div className="flex flex-wrap gap-4 items-center">
                        <select
                            value={filterStatus}
                            onChange={e => setFilterStatus(e.target.value)}
                            className="border border-gray-300 rounded-md px-3 py-2 text-sm"
                        >
                            <option value="all">All Statuses</option>
                            {statuses.map(s => (
                                <option key={s.id} value={s.id}>{s.label}</option>
                            ))}
                        </select>
                        <select
                            value={sortBy}
                            onChange={e => setSortBy(e.target.value)}
                            className="border border-gray-300 rounded-md px-3 py-2 text-sm"
                        >
                            <option value="name">Sort by Name</option>
                            <option value="visits">Sort by Visits</option>
                        </select>
                        <div className="ml-auto text-sm text-gray-500">
                            Showing {displayWorkers.length} of {workers.length} workers
                        </div>
                    </div>
                </div>
            )}

            {/* Worker Table */}
            <div className="bg-white rounded-lg shadow-sm overflow-hidden">
                <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                        <tr>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Worker</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Visits</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Last Active</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                        </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                        {displayWorkers.map(worker => {
                            const currentStatus = workerStates[worker.username]?.status || 'pending';
                            return (
                                <tr key={worker.username} className="hover:bg-gray-50">
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <div className="font-medium text-gray-900">{worker.name || worker.username}</div>
                                        <div className="text-sm text-gray-500">{worker.username}</div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                        {worker.visit_count || 0}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                        {worker.last_active || 'Never'}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <select
                                            value={currentStatus}
                                            onChange={e => handleStatusChange(worker.username, e.target.value)}
                                            className="border rounded px-2 py-1 text-sm"
                                        >
                                            {statuses.map(s => (
                                                <option key={s.id} value={s.id}>{s.label}</option>
                                            ))}
                                        </select>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                                        <div className="flex gap-2">
                                            <a
                                                href={links.auditUrl({ username: worker.username, count: 5 })}
                                                className="text-blue-600 hover:text-blue-800"
                                            >
                                                Audit
                                            </a>
                                            <a
                                                href={links.taskUrl({ username: worker.username })}
                                                className="text-blue-600 hover:text-blue-800"
                                            >
                                                Task
                                            </a>
                                        </div>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
                {displayWorkers.length === 0 && (
                    <div className="px-6 py-12 text-center text-gray-500">
                        No workers match the current filter.
                    </div>
                )}
            </div>
        </div>
    );
}"""

# =============================================================================
# Template: OCS Bulk Outreach
# =============================================================================

OCS_OUTREACH_DEFINITION = {
    "name": "OCS Bulk Outreach",
    "description": "Create tasks and initiate AI chatbot conversations for multiple workers at once",
    "version": 1,
    "templateType": "ocs_outreach",
    "defaultPrompt": "Please reach out to this field worker to discuss their recent performance and offer support.",
    "taskTitleTemplate": "AI Outreach: {name}",
    "statuses": [
        {"id": "pending", "label": "Not Started", "color": "gray"},
        {"id": "outreach_initiated", "label": "Outreach Initiated", "color": "blue"},
        {"id": "in_progress", "label": "In Progress", "color": "yellow"},
        {"id": "completed", "label": "Completed", "color": "green"},
    ],
    "pipeline_sources": [],
}

OCS_OUTREACH_RENDER_CODE = """function WorkflowUI({ definition, instance, workers, pipelines, links, actions, onUpdateState }) {
    // OCS State
    const [ocsConnected, setOcsConnected] = React.useState(false);
    const [ocsLoading, setOcsLoading] = React.useState(true);
    const [ocsLoginUrl, setOcsLoginUrl] = React.useState('/labs/ocs/initiate/');
    const [bots, setBots] = React.useState([]);
    const [selectedBot, setSelectedBot] = React.useState('');
    const [promptText, setPromptText] = React.useState(definition.defaultPrompt || '');

    // Worker Selection
    const [selectedWorkers, setSelectedWorkers] = React.useState({});
    const [selectAll, setSelectAll] = React.useState(false);

    // Progress Tracking
    const [isRunning, setIsRunning] = React.useState(false);
    const [progress, setProgress] = React.useState({});

    const workerStates = instance.state?.worker_states || {};

    // Check OCS status on mount
    React.useEffect(() => {
        setOcsLoading(true);
        actions.checkOCSStatus().then(status => {
            setOcsConnected(status.connected);
            setOcsLoginUrl(status.login_url || '/labs/ocs/initiate/');
            if (status.connected) {
                actions.listOCSBots().then(result => {
                    if (result.success) {
                        setBots(result.bots || []);
                        if (result.bots?.length > 0) {
                            setSelectedBot(result.bots[0].id);
                        }
                    }
                    setOcsLoading(false);
                });
            } else {
                setOcsLoading(false);
            }
        }).catch(() => setOcsLoading(false));
    }, []);

    const toggleWorker = (username) => {
        setSelectedWorkers(prev => ({ ...prev, [username]: !prev[username] }));
    };

    const handleSelectAll = () => {
        const newState = !selectAll;
        setSelectAll(newState);
        const newSelected = {};
        workers.forEach(w => { newSelected[w.username] = newState; });
        setSelectedWorkers(newSelected);
    };

    const selectedCount = Object.values(selectedWorkers).filter(Boolean).length;

    const handleCreateTasks = async () => {
        const workersToProcess = workers.filter(w => selectedWorkers[w.username]);
        if (workersToProcess.length === 0) return;

        setIsRunning(true);

        for (const worker of workersToProcess) {
            setProgress(prev => ({ ...prev, [worker.username]: { status: 'creating' } }));

            try {
                const title = (definition.taskTitleTemplate || 'Outreach: {name}')
                    .replace('{name}', worker.name || worker.username);

                const result = await actions.createTaskWithOCS({
                    username: worker.username,
                    title: title,
                    description: promptText,
                    priority: 'medium',
                    ocs: selectedBot ? { experiment: selectedBot, prompt_text: promptText } : undefined
                });

                if (result.success) {
                    const newStatus = selectedBot && result.ocs?.success ? 'ocs_initiated' : 'task_created';
                    setProgress(prev => ({
                        ...prev,
                        [worker.username]: { status: newStatus, task_id: result.task_id }
                    }));

                    await onUpdateState({
                        worker_states: {
                            ...instance.state?.worker_states,
                            [worker.username]: { task_id: result.task_id, status: 'outreach_initiated' }
                        }
                    });
                } else {
                    setProgress(prev => ({
                        ...prev,
                        [worker.username]: { status: 'error', error: result.error || 'Unknown error' }
                    }));
                }
            } catch (err) {
                setProgress(prev => ({
                    ...prev,
                    [worker.username]: { status: 'error', error: err.message || 'Unknown error' }
                }));
            }
        }

        setIsRunning(false);
    };

    const getProgressBadge = (username) => {
        const p = progress[username];
        if (!p) return null;

        const badges = {
            creating: { bg: 'bg-blue-100', text: 'text-blue-800', icon: 'fa-spinner fa-spin', label: 'Creating...' },
            task_created: { bg: 'bg-green-100', text: 'text-green-800', icon: 'fa-check', label: 'Task Created' },
            ocs_initiated: { bg: 'bg-purple-100', text: 'text-purple-800', icon: 'fa-robot', label: 'OCS Initiated' },
            error: { bg: 'bg-red-100', text: 'text-red-800', icon: 'fa-exclamation-triangle', label: 'Error' }
        };

        const badge = badges[p.status];
        if (!badge) return null;

        return (
            <span className={"inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium " + badge.bg + " " + badge.text}>
                <i className={"fa-solid " + badge.icon}></i>
                {badge.label}
            </span>
        );
    };

    return (
        <div className="space-y-6">
            <div className="bg-white rounded-lg shadow-sm p-6">
                <h1 className="text-2xl font-bold text-gray-900">{definition.name}</h1>
                <p className="text-gray-600 mt-1">{definition.description}</p>
            </div>

            {ocsLoading ? (
                <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                    <div className="flex items-center gap-2 text-gray-600">
                        <i className="fa-solid fa-spinner fa-spin"></i>
                        Checking OCS connection...
                    </div>
                </div>
            ) : !ocsConnected ? (
                <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-yellow-800">
                            <i className="fa-solid fa-exclamation-triangle"></i>
                            <span>Open Chat Studio not connected.</span>
                        </div>
                        <a href={ocsLoginUrl} className="px-4 py-2 bg-yellow-600 text-white rounded-lg hover:bg-yellow-700 text-sm font-medium">
                            Connect to OCS
                        </a>
                    </div>
                </div>
            ) : (
                <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                    <div className="flex items-center gap-2 text-green-800">
                        <i className="fa-solid fa-check-circle"></i>
                        <span>Connected to Open Chat Studio - {bots.length} bot(s) available</span>
                    </div>
                </div>
            )}

            <div className="bg-white rounded-lg shadow-sm p-6 space-y-4">
                <h2 className="text-lg font-semibold text-gray-900">Configuration</h2>
                {ocsConnected && bots.length > 0 && (
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">Select AI Bot</label>
                        <select value={selectedBot} onChange={e => setSelectedBot(e.target.value)} className="w-full border border-gray-300 rounded-lg px-3 py-2" disabled={isRunning}>
                            <option value="">No AI Bot (create tasks only)</option>
                            {bots.map(bot => (<option key={bot.id} value={bot.id}>{bot.name}</option>))}
                        </select>
                    </div>
                )}
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">Task Description</label>
                    <textarea value={promptText} onChange={e => setPromptText(e.target.value)} rows={4} className="w-full border border-gray-300 rounded-lg px-3 py-2 resize-none" disabled={isRunning} />
                </div>
            </div>

            <div className="bg-white rounded-lg shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <h2 className="text-lg font-semibold text-gray-900">Select Workers</h2>
                        <span className="text-sm text-gray-500">{selectedCount} of {workers.length} selected</span>
                    </div>
                    <div className="flex items-center gap-3">
                        <button onClick={handleSelectAll} className="text-sm text-blue-600 hover:text-blue-800" disabled={isRunning}>
                            {selectAll ? 'Deselect All' : 'Select All'}
                        </button>
                        <button onClick={handleCreateTasks} disabled={selectedCount === 0 || isRunning || !promptText.trim()} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 text-sm font-medium">
                            {isRunning ? 'Processing...' : 'Create Tasks (' + selectedCount + ')'}
                        </button>
                    </div>
                </div>

                <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                        <tr>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase w-12">
                                <input type="checkbox" checked={selectAll} onChange={handleSelectAll} disabled={isRunning} className="rounded border-gray-300" />
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Worker</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Visits</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                        </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                        {workers.map(worker => (
                            <tr key={worker.username} className={selectedWorkers[worker.username] ? 'bg-blue-50' : 'hover:bg-gray-50'}>
                                <td className="px-6 py-4">
                                    <input type="checkbox" checked={selectedWorkers[worker.username] || false} onChange={() => toggleWorker(worker.username)} disabled={isRunning} className="rounded border-gray-300" />
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap">
                                    <div className="font-medium text-gray-900">{worker.name || worker.username}</div>
                                    <div className="text-sm text-gray-500">{worker.username}</div>
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{worker.visit_count || 0}</td>
                                <td className="px-6 py-4 whitespace-nowrap">{getProgressBadge(worker.username)}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}"""

# =============================================================================
# Template: KMC Scale Validation
# =============================================================================

# Pipeline schema for KMC visit data with scale images and weight readings
KMC_SCALE_VALIDATION_PIPELINE_SCHEMA = {
    "name": "KMC Visits with Scale Images",
    "description": "Extract KMC visit data with scale images and weight readings for ML validation",
    "version": 1,
    "grouping_key": "username",
    "terminal_stage": "visit_level",  # Visit-level to get each individual visit
    "linking_field": "beneficiary_case_id",
    "fields": [
        {
            "name": "beneficiary_case_id",
            "paths": [
                "form.case.@case_id",
                "form.kmc_beneficiary_case_id",
            ],
            "aggregation": "first",
            "description": "Beneficiary case ID (unique per child)",
        },
        {
            "name": "child_name",
            "paths": [
                "form.child_name",
                "form.registration_visit.child_details.child_name",
            ],
            "aggregation": "first",
            "description": "Child name",
        },
        {
            "name": "visit_date",
            "path": "form.meta.timeEnd",
            "aggregation": "first",
            "transform": "date",
            "description": "Visit date from form submission",
        },
        {
            "name": "visit_number",
            "paths": [
                "form.visit_number",
                "form.kmc_visit_counter",
            ],
            "aggregation": "first",
            "description": "Visit number in sequence",
        },
        {
            "name": "weight_reading",
            "path": "form.anthropometric.child_weight_visit",
            "aggregation": "first",
            "description": "User-entered weight reading from form",
        },
        {
            "name": "scale_image_filename",
            "path": "form.anthropometric.upload_weight_image",
            "aggregation": "first",
            "description": "Filename of the scale image uploaded",
        },
        {
            "name": "images",
            "path": "images",
            "aggregation": "first",
            "description": "Image attachments with blob_id UUIDs",
        },
        {
            "name": "entity_name",
            "paths": [
                "form.new_registration_du.deliver.entity_name",
                "form.kmc_non_pay_visit_du.deliver.entity_name",
                "form.kmc_pay_visit_du.deliver.entity_name",
            ],
            "aggregation": "first",
            "description": "Entity name from deliver unit",
        },
    ],
    "histograms": [],
    "filters": {},
}

KMC_SCALE_VALIDATION_DEFINITION = {
    "name": "KMC Scale Validation",
    "description": "Validate weight readings against scale images using ML vision for KMC visits",
    "version": 1,
    "templateType": "kmc_scale_validation",
    "statuses": [
        {"id": "pending", "label": "Pending Validation", "color": "gray"},
        {"id": "validated", "label": "Validated Match", "color": "green"},
        {"id": "mismatch", "label": "Mismatch", "color": "red"},
        {"id": "error", "label": "Error", "color": "yellow"},
        {"id": "skipped", "label": "Skipped", "color": "gray"},
    ],
    "config": {
        "showSummaryCards": True,
        "showFilters": True,
        "jobConfig": {
            "job_type": "scale_validation",
            "params": {
                "image_field": "scale_image_filename",
                "reading_field": "weight_reading",
            },
        },
    },
    "pipeline_sources": [],  # Will be populated when pipeline is created
}

KMC_SCALE_VALIDATION_RENDER_CODE = """function WorkflowUI({ definition, instance, workers, pipelines, links, actions, onUpdateState }) {
    // State for pipeline loading
    const [isLoadingPipeline, setIsLoadingPipeline] = React.useState(true);
    const [pipelineLoadingMessage, setPipelineLoadingMessage] = React.useState('Connecting...');
    const [pipelineLoadingError, setPipelineLoadingError] = React.useState(null);
    const [localPipelineData, setLocalPipelineData] = React.useState([]);

    // State for validation job
    const [filterStatus, setFilterStatus] = React.useState('all');
    const [sortBy, setSortBy] = React.useState('date');
    const [isRunning, setIsRunning] = React.useState(false);
    const [isCancelling, setIsCancelling] = React.useState(false);
    const [jobProgress, setJobProgress] = React.useState(null);
    const [taskId, setTaskId] = React.useState(null);
    const cleanupRef = React.useRef(null);
    const pipelineCleanupRef = React.useRef(null);

    // Date range filters
    const [startDate, setStartDate] = React.useState('');
    const [endDate, setEndDate] = React.useState('');

    // Single row validation state
    const [validatingSingle, setValidatingSingle] = React.useState({});

    // Get validation results from state
    const validationResults = instance.state?.validation_results || {};
    const activeJob = instance.state?.active_job || {};

    // Use locally loaded pipeline data (SSE streaming) or fall back to server-rendered data
    const pipelineData = localPipelineData.length > 0 ? localPipelineData : (pipelines?.visits?.rows || []);

    // Load pipeline data via SSE on mount
    React.useEffect(() => {
        // Build stream URL from apiEndpoints
        const baseUrl = window.WORKFLOW_API_ENDPOINTS?.streamPipelineData;
        if (!baseUrl) {
            console.error('[KMC] No streamPipelineData URL configured');
            setIsLoadingPipeline(false);
            setPipelineLoadingError('Pipeline streaming not configured');
            return;
        }

        // Get opportunity_id from URL params
        const urlParams = new URLSearchParams(window.location.search);
        const opportunityId = urlParams.get('opportunity_id');
        const streamUrl = opportunityId ? baseUrl + '?opportunity_id=' + opportunityId : baseUrl;

        console.log('[KMC] Connecting to pipeline stream:', streamUrl);
        setPipelineLoadingMessage('Connecting to data stream...');

        const eventSource = new EventSource(streamUrl);

        eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                console.log('[KMC] SSE event:', data.message);

                if (data.error) {
                    setPipelineLoadingError(data.error);
                    setIsLoadingPipeline(false);
                    eventSource.close();
                    return;
                }

                setPipelineLoadingMessage(data.message || 'Loading...');

                if (data.complete && data.data) {
                    // Pipeline loading complete
                    const pipelinesData = data.data.pipelines || {};
                    const visitsData = pipelinesData.visits?.rows || [];
                    console.log('[KMC] Loaded', visitsData.length, 'visits');
                    setLocalPipelineData(visitsData);
                    setIsLoadingPipeline(false);
                    eventSource.close();
                }
            } catch (e) {
                console.error('[KMC] Error parsing SSE event:', e);
            }
        };

        eventSource.onerror = (error) => {
            console.error('[KMC] SSE error:', error);
            if (eventSource.readyState === EventSource.CLOSED) {
                setIsLoadingPipeline(false);
                if (!localPipelineData.length) {
                    setPipelineLoadingError('Connection closed');
                }
            }
        };

        pipelineCleanupRef.current = () => eventSource.close();

        return () => {
            eventSource.close();
        };
    }, []);

    // Check if there's an active job on mount
    React.useEffect(() => {
        if (activeJob.status === 'running' && activeJob.job_id) {
            setTaskId(activeJob.job_id);
            setIsRunning(true);
            setJobProgress({
                status: 'running',
                current_stage: activeJob.current_stage || 1,
                total_stages: activeJob.total_stages || 2,
                stage_name: activeJob.stage_name || 'Processing',
                processed: activeJob.processed || 0,
                total: activeJob.total || 0,
            });
            // Reconnect to SSE stream
            reconnectToJob(activeJob.job_id);
        }
    }, []);

    // Cleanup on unmount
    React.useEffect(() => {
        return () => {
            if (cleanupRef.current) {
                cleanupRef.current();
            }
        };
    }, []);

    const reconnectToJob = (jobId) => {
        const cleanup = actions.streamJobProgress(
            jobId,
            (progress) => {
                setJobProgress(progress);
            },
            (itemResult) => {
                // Update local state with new result for real-time UI update
                // The backend already persists this, but we want immediate UI feedback
            },
            (results) => {
                setIsRunning(false);
                setJobProgress({ status: 'completed', ...results });
                // Refresh state to get final results
                window.location.reload();
            },
            (error) => {
                setIsRunning(false);
                setJobProgress({ status: 'failed', error });
            },
            () => {
                setIsRunning(false);
                setJobProgress({ status: 'cancelled' });
            }
        );
        cleanupRef.current = cleanup;
    };

    const handleRunValidation = async () => {
        // Use filtered visits (displayVisits) - respects date range and status filters
        const recordsToValidate = displayVisits;

        if (recordsToValidate.length === 0) {
            setJobProgress({ status: 'failed', error: 'No visits match the current filters. Adjust filters or wait for data to load.' });
            return;
        }

        setIsRunning(true);
        setJobProgress({ status: 'running', current_stage: 1, total_stages: 1, stage_name: 'Validating', processed: 0, total: recordsToValidate.length });

        // Build job config - pass filtered records from UI
        const jobConfig = {
            job_type: 'scale_validation',
            params: {
                image_field: 'scale_image_filename',
                reading_field: 'weight_reading',
            },
            records: recordsToValidate,
        };

        const result = await actions.startJob(instance.id, jobConfig);

        if (result.success && result.task_id) {
            setTaskId(result.task_id);
            reconnectToJob(result.task_id);
        } else {
            setIsRunning(false);
            setJobProgress({ status: 'failed', error: result.error || 'Failed to start job' });
        }
    };

    // Handle single-row validation
    const handleValidateSingle = async (visit) => {
        const id = visit.id || visit.visit_id || visit.beneficiary_case_id;

        // Check if already validating or has result
        if (validatingSingle[id]) return;

        setValidatingSingle(prev => ({ ...prev, [id]: true }));

        // Build job config for single record
        const jobConfig = {
            job_type: 'scale_validation',
            params: {
                image_field: 'scale_image_filename',
                reading_field: 'weight_reading',
            },
            records: [visit],
        };

        try {
            const result = await actions.startJob(instance.id, jobConfig);

            if (result.success && result.task_id) {
                // For single validation, we can poll for completion or just wait
                // Since it's a single record, stream to get the result
                const cleanup = actions.streamJobProgress(
                    result.task_id,
                    () => {}, // progress - not needed for single
                    () => {}, // itemResult
                    () => {
                        // completed - refresh to get results
                        setValidatingSingle(prev => ({ ...prev, [id]: false }));
                        window.location.reload();
                    },
                    (error) => {
                        console.error('Single validation failed:', error);
                        setValidatingSingle(prev => ({ ...prev, [id]: false }));
                    },
                    () => {
                        // cancelled
                        setValidatingSingle(prev => ({ ...prev, [id]: false }));
                    }
                );
            } else {
                console.error('Failed to start single validation:', result.error);
                setValidatingSingle(prev => ({ ...prev, [id]: false }));
            }
        } catch (err) {
            console.error('Error starting single validation:', err);
            setValidatingSingle(prev => ({ ...prev, [id]: false }));
        }
    };

    // Clear date filters
    const handleClearDates = () => {
        setStartDate('');
        setEndDate('');
    };

    const handleCancelJob = async () => {
        if (!taskId) return;
        setIsCancelling(true);
        const result = await actions.cancelJob(taskId, instance.id);
        if (result.success) {
            if (cleanupRef.current) cleanupRef.current();
            setIsRunning(false);
            setJobProgress({ status: 'cancelled' });
        }
        setIsCancelling(false);
    };

    // Calculate stats
    const stats = React.useMemo(() => {
        const counts = { pending: 0, validated: 0, mismatch: 0, error: 0, skipped: 0 };
        pipelineData.forEach(visit => {
            const id = visit.id || visit.visit_id || visit.beneficiary_case_id;
            const result = validationResults[id];
            if (!result) {
                counts.pending++;
            } else if (result.status === 'validated' && result.match) {
                counts.validated++;
            } else if (result.status === 'validated' && !result.match) {
                counts.mismatch++;
            } else if (result.status === 'error') {
                counts.error++;
            } else if (result.status === 'skipped') {
                counts.skipped++;
            } else {
                counts.pending++;
            }
        });
        return {
            total: pipelineData.length,
            processed: pipelineData.length - counts.pending,
            ...counts
        };
    }, [pipelineData, validationResults]);

    // Filter and sort visits
    const displayVisits = React.useMemo(() => {
        let filtered = pipelineData;

        // Apply date range filter
        if (startDate) {
            const start = new Date(startDate);
            start.setHours(0, 0, 0, 0);
            filtered = filtered.filter(visit => {
                if (!visit.visit_date) return false;
                const visitDate = new Date(visit.visit_date);
                return visitDate >= start;
            });
        }
        if (endDate) {
            const end = new Date(endDate);
            end.setHours(23, 59, 59, 999);
            filtered = filtered.filter(visit => {
                if (!visit.visit_date) return false;
                const visitDate = new Date(visit.visit_date);
                return visitDate <= end;
            });
        }

        // Apply status filter
        if (filterStatus !== 'all') {
            filtered = filtered.filter(visit => {
                const id = visit.id || visit.visit_id || visit.beneficiary_case_id;
                const result = validationResults[id];
                if (filterStatus === 'pending') return !result;
                if (filterStatus === 'validated') return result?.status === 'validated' && result?.match;
                if (filterStatus === 'mismatch') return result?.status === 'validated' && !result?.match;
                if (filterStatus === 'error') return result?.status === 'error';
                if (filterStatus === 'skipped') return result?.status === 'skipped';
                return true;
            });
        }

        return [...filtered].sort((a, b) => {
            if (sortBy === 'date') return new Date(b.visit_date || 0) - new Date(a.visit_date || 0);
            if (sortBy === 'worker') return (a.username || '').localeCompare(b.username || '');
            if (sortBy === 'child') return (a.child_name || '').localeCompare(b.child_name || '');
            return 0;
        });
    }, [pipelineData, validationResults, filterStatus, sortBy, startDate, endDate]);

    const getStatusBadge = (visit) => {
        const id = visit.id || visit.visit_id || visit.beneficiary_case_id;
        const result = validationResults[id];

        if (!result) {
            return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800">Pending</span>;
        }

        if (result.status === 'validated' && result.match) {
            return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800"><i className="fa-solid fa-check mr-1"></i>Match</span>;
        }
        if (result.status === 'validated' && !result.match) {
            return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800"><i className="fa-solid fa-xmark mr-1"></i>Mismatch</span>;
        }
        if (result.status === 'error') {
            return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-800" title={result.error}><i className="fa-solid fa-exclamation-triangle mr-1"></i>Error</span>;
        }
        if (result.status === 'skipped') {
            return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-600"><i className="fa-solid fa-forward mr-1"></i>Skipped</span>;
        }

        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800">Unknown</span>;
    };

    // Show loading state while pipeline data is being fetched
    if (isLoadingPipeline) {
        return (
            <div className="space-y-6">
                {/* Header */}
                <div className="bg-white rounded-lg shadow-sm p-6">
                    <h1 className="text-2xl font-bold text-gray-900">{definition.name}</h1>
                    <p className="text-gray-600 mt-1">{definition.description}</p>
                </div>

                {/* Loading Progress */}
                <div className="bg-white rounded-lg shadow-sm p-8">
                    <div className="flex flex-col items-center justify-center space-y-4">
                        <div className="relative">
                            <i className="fa-solid fa-database text-6xl text-blue-200"></i>
                            <div className="absolute inset-0 flex items-center justify-center">
                                <i className="fa-solid fa-spinner fa-spin text-2xl text-blue-600"></i>
                            </div>
                        </div>
                        <div className="text-lg font-medium text-gray-700">Loading Pipeline Data</div>
                        <div className="text-sm text-gray-500">{pipelineLoadingMessage}</div>
                        <div className="w-64 bg-gray-200 rounded-full h-2 overflow-hidden">
                            <div className="bg-blue-600 h-2 rounded-full animate-pulse" style={{width: '60%'}}></div>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    // Show error state if pipeline loading failed
    if (pipelineLoadingError && pipelineData.length === 0) {
        return (
            <div className="space-y-6">
                {/* Header */}
                <div className="bg-white rounded-lg shadow-sm p-6">
                    <h1 className="text-2xl font-bold text-gray-900">{definition.name}</h1>
                    <p className="text-gray-600 mt-1">{definition.description}</p>
                </div>

                {/* Error Message */}
                <div className="bg-red-50 border border-red-200 rounded-lg p-6">
                    <div className="flex items-start">
                        <i className="fa-solid fa-circle-exclamation text-red-500 text-xl mr-3 mt-0.5"></i>
                        <div>
                            <h3 className="font-medium text-red-800">Failed to load pipeline data</h3>
                            <p className="text-red-700 mt-1">{pipelineLoadingError}</p>
                            <button
                                onClick={() => window.location.reload()}
                                className="mt-4 inline-flex items-center px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
                            >
                                <i className="fa-solid fa-refresh mr-2"></i>Retry
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="bg-white rounded-lg shadow-sm p-6">
                <div className="flex justify-between items-start">
                    <div>
                        <h1 className="text-2xl font-bold text-gray-900">{definition.name}</h1>
                        <p className="text-gray-600 mt-1">{definition.description}</p>
                    </div>
                    <div className="flex items-center gap-3">
                        {!isRunning ? (
                            <button
                                onClick={handleRunValidation}
                                disabled={displayVisits.length === 0}
                                className="inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 font-medium"
                            >
                                <i className="fa-solid fa-play mr-2"></i>
                                Run Validation ({displayVisits.length})
                            </button>
                        ) : (
                            <button
                                onClick={handleCancelJob}
                                disabled={isCancelling}
                                className="inline-flex items-center px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:bg-red-400 font-medium"
                            >
                                {isCancelling ? (
                                    <><i className="fa-solid fa-spinner fa-spin mr-2"></i>Cancelling...</>
                                ) : (
                                    <><i className="fa-solid fa-stop mr-2"></i>Cancel Job</>
                                )}
                            </button>
                        )}
                    </div>
                </div>
            </div>

            {/* Job Progress */}
            {jobProgress && (
                <div className="bg-white rounded-lg shadow-sm p-4">
                    <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-3">
                            {jobProgress.status === 'running' && (
                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800">
                                    <i className="fa-solid fa-cog fa-spin mr-1.5"></i>Running
                                </span>
                            )}
                            {jobProgress.status === 'completed' && (
                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                                    <i className="fa-solid fa-check mr-1.5"></i>Completed
                                </span>
                            )}
                            {jobProgress.status === 'failed' && (
                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">
                                    <i className="fa-solid fa-xmark mr-1.5"></i>Failed
                                </span>
                            )}
                            {jobProgress.status === 'cancelled' && (
                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
                                    <i className="fa-solid fa-ban mr-1.5"></i>Cancelled
                                </span>
                            )}
                            {jobProgress.total_stages > 1 && jobProgress.status === 'running' && (
                                <span className="text-sm text-gray-600">
                                    Stage {jobProgress.current_stage}/{jobProgress.total_stages}: {jobProgress.stage_name}
                                </span>
                            )}
                        </div>
                        {jobProgress.total > 0 && (
                            <span className="text-sm text-gray-500">{jobProgress.processed}/{jobProgress.total}</span>
                        )}
                    </div>
                    {jobProgress.status === 'running' && jobProgress.total > 0 && (
                        <div className="w-full bg-gray-200 rounded-full h-2">
                            <div
                                className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                                style={{ width: (jobProgress.processed / jobProgress.total * 100) + '%' }}
                            ></div>
                        </div>
                    )}
                    {jobProgress.error && (
                        <div className="mt-2 text-sm text-red-600">{jobProgress.error}</div>
                    )}
                </div>
            )}

            {/* Summary Cards */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                <div className="bg-white p-4 rounded-lg shadow-sm">
                    <div className="text-3xl font-bold text-gray-900">{stats.total}</div>
                    <div className="text-gray-600">Total Visits</div>
                </div>
                <div className="bg-green-50 p-4 rounded-lg shadow-sm border border-green-200">
                    <div className="text-3xl font-bold text-green-700">{stats.validated}</div>
                    <div className="text-gray-600">Matches</div>
                </div>
                <div className="bg-red-50 p-4 rounded-lg shadow-sm border border-red-200">
                    <div className="text-3xl font-bold text-red-700">{stats.mismatch}</div>
                    <div className="text-gray-600">Mismatches</div>
                </div>
                <div className="bg-yellow-50 p-4 rounded-lg shadow-sm border border-yellow-200">
                    <div className="text-2xl font-bold text-yellow-700">{stats.error}</div>
                    <div className="text-gray-600">Errors</div>
                </div>
                <div className="bg-gray-50 p-4 rounded-lg shadow-sm border border-gray-200">
                    <div className="text-2xl font-bold text-gray-700">{stats.pending}</div>
                    <div className="text-gray-600">Pending</div>
                </div>
            </div>

            {/* Filters */}
            <div className="bg-white rounded-lg shadow-sm p-4">
                <div className="flex flex-wrap gap-4 items-center">
                    {/* Date Range Filters */}
                    <div className="flex items-center gap-2">
                        <label className="text-sm text-gray-600">From:</label>
                        <input
                            type="date"
                            value={startDate}
                            onChange={e => setStartDate(e.target.value)}
                            className="border border-gray-300 rounded-md px-3 py-2 text-sm"
                        />
                    </div>
                    <div className="flex items-center gap-2">
                        <label className="text-sm text-gray-600">To:</label>
                        <input
                            type="date"
                            value={endDate}
                            onChange={e => setEndDate(e.target.value)}
                            className="border border-gray-300 rounded-md px-3 py-2 text-sm"
                        />
                    </div>
                    {(startDate || endDate) && (
                        <button
                            onClick={handleClearDates}
                            className="text-sm text-blue-600 hover:text-blue-800"
                        >
                            Clear dates
                        </button>
                    )}

                    <div className="border-l border-gray-300 h-8 mx-2"></div>

                    <select
                        value={filterStatus}
                        onChange={e => setFilterStatus(e.target.value)}
                        className="border border-gray-300 rounded-md px-3 py-2 text-sm"
                    >
                        <option value="all">All Results</option>
                        <option value="pending">Pending</option>
                        <option value="validated">Matches</option>
                        <option value="mismatch">Mismatches</option>
                        <option value="error">Errors</option>
                        <option value="skipped">Skipped</option>
                    </select>
                    <select
                        value={sortBy}
                        onChange={e => setSortBy(e.target.value)}
                        className="border border-gray-300 rounded-md px-3 py-2 text-sm"
                    >
                        <option value="date">Sort by Date</option>
                        <option value="worker">Sort by Worker</option>
                        <option value="child">Sort by Child</option>
                    </select>
                    <div className="ml-auto text-sm text-gray-500">
                        Showing {displayVisits.length} of {pipelineData.length} visits
                        {displayVisits.length !== pipelineData.length && displayVisits.length > 0 && (
                            <span className="ml-2 text-blue-600">
                                (filtered)
                            </span>
                        )}
                    </div>
                </div>
            </div>

            {/* Visits Table */}
            <div className="bg-white rounded-lg shadow-sm overflow-hidden">
                <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                        <tr>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Child</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Visit Date</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Worker</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Weight</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Image</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Validation</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                        </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                        {displayVisits.map((visit, idx) => {
                            const id = visit.id || visit.visit_id || visit.beneficiary_case_id || idx;
                            const result = validationResults[id];
                            const isValidating = validatingSingle[id];
                            const hasResult = !!result;
                            const canValidate = visit.scale_image_filename && visit.weight_reading && !isRunning;

                            return (
                                <tr key={id} className="hover:bg-gray-50">
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <div className="font-medium text-gray-900">{visit.child_name || visit.entity_name || '-'}</div>
                                        <div className="text-xs text-gray-500">Visit #{visit.visit_number || '-'}</div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                                        {visit.visit_date ? new Date(visit.visit_date).toLocaleDateString() : '-'}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                                        {visit.username || '-'}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <span className="text-sm font-mono bg-gray-100 px-2 py-1 rounded">
                                            {visit.weight_reading || '-'}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                                        {visit.scale_image_filename ? (
                                            <span className="text-green-600"><i className="fa-solid fa-image mr-1"></i>Yes</span>
                                        ) : (
                                            <span className="text-gray-400"><i className="fa-solid fa-image-slash mr-1"></i>No</span>
                                        )}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        {getStatusBadge(visit)}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        {isValidating ? (
                                            <span className="inline-flex items-center px-2.5 py-1 text-xs font-medium text-blue-700">
                                                <i className="fa-solid fa-spinner fa-spin mr-1.5"></i>Validating...
                                            </span>
                                        ) : hasResult ? (
                                            <button
                                                onClick={() => handleValidateSingle(visit)}
                                                disabled={!canValidate}
                                                className="inline-flex items-center px-2.5 py-1 text-xs font-medium text-gray-600 hover:text-blue-600 disabled:opacity-50 disabled:cursor-not-allowed"
                                                title="Re-validate this visit"
                                            >
                                                <i className="fa-solid fa-rotate mr-1.5"></i>Re-validate
                                            </button>
                                        ) : (
                                            <button
                                                onClick={() => handleValidateSingle(visit)}
                                                disabled={!canValidate}
                                                className="inline-flex items-center px-2.5 py-1 text-xs font-medium text-blue-600 hover:text-blue-800 disabled:opacity-50 disabled:cursor-not-allowed"
                                                title={!canValidate ? 'Missing image or weight data' : 'Validate this visit'}
                                            >
                                                <i className="fa-solid fa-check-circle mr-1.5"></i>Validate
                                            </button>
                                        )}
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
                {displayVisits.length === 0 && (
                    <div className="px-6 py-12 text-center text-gray-500">
                        {pipelineData.length === 0 ? (
                            <div>
                                <i className="fa-solid fa-database text-4xl text-gray-300 mb-4"></i>
                                <p>No visits found for this opportunity.</p>
                            </div>
                        ) : (
                            <p>No visits match the current filter.</p>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}"""

# =============================================================================
# Template: Audit with AI Review
# =============================================================================

AUDIT_WITH_AI_REVIEW_DEFINITION = {
    "name": "Audit with AI Review",
    "description": "Create audit sessions and optionally run AI review agents to pre-validate images",
    "version": 1,
    "templateType": "audit_with_ai_review",
    "statuses": [
        {"id": "configuring", "label": "Configuring", "color": "gray"},
        {"id": "creating", "label": "Creating Audits", "color": "blue"},
        {"id": "ai_reviewing", "label": "Running AI Review", "color": "purple"},
        {"id": "completed", "label": "Completed", "color": "green"},
        {"id": "failed", "label": "Failed", "color": "red"},
    ],
    "config": {
        "showSummaryCards": True,
        "defaultAuditType": "date_range",
        "defaultGranularity": "combined",
    },
    "pipeline_sources": [],
}

AUDIT_WITH_AI_REVIEW_RENDER_CODE = """function WorkflowUI({ definition, instance, workers, pipelines, links, actions, onUpdateState }) {
    // Audit configuration state
    const [auditType, setAuditType] = React.useState(instance.state?.audit_config?.audit_type || 'date_range');
    const [granularity, setGranularity] = React.useState(instance.state?.audit_config?.granularity || 'combined');
    const [countAcrossAll, setCountAcrossAll] = React.useState(instance.state?.audit_config?.count_across_all || 50);
    const [countPerFlw, setCountPerFlw] = React.useState(instance.state?.audit_config?.count_per_flw || 10);
    const [startDate, setStartDate] = React.useState(instance.state?.audit_config?.start_date || '');
    const [endDate, setEndDate] = React.useState(instance.state?.audit_config?.end_date || '');
    const [titleSuffix, setTitleSuffix] = React.useState(instance.state?.audit_config?.title_suffix || '');

    // AI Agent state
    const [availableAgents, setAvailableAgents] = React.useState([]);
    const [selectedAgent, setSelectedAgent] = React.useState(instance.state?.audit_config?.ai_agent_id || '');
    const [loadingAgents, setLoadingAgents] = React.useState(true);

    // Related fields configuration
    const [relatedFields, setRelatedFields] = React.useState(instance.state?.audit_config?.related_fields || []);

    // Execution state
    const [isRunning, setIsRunning] = React.useState(false);
    const [progress, setProgress] = React.useState(null);
    const [taskId, setTaskId] = React.useState(null);
    const cleanupRef = React.useRef(null);

    // Results
    const auditResults = instance.state?.audit_results || null;

    // Get opportunity from URL or instance state
    const urlParams = new URLSearchParams(window.location.search);
    const opportunityId = parseInt(urlParams.get('opportunity_id')) || instance.state?.opportunity_id;
    const opportunityName = instance.state?.opportunity_name || 'Selected Opportunity';

    // Load AI agents on mount
    React.useEffect(() => {
        setLoadingAgents(true);
        fetch('/labs/audit/api/ai-agents/')
            .then(res => res.json())
            .then(data => {
                setAvailableAgents(data.agents || []);
                setLoadingAgents(false);
            })
            .catch(err => {
                console.error('Failed to load AI agents:', err);
                setLoadingAgents(false);
            });
    }, []);

    // Set default dates (last 30 days)
    React.useEffect(() => {
        if (!startDate && !endDate) {
            const today = new Date();
            const thirtyDaysAgo = new Date(today);
            thirtyDaysAgo.setDate(today.getDate() - 30);
            setStartDate(thirtyDaysAgo.toISOString().split('T')[0]);
            setEndDate(today.toISOString().split('T')[0]);
        }
    }, []);

    // Cleanup on unmount
    React.useEffect(() => {
        return () => {
            if (cleanupRef.current) cleanupRef.current();
        };
    }, []);

    // Add related field rule
    const addRelatedField = () => {
        setRelatedFields([...relatedFields, { imagePath: '', fieldPath: '', label: '' }]);
    };

    // Remove related field rule
    const removeRelatedField = (index) => {
        setRelatedFields(relatedFields.filter((_, i) => i !== index));
    };

    // Update related field
    const updateRelatedField = (index, field, value) => {
        const updated = [...relatedFields];
        updated[index] = { ...updated[index], [field]: value };
        setRelatedFields(updated);
    };

    // Build audit criteria
    const buildCriteria = () => {
        const criteria = {
            audit_type: auditType,
            granularity: granularity,
            title: titleSuffix,
            relatedFields: relatedFields.filter(rf => rf.imagePath && rf.fieldPath),
        };

        if (auditType === 'date_range') {
            criteria.startDate = startDate;
            criteria.endDate = endDate;
        } else if (auditType === 'last_n_total') {
            criteria.countAcrossAll = countAcrossAll;
        } else if (auditType === 'last_n_per_flw') {
            criteria.countPerFlw = countPerFlw;
        }

        return criteria;
    };

    // Start audit creation
    const handleCreateAudit = async () => {
        if (!opportunityId) {
            alert('No opportunity selected');
            return;
        }

        setIsRunning(true);
        setProgress({ status: 'starting', message: 'Initializing...' });

        // Save config to workflow state
        const auditConfig = {
            audit_type: auditType,
            granularity: granularity,
            count_across_all: countAcrossAll,
            count_per_flw: countPerFlw,
            start_date: startDate,
            end_date: endDate,
            title_suffix: titleSuffix,
            ai_agent_id: selectedAgent,
            related_fields: relatedFields,
        };

        await onUpdateState({
            audit_config: auditConfig,
            opportunity_id: opportunityId,
        });

        // Build request
        const criteria = buildCriteria();

        try {
            const result = await actions.createAudit({
                opportunities: [{ id: opportunityId, name: opportunityName }],
                criteria: criteria,
                workflow_run_id: instance.id,
                ai_agent_id: selectedAgent || undefined,
            });

            if (result.success && result.task_id) {
                setTaskId(result.task_id);

                // Stream progress
                const cleanup = actions.streamAuditProgress(
                    result.task_id,
                    (progressData) => {
                        setProgress(progressData);
                    },
                    async (finalResult) => {
                        setIsRunning(false);
                        setProgress({ status: 'completed', ...finalResult });

                        // Save results to workflow state
                        await onUpdateState({
                            audit_results: finalResult,
                            status: 'completed',
                        });
                    },
                    (error) => {
                        setIsRunning(false);
                        setProgress({ status: 'failed', error });
                    }
                );
                cleanupRef.current = cleanup;
            } else {
                setIsRunning(false);
                setProgress({ status: 'failed', error: result.error || 'Failed to start audit creation' });
            }
        } catch (err) {
            setIsRunning(false);
            setProgress({ status: 'failed', error: err.message || 'Unknown error' });
        }
    };

    // Get selected agent info
    const selectedAgentInfo = availableAgents.find(a => a.agent_id === selectedAgent);

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="bg-white rounded-lg shadow-sm p-6">
                <div className="flex justify-between items-start">
                    <div>
                        <h1 className="text-2xl font-bold text-gray-900">{definition.name}</h1>
                        <p className="text-gray-600 mt-1">{definition.description}</p>
                    </div>
                    {opportunityId && (
                        <div className="text-sm text-gray-500 bg-gray-100 px-3 py-1 rounded">
                            Opportunity: {opportunityName} (ID: {opportunityId})
                        </div>
                    )}
                </div>
            </div>

            {/* Results Summary (if completed) */}
            {auditResults && (
                <div className="bg-green-50 border border-green-200 rounded-lg p-6">
                    <h2 className="text-lg font-semibold text-green-800 mb-4">
                        <i className="fa-solid fa-check-circle mr-2"></i>Audit Created Successfully
                    </h2>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div className="bg-white p-3 rounded shadow-sm">
                            <div className="text-2xl font-bold text-gray-900">{auditResults.sessions?.length || 0}</div>
                            <div className="text-sm text-gray-600">Sessions Created</div>
                        </div>
                        <div className="bg-white p-3 rounded shadow-sm">
                            <div className="text-2xl font-bold text-gray-900">{auditResults.total_visits || 0}</div>
                            <div className="text-sm text-gray-600">Total Visits</div>
                        </div>
                        <div className="bg-white p-3 rounded shadow-sm">
                            <div className="text-2xl font-bold text-gray-900">{auditResults.total_images || 0}</div>
                            <div className="text-sm text-gray-600">Total Images</div>
                        </div>
                        {auditResults.ai_review && (
                            <div className="bg-purple-50 p-3 rounded shadow-sm border border-purple-200">
                                <div className="text-2xl font-bold text-purple-700">{auditResults.ai_review.total_reviewed || 0}</div>
                                <div className="text-sm text-purple-600">AI Reviewed</div>
                            </div>
                        )}
                    </div>

                    {/* AI Review Summary */}
                    {auditResults.ai_review && (
                        <div className="mt-4 p-4 bg-purple-50 rounded border border-purple-200">
                            <h3 className="font-medium text-purple-800 mb-2">
                                <i className="fa-solid fa-robot mr-2"></i>
                                AI Review Results ({auditResults.ai_review.agent_name})
                            </h3>
                            <div className="flex gap-4 text-sm">
                                <span className="text-green-700">
                                    <i className="fa-solid fa-check mr-1"></i>
                                    Passed: {auditResults.ai_review.total_passed || 0}
                                </span>
                                <span className="text-red-700">
                                    <i className="fa-solid fa-xmark mr-1"></i>
                                    Failed: {auditResults.ai_review.total_failed || 0}
                                </span>
                                <span className="text-yellow-700">
                                    <i className="fa-solid fa-exclamation-triangle mr-1"></i>
                                    Errors: {auditResults.ai_review.total_errors || 0}
                                </span>
                                <span className="text-gray-600">
                                    <i className="fa-solid fa-forward mr-1"></i>
                                    Skipped: {auditResults.ai_review.total_skipped || 0}
                                </span>
                            </div>
                        </div>
                    )}

                    {/* Session Links */}
                    {auditResults.sessions && auditResults.sessions.length > 0 && (
                        <div className="mt-4">
                            <h3 className="font-medium text-gray-800 mb-2">Created Sessions:</h3>
                            <div className="flex flex-wrap gap-2">
                                {auditResults.sessions.map(session => (
                                    <a
                                        key={session.id}
                                        href={'/labs/audit/' + session.id + '/bulk/'}
                                        className="inline-flex items-center px-3 py-1 bg-blue-100 text-blue-800 rounded hover:bg-blue-200"
                                    >
                                        <i className="fa-solid fa-external-link mr-2"></i>
                                        {session.title} ({session.visits} visits)
                                    </a>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* Progress */}
            {isRunning && progress && (
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                    <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-3">
                            <i className="fa-solid fa-spinner fa-spin text-blue-600"></i>
                            <span className="font-medium text-blue-800">
                                {progress.stage_name || 'Processing...'}
                            </span>
                        </div>
                        {progress.current_stage && progress.total_stages && (
                            <span className="text-sm text-blue-600">
                                Stage {progress.current_stage}/{progress.total_stages}
                            </span>
                        )}
                    </div>
                    {progress.total > 0 && (
                        <div className="w-full bg-blue-200 rounded-full h-2">
                            <div
                                className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                                style={{ width: (progress.processed / progress.total * 100) + '%' }}
                            ></div>
                        </div>
                    )}
                    <div className="mt-2 text-sm text-blue-700">{progress.message}</div>
                </div>
            )}

            {/* Error */}
            {progress?.status === 'failed' && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                    <div className="flex items-center gap-2 text-red-800">
                        <i className="fa-solid fa-circle-exclamation"></i>
                        <span className="font-medium">Error: {progress.error}</span>
                    </div>
                </div>
            )}

            {/* Configuration (only show if not completed) */}
            {!auditResults && (
                <>
                    {/* Audit Type Selection */}
                    <div className="bg-white rounded-lg shadow-sm p-6">
                        <h2 className="text-lg font-semibold text-gray-900 mb-4">
                            <i className="fa-solid fa-filter mr-2 text-blue-600"></i>
                            Audit Type
                        </h2>
                        <div className="space-y-3">
                            <label className="flex items-start gap-3 p-3 border rounded-lg cursor-pointer hover:bg-gray-50">
                                <input
                                    type="radio"
                                    name="auditType"
                                    value="date_range"
                                    checked={auditType === 'date_range'}
                                    onChange={e => setAuditType(e.target.value)}
                                    className="mt-1"
                                />
                                <div>
                                    <div className="font-medium">Date Range</div>
                                    <div className="text-sm text-gray-600">Audit all visits within a date range</div>
                                    {auditType === 'date_range' && (
                                        <div className="mt-3 flex gap-4">
                                            <div>
                                                <label className="block text-xs text-gray-500 mb-1">Start Date</label>
                                                <input
                                                    type="date"
                                                    value={startDate}
                                                    onChange={e => setStartDate(e.target.value)}
                                                    className="border rounded px-3 py-1 text-sm"
                                                />
                                            </div>
                                            <div>
                                                <label className="block text-xs text-gray-500 mb-1">End Date</label>
                                                <input
                                                    type="date"
                                                    value={endDate}
                                                    onChange={e => setEndDate(e.target.value)}
                                                    className="border rounded px-3 py-1 text-sm"
                                                />
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </label>

                            <label className="flex items-start gap-3 p-3 border rounded-lg cursor-pointer hover:bg-gray-50">
                                <input
                                    type="radio"
                                    name="auditType"
                                    value="last_n_total"
                                    checked={auditType === 'last_n_total'}
                                    onChange={e => setAuditType(e.target.value)}
                                    className="mt-1"
                                />
                                <div>
                                    <div className="font-medium">Last N Visits (Total)</div>
                                    <div className="text-sm text-gray-600">Audit the most recent N visits across all FLWs</div>
                                    {auditType === 'last_n_total' && (
                                        <div className="mt-3">
                                            <label className="block text-xs text-gray-500 mb-1">Number of Visits</label>
                                            <input
                                                type="number"
                                                min="1"
                                                max="1000"
                                                value={countAcrossAll}
                                                onChange={e => setCountAcrossAll(parseInt(e.target.value) || 50)}
                                                className="border rounded px-3 py-1 text-sm w-24"
                                            />
                                        </div>
                                    )}
                                </div>
                            </label>

                            <label className="flex items-start gap-3 p-3 border rounded-lg cursor-pointer hover:bg-gray-50">
                                <input
                                    type="radio"
                                    name="auditType"
                                    value="last_n_per_flw"
                                    checked={auditType === 'last_n_per_flw'}
                                    onChange={e => setAuditType(e.target.value)}
                                    className="mt-1"
                                />
                                <div>
                                    <div className="font-medium">Last N Visits per FLW</div>
                                    <div className="text-sm text-gray-600">Audit the most recent N visits for each field worker</div>
                                    {auditType === 'last_n_per_flw' && (
                                        <div className="mt-3">
                                            <label className="block text-xs text-gray-500 mb-1">Visits per FLW</label>
                                            <input
                                                type="number"
                                                min="1"
                                                max="100"
                                                value={countPerFlw}
                                                onChange={e => setCountPerFlw(parseInt(e.target.value) || 10)}
                                                className="border rounded px-3 py-1 text-sm w-24"
                                            />
                                        </div>
                                    )}
                                </div>
                            </label>
                        </div>
                    </div>

                    {/* Granularity */}
                    <div className="bg-white rounded-lg shadow-sm p-6">
                        <h2 className="text-lg font-semibold text-gray-900 mb-4">
                            <i className="fa-solid fa-layer-group mr-2 text-blue-600"></i>
                            Audit Granularity
                        </h2>
                        <div className="flex gap-4">
                            <label className="flex items-center gap-2">
                                <input
                                    type="radio"
                                    name="granularity"
                                    value="combined"
                                    checked={granularity === 'combined'}
                                    onChange={e => setGranularity(e.target.value)}
                                />
                                <span>Single audit for all</span>
                            </label>
                            <label className="flex items-center gap-2">
                                <input
                                    type="radio"
                                    name="granularity"
                                    value="per_flw"
                                    checked={granularity === 'per_flw'}
                                    onChange={e => setGranularity(e.target.value)}
                                />
                                <span>One audit per FLW</span>
                            </label>
                        </div>
                    </div>

                    {/* Related Fields */}
                    <div className="bg-white rounded-lg shadow-sm p-6">
                        <h2 className="text-lg font-semibold text-gray-900 mb-4">
                            <i className="fa-solid fa-link mr-2 text-blue-600"></i>
                            Related Fields (Optional)
                        </h2>
                        <p className="text-sm text-gray-600 mb-4">
                            Associate form field values with images for display during review.
                        </p>
                        <div className="space-y-3">
                            {relatedFields.map((rf, index) => (
                                <div key={index} className="flex gap-3 items-end p-3 bg-gray-50 rounded">
                                    <div className="flex-1">
                                        <label className="block text-xs text-gray-500 mb-1">Image Path</label>
                                        <input
                                            type="text"
                                            value={rf.imagePath}
                                            onChange={e => updateRelatedField(index, 'imagePath', e.target.value)}
                                            placeholder="form/photo_field"
                                            className="w-full border rounded px-3 py-1 text-sm"
                                        />
                                    </div>
                                    <div className="flex-1">
                                        <label className="block text-xs text-gray-500 mb-1">Field Path</label>
                                        <input
                                            type="text"
                                            value={rf.fieldPath}
                                            onChange={e => updateRelatedField(index, 'fieldPath', e.target.value)}
                                            placeholder="form/related_field"
                                            className="w-full border rounded px-3 py-1 text-sm"
                                        />
                                    </div>
                                    <div className="flex-1">
                                        <label className="block text-xs text-gray-500 mb-1">Label</label>
                                        <input
                                            type="text"
                                            value={rf.label}
                                            onChange={e => updateRelatedField(index, 'label', e.target.value)}
                                            placeholder="Display Label"
                                            className="w-full border rounded px-3 py-1 text-sm"
                                        />
                                    </div>
                                    <button
                                        onClick={() => removeRelatedField(index)}
                                        className="text-red-500 hover:text-red-700 px-2 py-1"
                                    >
                                        <i className="fa-solid fa-times"></i>
                                    </button>
                                </div>
                            ))}
                            <button
                                onClick={addRelatedField}
                                className="text-sm text-blue-600 hover:text-blue-800"
                            >
                                <i className="fa-solid fa-plus mr-1"></i>Add Related Field Rule
                            </button>
                        </div>
                    </div>

                    {/* AI Agent Selection */}
                    <div className="bg-white rounded-lg shadow-sm p-6">
                        <h2 className="text-lg font-semibold text-gray-900 mb-4">
                            <i className="fa-solid fa-robot mr-2 text-purple-600"></i>
                            AI Review Agent (Optional)
                        </h2>
                        <p className="text-sm text-gray-600 mb-4">
                            Run an AI agent to automatically pre-validate images after the audit is created.
                        </p>
                        {loadingAgents ? (
                            <div className="text-gray-500">
                                <i className="fa-solid fa-spinner fa-spin mr-2"></i>Loading agents...
                            </div>
                        ) : (
                            <div className="space-y-3">
                                <select
                                    value={selectedAgent}
                                    onChange={e => setSelectedAgent(e.target.value)}
                                    className="border rounded px-3 py-2 w-full md:w-1/2"
                                >
                                    <option value="">None - Skip AI review</option>
                                    {availableAgents.map(agent => (
                                        <option key={agent.agent_id} value={agent.agent_id}>
                                            {agent.name}
                                        </option>
                                    ))}
                                </select>
                                {selectedAgentInfo && (
                                    <div className="p-3 bg-purple-50 rounded border border-purple-200">
                                        <div className="font-medium text-purple-800">{selectedAgentInfo.name}</div>
                                        <div className="text-sm text-purple-700">{selectedAgentInfo.description}</div>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    {/* Title */}
                    <div className="bg-white rounded-lg shadow-sm p-6">
                        <h2 className="text-lg font-semibold text-gray-900 mb-4">
                            <i className="fa-solid fa-tag mr-2 text-blue-600"></i>
                            Audit Title
                        </h2>
                        <input
                            type="text"
                            value={titleSuffix}
                            onChange={e => setTitleSuffix(e.target.value)}
                            placeholder="e.g., Week of Jan 1-7, 2024"
                            className="border rounded px-3 py-2 w-full md:w-1/2"
                        />
                        <p className="text-sm text-gray-500 mt-2">
                            This will be appended to the audit session title
                        </p>
                    </div>

                    {/* Create Button */}
                    <div className="bg-white rounded-lg shadow-sm p-6">
                        <button
                            onClick={handleCreateAudit}
                            disabled={isRunning || !opportunityId}
                            className="inline-flex items-center px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 font-medium text-lg"
                        >
                            {isRunning ? (
                                <><i className="fa-solid fa-spinner fa-spin mr-2"></i>Creating...</>
                            ) : (
                                <><i className="fa-solid fa-play mr-2"></i>Create Audit{selectedAgent && ' with AI Review'}</>
                            )}
                        </button>
                        {!opportunityId && (
                            <p className="mt-2 text-sm text-red-600">
                                No opportunity selected. Add ?opportunity_id=XXX to the URL.
                            </p>
                        )}
                    </div>
                </>
            )}
        </div>
    );
}"""


# =============================================================================
# Template Registry
# =============================================================================

TEMPLATES = {
    "performance_review": {
        "name": "Weekly Performance Review",
        "description": "Review worker performance and mark as confirmed, needs audit, or create tasks",
        "icon": "fa-clipboard-check",
        "color": "green",
        "definition": PERFORMANCE_REVIEW_DEFINITION,
        "render_code": PERFORMANCE_REVIEW_RENDER_CODE,
        "pipeline_schema": PERFORMANCE_REVIEW_PIPELINE_SCHEMA,
    },
    "ocs_outreach": {
        "name": "OCS Bulk Outreach",
        "description": "Create tasks and initiate AI chatbot conversations for multiple workers",
        "icon": "fa-robot",
        "color": "orange",
        "definition": OCS_OUTREACH_DEFINITION,
        "render_code": OCS_OUTREACH_RENDER_CODE,
        "pipeline_schema": None,  # No pipeline for this template
    },
    "kmc_scale_validation": {
        "name": "KMC Scale Validation",
        "description": "Validate KMC weight readings against scale images using ML vision",
        "icon": "fa-scale-balanced",
        "color": "blue",
        "definition": KMC_SCALE_VALIDATION_DEFINITION,
        "render_code": KMC_SCALE_VALIDATION_RENDER_CODE,
        "pipeline_schema": KMC_SCALE_VALIDATION_PIPELINE_SCHEMA,
    },
    "audit_with_ai_review": {
        "name": "Audit with AI Review",
        "description": "Create audit sessions and run AI review agents to pre-validate images",
        "icon": "fa-clipboard-check",
        "color": "purple",
        "definition": AUDIT_WITH_AI_REVIEW_DEFINITION,
        "render_code": AUDIT_WITH_AI_REVIEW_RENDER_CODE,
        "pipeline_schema": None,  # No pipeline needed - uses audit creation API
    },
}


def get_template(template_key: str) -> dict | None:
    """
    Get a workflow template by key.

    Args:
        template_key: One of 'performance_review', 'ocs_outreach'

    Returns:
        Template dict with 'name', 'description', 'definition', 'render_code'
        or None if not found
    """
    return TEMPLATES.get(template_key)


def list_templates() -> list[dict]:
    """
    List all available templates.

    Returns:
        List of dicts with 'key', 'name', 'description', 'icon', 'color'
    """
    return [
        {
            "key": key,
            "name": t["name"],
            "description": t["description"],
            "icon": t.get("icon", "fa-cog"),
            "color": t.get("color", "gray"),
        }
        for key, t in TEMPLATES.items()
    ]


def create_workflow_from_template(data_access, template_key: str, request=None) -> tuple:
    """
    Create a workflow from a template using the data access layer.

    If the template includes a pipeline_schema, a pipeline will also be created
    and linked to the workflow.

    Args:
        data_access: WorkflowDataAccess instance with valid OAuth
        template_key: Template key (e.g., 'performance_review')
        request: Optional HttpRequest for creating pipelines (needed for PipelineDataAccess)

    Returns:
        Tuple of (definition_record, render_code_record, pipeline_record or None)

    Raises:
        ValueError: If template not found
    """
    template = get_template(template_key)
    if not template:
        raise ValueError(f"Unknown template: {template_key}")

    template_def = template["definition"]
    pipeline_schema = template.get("pipeline_schema")
    pipeline_record = None
    pipeline_sources = []

    # Create pipeline if template has one
    if pipeline_schema and request:
        from commcare_connect.workflow.data_access import PipelineDataAccess

        pipeline_data_access = PipelineDataAccess(request=request)
        pipeline_record = pipeline_data_access.create_definition(
            name=pipeline_schema["name"],
            description=pipeline_schema["description"],
            schema=pipeline_schema,
        )
        pipeline_data_access.close()

        # Determine alias based on template type
        alias_map = {
            "kmc_scale_validation": "visits",
            "performance_review": "performance_data",
        }
        pipeline_alias = alias_map.get(template_key, "data")

        # Add pipeline as a source with a default alias
        pipeline_sources = [
            {
                "pipeline_id": pipeline_record.id,
                "alias": pipeline_alias,
            }
        ]

    # Create the workflow definition with pipeline source if created
    definition = data_access.create_definition(
        name=template_def["name"],
        description=template_def["description"],
        statuses=template_def.get("statuses", []),
        config=template_def.get("config", {}),
        pipeline_sources=pipeline_sources,
    )

    # Create the render code
    render_code = data_access.save_render_code(
        definition_id=definition.id,
        component_code=template["render_code"],
        version=1,
    )

    return definition, render_code, pipeline_record
