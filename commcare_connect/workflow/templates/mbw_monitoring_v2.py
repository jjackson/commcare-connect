"""
MBW Monitoring V2 Workflow Template.

Pipeline-based version of the MBW monitoring dashboard. Uses 3 pipeline
sources (Connect visits, CCHQ registrations, CCHQ GS forms) and an
mbw_monitoring job handler for complex computations.

Replaces the custom_analysis SSE streaming approach in mbw_monitoring/.
"""

from commcare_connect.workflow.templates.mbw_monitoring.template import RENDER_CODE as V1_RENDER_CODE

# ---------------------------------------------------------------------------
# Build the V2 RENDER_CODE by surgically replacing the SSE data-loading layer
# in the V1 render code with pipeline + job handler logic.
#
# The v1 code loads data via EventSource (SSE) from a custom endpoint.
# The v2 code reads from the `pipelines` prop (auto-loaded by the workflow
# runner) and triggers `actions.startJob()` for complex computations.
#
# Everything else — tabs, modals, helpers, worker management — stays identical.
# ---------------------------------------------------------------------------

DEFINITION = {
    "name": "MBW Monitoring V2",
    "description": "Pipeline-based MBW monitoring with GPS analysis, follow-up rates, and FLW assessment",
    "version": 1,
    "templateType": "mbw_monitoring_v2",
    "statuses": [
        {"id": "in_progress", "label": "In Progress", "color": "blue"},
        {"id": "completed", "label": "Completed", "color": "green"},
    ],
    "config": {
        "showSummaryCards": False,
        "showFilters": False,
        "job_type": "mbw_monitoring",
    },
    "pipeline_sources": [],
}

