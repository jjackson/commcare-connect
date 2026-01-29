"""
KMC Scale Validation Workflow Template.

Validate weight readings against scale images using ML vision for KMC visits.
"""

PIPELINE_SCHEMA = {
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

DEFINITION = {
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

RENDER_CODE = """function WorkflowUI({ definition, instance, workers, pipelines, links, actions, onUpdateState }) {
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
            setJobProgress({
                status: 'failed',
                error: 'No visits match the current filters. Adjust filters or wait for data to load.'
            });
            return;
        }

        setIsRunning(true);
        setJobProgress({
            status: 'running',
            current_stage: 1,
            total_stages: 1,
            stage_name: 'Validating',
            processed: 0,
            total: recordsToValidate.length
        });

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

        // Stop the progress stream first
        if (cleanupRef.current) {
            cleanupRef.current();
            cleanupRef.current = null;
        }

        // Always stop running state - user requested cancel
        setIsRunning(false);

        try {
            const result = await actions.cancelJob(taskId, instance.id);
            if (result.success) {
                setJobProgress({ status: 'cancelled' });
            } else {
                // Cancel API failed but we've already stopped the UI
                setJobProgress({
                    status: 'cancelled',
                    error: 'Cancelled (cleanup may have failed)'
                });
            }
        } catch (err) {
            setJobProgress({
                status: 'cancelled',
                error: 'Cancelled (error during cleanup)'
            });
        } finally {
            setIsCancelling(false);
        }
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

        const badgeClass = 'inline-flex items-center px-2 py-0.5 rounded text-xs font-medium';

        if (!result) {
            return <span className={badgeClass + ' bg-gray-100 text-gray-800'}>Pending</span>;
        }

        if (result.status === 'validated' && result.match) {
            return (
                <span className={badgeClass + ' bg-green-100 text-green-800'}>
                    <i className="fa-solid fa-check mr-1"></i>Match
                </span>
            );
        }
        if (result.status === 'validated' && !result.match) {
            return (
                <span className={badgeClass + ' bg-red-100 text-red-800'}>
                    <i className="fa-solid fa-xmark mr-1"></i>Mismatch
                </span>
            );
        }
        if (result.status === 'error') {
            return (
                <span className={badgeClass + ' bg-yellow-100 text-yellow-800'} title={result.error}>
                    <i className="fa-solid fa-exclamation-triangle mr-1"></i>Error
                </span>
            );
        }
        if (result.status === 'skipped') {
            return (
                <span className={badgeClass + ' bg-gray-100 text-gray-600'}>
                    <i className="fa-solid fa-forward mr-1"></i>Skipped
                </span>
            );
        }

        return <span className={badgeClass + ' bg-gray-100 text-gray-800'}>Unknown</span>;
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
                                className={'mt-4 inline-flex items-center px-4 py-2 ' +
                                    'bg-red-600 text-white rounded-lg hover:bg-red-700'}
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
                                className={'inline-flex items-center px-4 py-2 bg-blue-600 ' +
                                    'text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 font-medium'}
                            >
                                <i className="fa-solid fa-play mr-2"></i>
                                Run Validation ({displayVisits.length})
                            </button>
                        ) : (
                            <button
                                onClick={handleCancelJob}
                                disabled={isCancelling}
                                className={'inline-flex items-center px-4 py-2 bg-red-600 ' +
                                    'text-white rounded-lg hover:bg-red-700 disabled:bg-red-400 font-medium'}
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
                                <span className={'inline-flex items-center px-2.5 py-0.5 ' +
                                    'rounded-full text-xs font-medium bg-amber-100 text-amber-800'}>
                                    <i className="fa-solid fa-cog fa-spin mr-1.5"></i>Running
                                </span>
                            )}
                            {jobProgress.status === 'completed' && (
                                <span className={'inline-flex items-center px-2.5 py-0.5 ' +
                                    'rounded-full text-xs font-medium bg-green-100 text-green-800'}>
                                    <i className="fa-solid fa-check mr-1.5"></i>Completed
                                </span>
                            )}
                            {jobProgress.status === 'failed' && (
                                <span className={'inline-flex items-center px-2.5 py-0.5 ' +
                                    'rounded-full text-xs font-medium bg-red-100 text-red-800'}>
                                    <i className="fa-solid fa-xmark mr-1.5"></i>Failed
                                </span>
                            )}
                            {jobProgress.status === 'cancelled' && (
                                <span className={'inline-flex items-center px-2.5 py-0.5 ' +
                                    'rounded-full text-xs font-medium bg-gray-100 text-gray-600'}>
                                    <i className="fa-solid fa-ban mr-1.5"></i>Cancelled
                                </span>
                            )}
                            {jobProgress.total_stages > 1 && jobProgress.status === 'running' && (
                                <span className="text-sm text-gray-600">
                                    Stage {jobProgress.current_stage}/{jobProgress.total_stages}:
                                    {' '}{jobProgress.stage_name}
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
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                Child
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                Visit Date
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                Worker
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                Weight
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                Image
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                Validation
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                Actions
                            </th>
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
                                        <div className="font-medium text-gray-900">
                                            {visit.child_name || visit.entity_name || '-'}
                                        </div>
                                        <div className="text-xs text-gray-500">
                                            Visit #{visit.visit_number || '-'}
                                        </div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                                        {visit.visit_date
                                            ? new Date(visit.visit_date).toLocaleDateString()
                                            : '-'}
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
                                            <span className="text-green-600">
                                                <i className="fa-solid fa-image mr-1"></i>Yes
                                            </span>
                                        ) : (
                                            <span className="text-gray-400">
                                                <i className="fa-solid fa-image-slash mr-1"></i>No
                                            </span>
                                        )}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        {getStatusBadge(visit)}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        {isValidating ? (
                                            <span className={'inline-flex items-center px-2.5 py-1 ' +
                                                'text-xs font-medium text-blue-700'}>
                                                <i className="fa-solid fa-spinner fa-spin mr-1.5"></i>
                                                Validating...
                                            </span>
                                        ) : hasResult ? (
                                            <button
                                                onClick={() => handleValidateSingle(visit)}
                                                disabled={!canValidate}
                                                className={'inline-flex items-center px-2.5 py-1 text-xs ' +
                                                    'font-medium text-gray-600 hover:text-blue-600 ' +
                                                    'disabled:opacity-50 disabled:cursor-not-allowed'}
                                                title="Re-validate this visit"
                                            >
                                                <i className="fa-solid fa-rotate mr-1.5"></i>Re-validate
                                            </button>
                                        ) : (
                                            <button
                                                onClick={() => handleValidateSingle(visit)}
                                                disabled={!canValidate}
                                                className={'inline-flex items-center px-2.5 py-1 text-xs ' +
                                                    'font-medium text-blue-600 hover:text-blue-800 ' +
                                                    'disabled:opacity-50 disabled:cursor-not-allowed'}
                                                title={!canValidate
                                                    ? 'Missing image or weight data'
                                                    : 'Validate this visit'}
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

# Template export - this is what the registry imports
TEMPLATE = {
    "key": "kmc_scale_validation",
    "name": "KMC Scale Validation",
    "description": "Validate KMC weight readings against scale images using ML vision",
    "icon": "fa-scale-balanced",
    "color": "blue",
    "definition": DEFINITION,
    "render_code": RENDER_CODE,
    "pipeline_schema": PIPELINE_SCHEMA,
}