# Pipeline schemas — these create pipeline definitions when the template is initialized
PIPELINE_SCHEMAS = [
    {
        "alias": "visits",
        "name": "MBW Visit Forms",
        "description": "Connect CSV visit data for MBW monitoring",
        "schema": {
            "data_source": {"type": "connect_csv"},
            "grouping_key": "username",
            "terminal_stage": "visit_level",
            "fields": [
                {"name": "gps_location", "path": "form.meta.location.#text", "aggregation": "first"},
                {"name": "case_id", "path": "form.case.@case_id", "aggregation": "first"},
                {"name": "mother_case_id", "path": "form.parents.parent.case.@case_id", "aggregation": "first"},
                {"name": "form_name", "path": "form.@name", "aggregation": "first"},
                {"name": "visit_datetime", "path": "form.meta.timeEnd", "aggregation": "first"},
                {
                    "name": "entity_id_deliver",
                    "paths": [
                        "form.mbw_visit.deliver.entity_id",
                        "form.visit_completion.mbw_visit.deliver.entity_id",
                    ],
                    "aggregation": "first",
                },
                {
                    "name": "entity_name",
                    "paths": [
                        "form.mbw_visit.deliver.entity_name",
                        "form.visit_completion.mbw_visit.deliver.entity_name",
                    ],
                    "aggregation": "first",
                },
                {
                    "name": "parity",
                    "path": "form.confirm_visit_information.parity__of_live_births_or_stillbirths_after_24_weeks",
                    "aggregation": "first",
                },
                {"name": "anc_completion_date", "path": "form.visit_completion.anc_completion_date", "aggregation": "first"},
                {"name": "pnc_completion_date", "path": "form.pnc_completion_date", "aggregation": "first"},
                {"name": "baby_dob", "path": "form.capture_the_following_birth_details.baby_dob", "aggregation": "first"},
                {
                    "name": "app_build_version",
                    "path": "form.meta.app_build_version",
                    "aggregation": "first",
                    "transform": "int",
                },
                {
                    "name": "bf_status",
                    "paths": [
                        "form.feeding_history.pnc_current_bf_status",
                        "form.feeding_history.oneweek_current_bf_status",
                        "form.feeding_history.onemonth_current_bf_status",
                        "form.feeding_history.threemonth_current_bf_status",
                        "form.feeding_history.sixmonth_current_bf_status",
                    ],
                    "aggregation": "first",
                },
            ],
        },
    },
    {
        "alias": "registrations",
        "name": "CCHQ Registration Forms",
        "description": "CCHQ registration forms for mother data",
        "schema": {
            "data_source": {
                "type": "cchq_forms",
                "form_name": "Register Mother",
                "app_id_source": "opportunity",
            },
            "grouping_key": "case_id",
            "terminal_stage": "visit_level",
            "fields": [
                {"name": "expected_visits", "path": "form.expected_visits", "aggregation": "first"},
                {"name": "mother_name", "path": "form.mother_name", "aggregation": "first"},
                {"name": "user_connect_id", "path": "form.user_connect_id", "aggregation": "first"},
            ],
        },
    },
    {
        "alias": "gs_forms",
        "name": "CCHQ Gold Standard Forms",
        "description": "CCHQ Gold Standard visit checklist forms",
        "schema": {
            "data_source": {
                "type": "cchq_forms",
                "form_name": "Gold Standard Visit Checklist",
                "app_id_source": "opportunity",
                "gs_app_id": "2ca67a89dd8a2209d75ed5599b45a5d1",
            },
            "grouping_key": "case_id",
            "terminal_stage": "visit_level",
            "fields": [
                {"name": "gs_score", "path": "form.gs_score", "aggregation": "first"},
                {"name": "assessor_name", "path": "form.assessor_name", "aggregation": "first"},
                {"name": "assessment_date", "path": "form.meta.timeEnd", "aggregation": "first"},
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Build the V2 RENDER_CODE via string replacement on V1_RENDER_CODE
# ---------------------------------------------------------------------------


def _replace_between(code: str, start_marker: str, end_marker: str, replacement: str) -> str:
    """Replace text between two markers (inclusive of start, exclusive of end)."""
    start = code.find(start_marker)
    end = code.find(end_marker, start + len(start_marker)) if start >= 0 else -1
    if start < 0 or end < 0:
        raise ValueError(f"Could not find markers: start={start_marker[:60]!r} end={end_marker[:60]!r}")
    return code[:start] + replacement + code[end:]


def _replace_between_inclusive(code: str, start_marker: str, end_marker: str, replacement: str) -> str:
    """Replace text between two markers (inclusive of both)."""
    start = code.find(start_marker)
    end = code.find(end_marker, start + len(start_marker)) if start >= 0 else -1
    if start < 0 or end < 0:
        raise ValueError(f"Could not find markers: start={start_marker[:60]!r} end={end_marker[:60]!r}")
    return code[:start] + replacement + code[end + len(end_marker) :]


def _build_v2_render_code() -> str:
    """Build the V2 render code by replacing SSE data loading with pipeline + job handler."""
    code = V1_RENDER_CODE

    # =====================================================================
    # 1. Replace SSE state variables with pipeline/job state variables
    # =====================================================================
    _SSE_STATE = """    var [dashData, setDashData] = React.useState(null);
    var [sseMessages, setSseMessages] = React.useState([]);
    var [sseError, setSseError] = React.useState(null);
    var [sseAuthorizeUrl, setSseAuthorizeUrl] = React.useState(null);
    var [sseComplete, setSseComplete] = React.useState(false);
    var [fromSnapshot, setFromSnapshot] = React.useState(false);
    var [snapshotTimestamp, setSnapshotTimestamp] = React.useState(null);
    var [refreshTrigger, setRefreshTrigger] = React.useState(0);
    var [oauthStatus, setOauthStatus] = React.useState(null);"""

    _PIPELINE_STATE = """    var [dashData, setDashData] = React.useState(null);
    var [jobMessages, setJobMessages] = React.useState([]);
    var [jobError, setJobError] = React.useState(null);
    var [jobRunning, setJobRunning] = React.useState(false);
    var [analysisComplete, setAnalysisComplete] = React.useState(false);
    var [oauthStatus, setOauthStatus] = React.useState(null);
    var jobCleanupRef = React.useRef(null);"""

    code = code.replace(_SSE_STATE, _PIPELINE_STATE)

    # =====================================================================
    # 2. Replace SSE loading useEffect with pipeline-aware job trigger
    # =====================================================================
    _SSE_LOADING = """    // =========================================================================
    // SSE: Load dashboard data (with snapshot-first loading)
    // =========================================================================
    var sseCleanupRef = React.useRef(null);

    React.useEffect(function() {
        if (step !== 'dashboard') return;
        var flws = instance.state?.selected_workers || instance.state?.selected_flws || [];
        if (flws.length === 0) return;

        setSseComplete(false);
        setSseError(null);
        setSseAuthorizeUrl(null);
        setSseMessages([]);
        setFromSnapshot(false);
        setSnapshotTimestamp(null);

        function startSSEStream(bustCache) {
            var end = new Date();
            var start = new Date();
            start.setDate(end.getDate() - 30);
            var startStr = start.toISOString().split('T')[0];
            var endStr = end.toISOString().split('T')[0];

            var params = new URLSearchParams({
                run_id: String(instance.id),
                start_date: startStr,
                end_date: endStr
            });
            if (bustCache) {
                params.set('bust_cache', '1');
            }
            if (appliedAppVersionOp && appliedAppVersionVal) {
                params.set('app_version_op', appliedAppVersionOp);
                params.set('app_version_val', appliedAppVersionVal);
            }
            var url = '/custom_analysis/mbw_monitoring/stream/?' + params.toString();
            var es = new EventSource(url);

            es.onmessage = function(event) {
                try {
                    var parsed = JSON.parse(event.data);
                    if (parsed.error) {
                        setSseError(parsed.error);
                        if (parsed.authorize_url) {
                            setSseAuthorizeUrl(parsed.authorize_url);
                        }
                        es.close();
                        return;
                    }
                    if (parsed.message === 'Complete!' && parsed.data) {
                        setDashData(parsed.data);
                        setSseComplete(true);
                        setFromSnapshot(false);
                        setSnapshotTimestamp(null);
                        if (parsed.data.monitoring_session?.flw_results) {
                            setWorkerResults(parsed.data.monitoring_session.flw_results);
                        }
                        es.close();
                    } else if (parsed.message) {
                        setSseMessages(function(prev) { return prev.concat([parsed.message]); });
                    }
                } catch (e) {
                    console.error('SSE parse error:', e);
                }
            };

            es.onerror = function() {
                if (!sseComplete) {
                    setSseError('Connection lost. Please refresh the page.');
                }
                es.close();
            };

            sseCleanupRef.current = function() { es.close(); };
        }

        // Check OAuth status before starting SSE stream
        function checkOAuthAndStream(bustCache) {
            setOauthStatus(null);
            setSseMessages(['Checking authentication...']);
            fetch('/custom_analysis/mbw_monitoring/api/oauth-status/?next=' + encodeURIComponent(window.location.pathname + window.location.search))
            .then(function(r) { return r.json(); })
            .then(function(status) {
                var expired = [];
                if (!status.connect?.active) expired.push('connect');
                if (!status.commcare?.active) expired.push('commcare');
                if (!status.ocs?.active) expired.push('ocs');
                // Always store OAuth status (used by inline task OCS check)
                setOauthStatus(status);
                // Connect + CommCare are required; OCS is optional
                if (!status.connect?.active || !status.commcare?.active) {
                    setSseMessages([]);
                    return;
                }
                startSSEStream(bustCache);
            })
            .catch(function() {
                // Network error checking OAuth — proceed anyway, SSE will fail with its own error
                startSSEStream(bustCache);
            });
        }

        // refreshTrigger=0 means initial load → try snapshot first
        // refreshTrigger>0 means user clicked Refresh Data → SSE with bust_cache
        if (refreshTrigger === 0 && instance.id) {
            fetch('/custom_analysis/mbw_monitoring/api/snapshot/?run_id=' + instance.id)
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.has_snapshot && data.success) {
                    setDashData(data);
                    setSseComplete(true);
                    setFromSnapshot(true);
                    setSnapshotTimestamp(data.snapshot_timestamp);
                    if (data.monitoring_session?.flw_results) {
                        setWorkerResults(data.monitoring_session.flw_results);
                    }
                    return;
                }
                checkOAuthAndStream(false);
            })
            .catch(function() { checkOAuthAndStream(false); });
        } else {
            checkOAuthAndStream(refreshTrigger > 0);
        }

        return function() {
            if (sseCleanupRef.current) sseCleanupRef.current();
        };
    }, [step, instance.id, refreshTrigger]);"""

    _PIPELINE_LOADING = """    // =========================================================================
    // OAuth: Check auth status on dashboard load
    // =========================================================================
    React.useEffect(function() {
        if (step !== 'dashboard') return;
        fetch('/custom_analysis/mbw_monitoring/api/oauth-status/?next=' + encodeURIComponent(window.location.pathname + window.location.search))
        .then(function(r) { return r.json(); })
        .then(function(status) {
            setOauthStatus(status);
        })
        .catch(function() {
            // Network error — leave oauthStatus null so UI doesn't block
        });
    }, [step]);

    // =========================================================================
    // Pipeline + Job: Detect loaded pipeline data and run analysis via job handler
    // =========================================================================

    // Helper: check if pipelines are ready (visits must have data; others just need to exist)
    var pipelinesReady = pipelines
        && pipelines.visits && pipelines.visits.rows && pipelines.visits.rows.length > 0
        && ['registrations', 'gs_forms'].every(function(key) {
            return !pipelines[key] || (pipelines[key].rows !== undefined);
        });

    var pipelinesPartial = pipelines && (
        (pipelines.visits && pipelines.visits.rows && pipelines.visits.rows.length > 0)
        || (pipelines.registrations && pipelines.registrations.rows && pipelines.registrations.rows.length > 0)
        || (pipelines.gs_forms && pipelines.gs_forms.rows && pipelines.gs_forms.rows.length > 0)
    );

    // Build FLW names from workers prop
    var flwNameMap = React.useMemo(function() {
        var m = {};
        (workers || []).forEach(function(w) {
            if (w.username) m[w.username.toLowerCase()] = w.name || w.username;
        });
        return m;
    }, [workers]);

    // Run analysis job when pipelines are ready
    var runAnalysis = React.useCallback(function() {
        if (!pipelinesReady || !actions || !actions.startJob) return;
        if (jobRunning) return;

        var sessionFlwsList = instance.state?.selected_workers || instance.state?.selected_flws || [];

        setJobRunning(true);
        setJobError(null);
        setJobMessages(['Starting analysis...']);
        setDashData(null);
        setAnalysisComplete(false);

        actions.startJob(instance.id, {
            job_type: 'mbw_monitoring',
            pipeline_data: {
                visits: { rows: pipelines.visits.rows },
                registrations: { rows: pipelines.registrations.rows },
                gs_forms: { rows: pipelines.gs_forms.rows },
            },
            active_usernames: sessionFlwsList,
            flw_names: flwNameMap,
            flw_statuses: instance.state?.flw_statuses || {},
            opportunity_id: instance.opportunity_id,
        }).then(function(resp) {
            if (!resp || !resp.success) {
                setJobRunning(false);
                setJobError(resp?.error || 'Failed to start analysis job');
                return;
            }
            var taskId = resp.task_id;
            if (!taskId) {
                setJobRunning(false);
                setJobError('No task ID returned from job');
                return;
            }

            setJobMessages(function(prev) { return prev.concat(['Job started (task: ' + taskId + ')']); });

            // Stream job progress
            var cleanup = actions.streamJobProgress(
                taskId,
                // onProgress
                function(data) {
                    if (data.message) {
                        setJobMessages(function(prev) { return prev.concat([data.message]); });
                    }
                },
                // onItemResult
                function(item) {
                    // Individual item results (not used for MBW monitoring)
                },
                // onComplete
                function(results) {
                    setJobRunning(false);
                    setAnalysisComplete(true);

                    // Build dashData in the shape the tabs expect
                    var gpsData = results.gps_data || {};
                    var followupData = results.followup_data || {};
                    var qualityMetrics = results.quality_metrics || {};
                    var overviewSummary = results.overview_data || {};
                    var performanceData = results.performance_data || [];

                    // Build overview flw_summaries by merging data from multiple result sections
                    var activeUsernamesList = instance.state?.selected_workers || instance.state?.selected_flws || [];
                    var overviewFlwSummaries = activeUsernamesList.map(function(username) {
                        var uLower = username.toLowerCase();
                        var displayName = flwNameMap[uLower] || username;

                        // From GPS data
                        var gpsFlw = (gpsData.flw_summaries || []).find(function(g) { return g.username === uLower; }) || {};
                        var medianMeters = (gpsData.median_meters_by_flw || {})[uLower];
                        var medianMinutes = (gpsData.median_minutes_by_flw || {})[uLower];

                        // From follow-up data
                        var fuFlw = (followupData.flw_summaries || []).find(function(f) { return f.username === uLower; }) || {};

                        // From quality metrics
                        var quality = qualityMetrics[uLower] || {};

                        // From overview summary
                        var motherCount = (overviewSummary.mother_counts || {})[uLower] || 0;
                        var ebfPct = (overviewSummary.ebf_pct_by_flw || {})[uLower];

                        // Build cases_still_eligible from drilldown
                        var drilldown = (followupData.flw_drilldown || {})[uLower] || [];
                        var eligibleMothers = drilldown.filter(function(m) { return m.eligible; });
                        var stillOnTrack = 0;
                        eligibleMothers.forEach(function(m) {
                            var completedCount = 0;
                            var missedCount = 0;
                            (m.visits || []).forEach(function(v) {
                                if (v.status && v.status.indexOf('Completed') === 0) completedCount++;
                                if (v.status === 'Missed') missedCount++;
                            });
                            if (completedCount >= 5 || missedCount <= 1) stillOnTrack++;
                        });
                        var totalEligible = eligibleMothers.length;

                        return Object.assign({
                            username: uLower,
                            display_name: displayName,
                            cases_registered: motherCount,
                            eligible_mothers: totalEligible,
                            first_gs_score: null,  // populated below from gs_forms pipeline
                            post_test_attempts: null,
                            followup_rate: fuFlw.completion_rate || 0,
                            ebf_pct: ebfPct != null ? ebfPct : null,
                            revisit_distance_km: gpsFlw.avg_case_distance_km != null ? Math.round(gpsFlw.avg_case_distance_km * 100) / 100 : null,
                            median_meters_per_visit: medianMeters != null ? medianMeters : null,
                            median_minutes_per_visit: medianMinutes != null ? medianMinutes : null,
                            cases_still_eligible: {
                                eligible: stillOnTrack,
                                total: totalEligible,
                                pct: totalEligible > 0 ? Math.round(stillOnTrack / totalEligible * 100) : 0,
                            },
                        }, quality);
                    });

                    // Enrich with GS scores from gs_forms pipeline data
                    var gsFormRows = (pipelines.gs_forms && pipelines.gs_forms.rows) || [];
                    var gsByFlw = {};
                    gsFormRows.forEach(function(row) {
                        var connectId = (row.computed || row).user_connect_id || row.username || '';
                        var uLower = connectId.toLowerCase();
                        var score = parseFloat((row.computed || row).gs_score);
                        if (!isNaN(score)) {
                            if (!gsByFlw[uLower]) gsByFlw[uLower] = [];
                            gsByFlw[uLower].push({ score: score, date: (row.computed || row).assessment_date || '' });
                        }
                    });
                    overviewFlwSummaries.forEach(function(flw) {
                        var gsEntries = gsByFlw[flw.username] || [];
                        if (gsEntries.length > 0) {
                            // Use the oldest (first) GS score
                            gsEntries.sort(function(a, b) { return (a.date || '').localeCompare(b.date || ''); });
                            flw.first_gs_score = Math.round(gsEntries[0].score);
                        }
                    });

                    var builtDashData = {
                        success: true,
                        gps_data: gpsData,
                        followup_data: followupData,
                        overview_data: {
                            flw_summaries: overviewFlwSummaries,
                            visit_status_distribution: followupData.visit_status_distribution || {},
                        },
                        performance_data: performanceData,
                        active_usernames: activeUsernamesList.map(function(u) { return u.toLowerCase(); }).sort(),
                        flw_names: flwNameMap,
                        open_tasks: instance.state?.open_tasks || {},
                        open_task_usernames: Object.keys(instance.state?.open_tasks || {}),
                        monitoring_session: instance.state?.monitoring_session || null,
                    };

                    setDashData(builtDashData);

                    // Restore worker results from monitoring session if available
                    if (builtDashData.monitoring_session?.flw_results) {
                        setWorkerResults(builtDashData.monitoring_session.flw_results);
                    }
                },
                // onError
                function(error) {
                    setJobRunning(false);
                    setJobError(error || 'Analysis job failed');
                },
                // onCancelled
                function() {
                    setJobRunning(false);
                    setJobError('Analysis job was cancelled');
                }
            );

            jobCleanupRef.current = cleanup;
        }).catch(function(err) {
            setJobRunning(false);
            setJobError('Failed to start job: ' + (err.message || err));
        });
    }, [pipelinesReady, jobRunning, instance.id, instance.state, pipelines, flwNameMap, actions]);

    // Cleanup job stream on unmount
    React.useEffect(function() {
        return function() {
            if (jobCleanupRef.current) jobCleanupRef.current();
        };
    }, []);"""

    code = code.replace(_SSE_LOADING, _PIPELINE_LOADING)

    # =====================================================================
    # 3. Replace sticky header dependency on sseComplete with analysisComplete
    # =====================================================================
    code = code.replace(
        "}, [activeTab, sseComplete]);",
        "}, [activeTab, analysisComplete]);"
    )

    # =====================================================================
    # 4. OAuth expired state check — KEPT in v2 (pipelines need auth too)
    # =====================================================================
    # No changes needed — the v1 OAuth expired state block is preserved as-is.

    # =====================================================================
    # 5. Replace Loading state with pipeline/job loading UI
    # =====================================================================
    _SSE_LOADING_UI = """    // ---- Loading state ----
    if (!sseComplete && !sseError) {
        return (
            <div className="space-y-4">
                <div className="bg-white rounded-lg shadow-sm p-6">
                    <h2 className="text-xl font-bold text-gray-900">{instance.state?.title || 'MBW Monitoring'}</h2>
                    <p className="text-gray-500 mt-1">Loading dashboard data...</p>
                </div>
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                    <div className="flex items-center gap-3 mb-3">
                        <div className="animate-spin h-5 w-5 border-2 border-blue-600 border-t-transparent rounded-full"></div>
                        <span className="font-medium text-blue-800">Loading data via SSE...</span>
                    </div>
                    <div className="space-y-1 text-sm text-blue-700 max-h-40 overflow-y-auto">
                        {sseMessages.map(function(msg, i) {
                            return <div key={i}>{msg}</div>;
                        })}
                    </div>
                </div>
            </div>
        );
    }

    // ---- Error state ----
    if (sseError) {
        return (
            <div className="space-y-4">
                <div className="bg-white rounded-lg shadow-sm p-6">
                    <h2 className="text-xl font-bold text-gray-900">{instance.state?.title || 'MBW Monitoring'}</h2>
                </div>
                <div className={sseAuthorizeUrl ? "bg-amber-50 border border-amber-300 rounded-lg p-4" : "bg-red-50 border border-red-200 rounded-lg p-4"}>
                    <div className={"flex items-center gap-2 " + (sseAuthorizeUrl ? "text-amber-800" : "text-red-800")}>
                        <i className={"fa-solid " + (sseAuthorizeUrl ? "fa-link-slash" : "fa-circle-exclamation")}></i>
                        <span className="font-medium">{sseError}</span>
                    </div>
                    <div className="mt-3 flex gap-2">
                        {sseAuthorizeUrl ? (
                            <a href={sseAuthorizeUrl}
                               className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 inline-block no-underline">
                                <i className="fa-solid fa-arrow-right-to-bracket mr-1"></i> Authorize CommCare
                            </a>
                        ) : (
                            <button onClick={function() { window.location.reload(); }}
                                    className="px-4 py-2 bg-red-600 text-white rounded text-sm hover:bg-red-700">
                                Retry
                            </button>
                        )}
                    </div>
                </div>
            </div>
        );
    }"""

    _PIPELINE_LOADING_UI = """    // ---- Pipeline loading / Job running / Error state ----
    if (!analysisComplete || !dashData) {
        var visitCount = (pipelines && pipelines.visits && pipelines.visits.rows) ? pipelines.visits.rows.length : 0;
        var regCount = (pipelines && pipelines.registrations && pipelines.registrations.rows) ? pipelines.registrations.rows.length : 0;
        var gsCount = (pipelines && pipelines.gs_forms && pipelines.gs_forms.rows) ? pipelines.gs_forms.rows.length : 0;

        return (
            <div className="space-y-4">
                <div className="bg-white rounded-lg shadow-sm p-6">
                    <h2 className="text-xl font-bold text-gray-900">{instance.state?.title || 'MBW Monitoring V2'}</h2>
                    <p className="text-gray-500 mt-1">Pipeline-based dashboard</p>
                </div>

                {/* Pipeline Status */}
                <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
                    <h3 className="text-sm font-semibold text-gray-700 mb-3">Pipeline Data Sources</h3>
                    <div className="space-y-2">
                        <div className="flex items-center gap-3">
                            <i className={'fa-solid ' + (visitCount > 0 ? 'fa-circle-check text-green-500' : 'fa-spinner fa-spin text-blue-500')}></i>
                            <span className="text-sm text-gray-700">Visit Forms</span>
                            <span className="text-xs text-gray-500 ml-auto">{visitCount > 0 ? visitCount + ' rows' : 'Loading...'}</span>
                        </div>
                        <div className="flex items-center gap-3">
                            <i className={'fa-solid ' + (regCount > 0 ? 'fa-circle-check text-green-500' : (pipelines && pipelines.registrations && pipelines.registrations.rows ? 'fa-circle-check text-amber-500' : 'fa-spinner fa-spin text-blue-500'))}></i>
                            <span className="text-sm text-gray-700">Registration Forms</span>
                            <span className="text-xs text-gray-500 ml-auto">{regCount > 0 ? regCount + ' rows' : (pipelines && pipelines.registrations && pipelines.registrations.rows ? '0 rows (none found)' : 'Loading...')}</span>
                        </div>
                        <div className="flex items-center gap-3">
                            <i className={'fa-solid ' + (gsCount > 0 ? 'fa-circle-check text-green-500' : (pipelines && pipelines.gs_forms && pipelines.gs_forms.rows ? 'fa-circle-check text-amber-500' : 'fa-spinner fa-spin text-blue-500'))}></i>
                            <span className="text-sm text-gray-700">Gold Standard Forms</span>
                            <span className="text-xs text-gray-500 ml-auto">{gsCount > 0 ? gsCount + ' rows' : (pipelines && pipelines.gs_forms && pipelines.gs_forms.rows ? '0 rows (none found)' : 'Loading...')}</span>
                        </div>
                    </div>
                </div>

                {/* Error State */}
                {jobError && (
                    <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                        <div className="flex items-center gap-2 text-red-800">
                            <i className="fa-solid fa-circle-exclamation"></i>
                            <span className="font-medium">{jobError}</span>
                        </div>
                        <div className="mt-3">
                            <button onClick={function() { setJobError(null); runAnalysis(); }}
                                    disabled={!pipelinesReady}
                                    className="px-4 py-2 bg-red-600 text-white rounded text-sm hover:bg-red-700 disabled:opacity-50">
                                Retry Analysis
                            </button>
                        </div>
                    </div>
                )}

                {/* Job Running State */}
                {jobRunning && (
                    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                        <div className="flex items-center gap-3 mb-3">
                            <div className="animate-spin h-5 w-5 border-2 border-blue-600 border-t-transparent rounded-full"></div>
                            <span className="font-medium text-blue-800">Running analysis...</span>
                        </div>
                        <div className="space-y-1 text-sm text-blue-700 max-h-40 overflow-y-auto">
                            {jobMessages.map(function(msg, i) {
                                return <div key={i}>{msg}</div>;
                            })}
                        </div>
                    </div>
                )}

                {/* Run Analysis Button */}
                {!jobRunning && !jobError && pipelinesReady && (
                    <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <span className="font-medium text-green-800">All pipelines loaded</span>
                                <p className="text-sm text-green-600 mt-1">
                                    {visitCount} visits, {regCount} registrations, {gsCount} GS forms loaded.
                                </p>
                            </div>
                            <button onClick={runAnalysis}
                                    className="px-6 py-2.5 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700 shadow-sm">
                                <i className="fa-solid fa-play mr-2"></i> Run Analysis
                            </button>
                        </div>
                    </div>
                )}

                {/* Waiting for pipelines */}
                {!jobRunning && !jobError && !pipelinesReady && pipelinesPartial && (
                    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                        <div className="flex items-center gap-3">
                            <div className="animate-spin h-5 w-5 border-2 border-blue-600 border-t-transparent rounded-full"></div>
                            <span className="font-medium text-blue-800">Waiting for all pipeline data to load...</span>
                        </div>
                    </div>
                )}

                {!jobRunning && !jobError && !pipelinesPartial && (
                    <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                        <div className="flex items-center gap-3">
                            <div className="animate-spin h-5 w-5 border-2 border-gray-400 border-t-transparent rounded-full"></div>
                            <span className="font-medium text-gray-600">Initializing pipeline data sources...</span>
                        </div>
                    </div>
                )}
            </div>
        );
    }"""

    code = code.replace(_SSE_LOADING_UI, _PIPELINE_LOADING_UI)

    # =====================================================================
    # 6. Replace the "Refresh Data" button behavior and snapshot indicator
    # =====================================================================
    # Replace the snapshot/refresh button in the tab bar
    code = code.replace(
        """                <div className="flex items-center gap-3 ml-auto">
                    {fromSnapshot && snapshotTimestamp && (
                        <div className="flex items-center gap-2 text-sm text-gray-500">
                            <span>Data from: {new Date(snapshotTimestamp).toLocaleString()}</span>
                            <span className="text-amber-600 text-xs font-medium">(snapshot)</span>
                        </div>
                    )}
                    <button onClick={function() {
                        setRefreshTrigger(function(n) { return n + 1; });
                        setDashData(null);
                        setSseComplete(false);
                    }} disabled={!sseComplete}
                    className={'inline-flex items-center gap-1 px-3 py-1.5 text-sm font-medium rounded-md border transition-colors ' +
                        (sseComplete
                            ? 'text-blue-700 bg-blue-50 border-blue-200 hover:bg-blue-100'
                            : 'text-gray-400 bg-gray-50 border-gray-200 cursor-not-allowed')}>
                        {'\\u21BB'} Refresh Data
                    </button>
                </div>""",
        """                <div className="flex items-center gap-3 ml-auto">
                    <button onClick={function() {
                        setDashData(null);
                        setAnalysisComplete(false);
                        setJobMessages([]);
                        setJobError(null);
                    }} disabled={jobRunning}
                    className={'inline-flex items-center gap-1 px-3 py-1.5 text-sm font-medium rounded-md border transition-colors ' +
                        (analysisComplete && !jobRunning
                            ? 'text-blue-700 bg-blue-50 border-blue-200 hover:bg-blue-100'
                            : 'text-gray-400 bg-gray-50 border-gray-200 cursor-not-allowed')}>
                        {'\\u21BB'} Re-run Analysis
                    </button>
                </div>"""
    )

    # =====================================================================
    # 7. Replace resetFilters references to SSE state
    # =====================================================================
    code = code.replace(
        """    var resetFilters = function() {
        setFilterFlws([]);
        setFilterMothers([]);
        var needsRefresh = appliedAppVersionOp !== 'gt' || appliedAppVersionVal !== '14';
        setAppVersionOp('gt');
        setAppVersionVal('14');
        setAppliedAppVersionOp('gt');
        setAppliedAppVersionVal('14');
        if (needsRefresh) {
            setRefreshTrigger(function(n) { return n + 1; });
            setDashData(null);
            setSseComplete(false);
        }
    };""",
        """    var resetFilters = function() {
        setFilterFlws([]);
        setFilterMothers([]);
        setAppVersionOp('gt');
        setAppVersionVal('14');
        setAppliedAppVersionOp('gt');
        setAppliedAppVersionVal('14');
    };"""
    )

    # =====================================================================
    # 8. Replace the App Version Apply button that referenced SSE state
    # =====================================================================
    code = code.replace(
        """                    <button onClick={function() {
                                var opChanged = appVersionOp !== appliedAppVersionOp;
                                var valChanged = appVersionVal !== appliedAppVersionVal;
                                if (opChanged || valChanged) {
                                    setAppliedAppVersionOp(appVersionOp);
                                    setAppliedAppVersionVal(appVersionVal);
                                    setRefreshTrigger(function(n) { return n + 1; });
                                    setDashData(null);
                                    setSseComplete(false);
                                }
                            }}
                            className="inline-flex items-center px-4 py-1.5 text-sm text-white bg-blue-600 rounded-md hover:bg-blue-700">
                        <i className="fa-solid fa-filter mr-1"></i> Apply
                    </button>""",
        """                    <button onClick={function() {
                                setAppliedAppVersionOp(appVersionOp);
                                setAppliedAppVersionVal(appVersionVal);
                            }}
                            className="inline-flex items-center px-4 py-1.5 text-sm text-white bg-blue-600 rounded-md hover:bg-blue-700">
                        <i className="fa-solid fa-filter mr-1"></i> Apply
                    </button>"""
    )

    # =====================================================================
    # 9. Replace "from_cache" indicator with pipeline-based indicator
    # =====================================================================
    code = code.replace(
        """                {dashData?.from_cache && (
                    <div className="mt-2 text-xs text-gray-400">Data loaded from cache</div>
                )}""",
        """                {dashData && (
                    <div className="mt-2 text-xs text-gray-400">Data loaded via pipeline analysis</div>
                )}"""
    )

    # =====================================================================
    # 10. Replace visit_status_distribution path for v2 data shape
    # =====================================================================
    # In v1: dashData?.overview_data?.visit_status_distribution
    # In v2: same path — we already build it there in the onComplete handler
    # No change needed here.

    # =====================================================================
    # 11. Additional cleanup: replace remaining SSE references
    # =====================================================================
    # The tab bar refresh button and snapshot indicator may have Unicode
    # chars that made exact string matching fail. Use marker-based replacement.

    # Replace the tab bar right section (snapshot indicator + refresh button)
    code = _replace_between(
        code,
        '                <div className="flex items-center gap-3 ml-auto">',
        "                </div>\n            </div>\n\n            {/* Filter Bar */}",
        '                <div className="flex items-center gap-3 ml-auto">\n'
        "                    <button onClick={function() {\n"
        "                        setDashData(null);\n"
        "                        setAnalysisComplete(false);\n"
        "                        setJobMessages([]);\n"
        "                        setJobError(null);\n"
        "                    }} disabled={jobRunning}\n"
        "                    className={'inline-flex items-center gap-1 px-3 py-1.5 text-sm"
        " font-medium rounded-md border transition-colors ' +\n"
        "                        (analysisComplete && !jobRunning\n"
        "                            ? 'text-blue-700 bg-blue-50 border-blue-200 hover:bg-blue-100'\n"
        "                            : 'text-gray-400 bg-gray-50 border-gray-200 cursor-not-allowed')}>\n"
        "                        {'\\u21BB'} Re-run Analysis\n"
        "                    </button>\n",
    )

    # OCS OAuth check — KEPT in v2 (uses oauthStatus, same as v1)

    # Replace fromSnapshot reference in follow-up drilldown
    code = code.replace("fromSnapshot ? ", "false ? ")

    # Replace the from_cache indicator
    code = code.replace(
        "{dashData?.from_cache && (",
        "{dashData && (",
    )
    code = code.replace(
        "Data loaded from cache",
        "Data loaded via pipeline analysis",
    )

    # Replace OAuth Retry button to reload page (no refreshTrigger in v2)
    code = code.replace(
        "setRefreshTrigger(function(c) { return c + 1; });",
        "window.location.reload();",
    )

    # Replace App Version Apply button SSE references
    code = code.replace(
        "setRefreshTrigger(function(n) { return n + 1; });\n"
        "                                    setDashData(null);\n"
        "                                    setSseComplete(false);",
        "// App version filter applied (no SSE refresh needed in v2)",
    )

    # =====================================================================
    # 12. Final safety check: ensure no SSE state refs remain
    # =====================================================================
    _sse_terms = [
        "sseComplete",
        "sseError",
        "sseMessages",
        "sseAuthorizeUrl",
        "fromSnapshot",
        "snapshotTimestamp",
        "refreshTrigger",
        "setSseComplete",
        "setSseError",
        "setSseMessages",
        "setSseAuthorizeUrl",
        "setFromSnapshot",
        "setSnapshotTimestamp",
        "setRefreshTrigger",
        "EventSource",
    ]
    for term in _sse_terms:
        if term in code:
            import logging

            logging.getLogger(__name__).warning(
                "MBW V2 render code still contains SSE reference: %s", term
            )

    return code


RENDER_CODE = _build_v2_render_code()

TEMPLATE = {
    "key": "mbw_monitoring_v2",
    "name": "MBW Monitoring V2",
    "description": "Pipeline-based MBW monitoring with GPS analysis, follow-up rates, and FLW assessment",
    "icon": "fa-baby",
    "color": "pink",
    "definition": DEFINITION,
    "render_code": RENDER_CODE,
    "pipeline_schemas": PIPELINE_SCHEMAS,
}
