"""
MBW Monitoring Workflow Template.

Select FLWs for monitoring and launch a full in-page dashboard with three tabs:
  - Overview (metrics table + FLW assessment)
  - GPS Analysis (visit GPS metrics per FLW)
  - Follow-Up Rate (visit completion tracking per FLW and per-mother)

FLW assessment uses three options: eligible_for_renewal / probation / suspended.
Data is loaded via SSE from the backend streaming endpoint.
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
    // =========================================================================
    // State key migration helpers
    // =========================================================================
    var savedWorkers = instance.state?.selected_workers || instance.state?.selected_flws || [];
    var savedResults = instance.state?.worker_results || instance.state?.flw_results || {};

    // =========================================================================
    // Step management: 'select' or 'dashboard'
    // =========================================================================
    var [step, setStep] = React.useState(savedWorkers.length > 0 ? 'dashboard' : 'select');

    // =========================================================================
    // STEP 1: FLW Selection State
    // =========================================================================
    var [selectedFlws, setSelectedFlws] = React.useState({});
    var [flwHistory, setFlwHistory] = React.useState({});
    var [historyLoading, setHistoryLoading] = React.useState(false);
    var [title, setTitle] = React.useState('');
    var [tag, setTag] = React.useState('');
    var [gsAppId, setGsAppId] = React.useState(instance.state?.gs_app_id || '2ca67a89dd8a2209d75ed5599b45a5d1');
    var [launching, setLaunching] = React.useState(false);
    var [selSearch, setSelSearch] = React.useState('');
    var [selSort, setSelSort] = React.useState({ col: 'name', dir: 'asc' });

    // =========================================================================
    // STEP 2: Dashboard State
    // =========================================================================
    var [dashData, setDashData] = React.useState(null);
    var [sseMessages, setSseMessages] = React.useState([]);
    var [sseError, setSseError] = React.useState(null);
    var [sseAuthorizeUrl, setSseAuthorizeUrl] = React.useState(null);
    var [sseComplete, setSseComplete] = React.useState(false);
    var [fromSnapshot, setFromSnapshot] = React.useState(false);
    var [snapshotTimestamp, setSnapshotTimestamp] = React.useState(null);
    var [refreshTrigger, setRefreshTrigger] = React.useState(0);
    var [oauthStatus, setOauthStatus] = React.useState(null);
    var [activeTab, setActiveTab] = React.useState('overview');
    var [overviewSearch, setOverviewSearch] = React.useState('');
    var [overviewSort, setOverviewSort] = React.useState({ col: 'display_name', dir: 'asc' });
    var [gpsSort, setGpsSort] = React.useState({ col: 'username', dir: 'asc' });
    var [fuSort, setFuSort] = React.useState({ col: 'username', dir: 'asc' });
    var [expandedGps, setExpandedGps] = React.useState(null);
    var [gpsDetail, setGpsDetail] = React.useState(null);
    var [gpsDetailLoading, setGpsDetailLoading] = React.useState(false);
    var [expandedFu, setExpandedFu] = React.useState(null);
    var [showCompleteModal, setShowCompleteModal] = React.useState(false);
    var [completeNotes, setCompleteNotes] = React.useState('');
    var [completing, setCompleting] = React.useState(false);
    var [workerResults, setWorkerResults] = React.useState(savedResults);
    var [savingResult, setSavingResult] = React.useState(null);

    // Additional state for filters, notes modal, toast
    var [filterFlws, setFilterFlws] = React.useState([]);
    var [filterMothers, setFilterMothers] = React.useState([]);
    var [showAllVisits, setShowAllVisits] = React.useState(false);
    var [showEligibleOnly, setShowEligibleOnly] = React.useState(true);
    var [showFlwNotesModal, setShowFlwNotesModal] = React.useState(false);
    var [flwNotesUsername, setFlwNotesUsername] = React.useState('');
    var [flwNotesText, setFlwNotesText] = React.useState('');
    var [flwNotesResult, setFlwNotesResult] = React.useState(null);
    var [toastMessage, setToastMessage] = React.useState('');
    var [filterStartDate, setFilterStartDate] = React.useState('');
    var [filterEndDate, setFilterEndDate] = React.useState('');
    var [appVersionOp, setAppVersionOp] = React.useState(instance.state?.app_version_op || 'gte');
    var [appVersionVal, setAppVersionVal] = React.useState(instance.state?.app_version_val || '14');
    var [appliedAppVersionOp, setAppliedAppVersionOp] = React.useState(instance.state?.app_version_op || 'gte');
    var [appliedAppVersionVal, setAppliedAppVersionVal] = React.useState(instance.state?.app_version_val || '14');
    var [hiddenCategories, setHiddenCategories] = React.useState({});

    // OCS Task Modal state
    var [showOcsModal, setShowOcsModal] = React.useState(false);
    var [ocsModalFlw, setOcsModalFlw] = React.useState(null);
    var [ocsLoading, setOcsLoading] = React.useState(false);
    var [ocsBots, setOcsBots] = React.useState([]);
    var [selectedBot, setSelectedBot] = React.useState('');
    var [ocsPrompt, setOcsPrompt] = React.useState('');
    var [ocsCreating, setOcsCreating] = React.useState(false);
    var [ocsError, setOcsError] = React.useState('');
    var [createdTaskUsernames, setCreatedTaskUsernames] = React.useState([]);

    // Inline task expansion state
    var [expandedTaskFlw, setExpandedTaskFlw] = React.useState(null);
    var [taskDetail, setTaskDetail] = React.useState(null);
    var [taskTranscript, setTaskTranscript] = React.useState(null);
    var [taskLoading, setTaskLoading] = React.useState(false);
    var [taskStatus, setTaskStatus] = React.useState('');
    var [taskOriginalStatus, setTaskOriginalStatus] = React.useState('');
    var [taskSaving, setTaskSaving] = React.useState(false);
    var [showCloseForm, setShowCloseForm] = React.useState(false);
    var [closeAction, setCloseAction] = React.useState('none');
    var [closeNote, setCloseNote] = React.useState('');

    // Column selector for Overview table
    var OVERVIEW_COLUMNS = [
        { id: 'flw_name', label: 'FLW Name', locked: true },
        { id: 'mothers', label: '# Mothers' },
        { id: 'gs_score', label: 'GS Score' },
        { id: 'post_test', label: 'Post-Test' },
        { id: 'followup_rate', label: 'Follow-up Rate' },
        { id: 'eligible_5', label: 'Eligible 5+' },
        { id: 'ebf_pct', label: '% EBF' },
        { id: 'revisit_dist', label: 'Revisit Dist.' },
        { id: 'meter_visit', label: 'Meter/Visit' },
        { id: 'minute_visit', label: 'Minute/Visit' },
        { id: 'phone_dup', label: 'Phone Dup %' },
        { id: 'anc_pnc', label: 'ANC = PNC' },
        { id: 'parity', label: 'Parity' },
        { id: 'age', label: 'Age' },
        { id: 'age_reg', label: 'Age = Reg' },
        { id: 'actions', label: 'Actions', locked: true },
    ];
    var [visibleCols, setVisibleCols] = React.useState(
        OVERVIEW_COLUMNS.map(function(c) { return c.id; })
    );
    var [showColPicker, setShowColPicker] = React.useState(false);
    var isColVisible = function(id) { return visibleCols.indexOf(id) >= 0; };
    var toggleCol = function(id) {
        setVisibleCols(function(prev) {
            return prev.indexOf(id) >= 0
                ? prev.filter(function(c) { return c !== id; })
                : prev.concat([id]);
        });
    };

    // CSRF helper
    var getCSRF = React.useCallback(function() {
        return document.querySelector('[name=csrfmiddlewaretoken]')?.value
            || document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
    }, []);

    // =========================================================================
    // Fetch audit history on mount (for selection step)
    // =========================================================================
    React.useEffect(function() {
        if (!instance.opportunity_id) return;
        setHistoryLoading(true);
        fetch('/custom_analysis/mbw_monitoring/api/opportunity-flws/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRF() },
            body: JSON.stringify({ opportunities: [instance.opportunity_id] })
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.success) {
                var hm = {};
                (data.flws || []).forEach(function(f) { hm[f.username] = f.history || {}; });
                setFlwHistory(hm);
            }
        })
        .catch(function(err) { console.error('Failed to fetch FLW history:', err); })
        .finally(function() { setHistoryLoading(false); });
    }, [instance.opportunity_id]);

    // =========================================================================
    // SSE: Load dashboard data (with snapshot-first loading)
    // =========================================================================
    var sseCleanupRef = React.useRef(null);

    React.useEffect(function() {
        if (step !== 'dashboard') return;
        var flws = instance.state?.selected_workers || instance.state?.selected_flws || [];
        if (flws.length === 0) return;

        setSseComplete(false);
        setSseError(null);
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
            if (appVersionOp && appVersionVal) {
                params.set('app_version_op', appVersionOp);
                params.set('app_version_val', appVersionVal);
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
                // Connect + CommCare are required; OCS is optional
                if (!status.connect?.active || !status.commcare?.active) {
                    setOauthStatus(status);
                    setSseMessages([]);
                    return;
                }
                setOauthStatus(null);
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
    }, [step, instance.id, refreshTrigger]);

    // =========================================================================
    // Sticky table headers via JS (CSS sticky breaks in Chrome due to ancestors)
    // =========================================================================
    React.useEffect(function() {
        var HEADER_HEIGHT = 64;
        var theadCache = [];

        function getDocumentOffsetTop(el) {
            var top = 0;
            while (el) { top += el.offsetTop; el = el.offsetParent; }
            return top;
        }

        function cacheTheads() {
            theadCache = [];
            document.querySelectorAll('[data-sticky-header] thead').forEach(function(thead) {
                var table = thead.closest('table');
                if (!table) return;
                theadCache.push({
                    thead: thead,
                    table: table,
                    offsetTop: getDocumentOffsetTop(thead)
                });
            });
        }

        function handleScroll() {
            if (theadCache.length === 0) cacheTheads();
            var scrollY = window.scrollY || window.pageYOffset;
            var threshold = scrollY + HEADER_HEIGHT;

            theadCache.forEach(function(d) {
                var tableBottom = d.offsetTop + d.table.offsetHeight;
                var theadH = d.thead.offsetHeight;
                if (threshold > d.offsetTop && threshold < tableBottom - theadH) {
                    var offset = threshold - d.offsetTop;
                    d.thead.style.transform = 'translateY(' + offset + 'px)';
                    d.thead.style.position = 'relative';
                    d.thead.style.zIndex = '20';
                    d.thead.style.boxShadow = '0 1px 3px rgba(0,0,0,0.1)';
                    // Ensure opaque background on all th cells
                    Array.from(d.thead.querySelectorAll('th')).forEach(function(th) {
                        if (!th.style.backgroundColor) th.style.backgroundColor = '#f9fafb';
                    });
                } else {
                    d.thead.style.transform = '';
                    d.thead.style.position = '';
                    d.thead.style.zIndex = '';
                    d.thead.style.boxShadow = '';
                    Array.from(d.thead.querySelectorAll('th')).forEach(function(th) {
                        th.style.backgroundColor = '';
                    });
                }
            });
        }

        // Small delay to let React finish rendering the active tab
        var timer = setTimeout(function() {
            cacheTheads();
            handleScroll();
        }, 50);

        window.addEventListener('scroll', handleScroll, { passive: true });
        window.addEventListener('resize', function() { theadCache = []; });

        return function() {
            clearTimeout(timer);
            window.removeEventListener('scroll', handleScroll);
            theadCache.forEach(function(d) {
                d.thead.style.transform = '';
                d.thead.style.position = '';
                d.thead.style.zIndex = '';
                d.thead.style.boxShadow = '';
            });
        };
    }, [activeTab, sseComplete]);

    // =========================================================================
    // Helpers
    // =========================================================================
    var toggleFlw = function(username) {
        setSelectedFlws(function(prev) {
            var next = Object.assign({}, prev);
            next[username] = !next[username];
            return next;
        });
    };
    var toggleAll = function() {
        var allSel = workers.length > 0 && workers.every(function(w) { return selectedFlws[w.username]; });
        var updated = {};
        workers.forEach(function(w) { updated[w.username] = !allSel; });
        setSelectedFlws(updated);
    };
    var selectedCount = Object.values(selectedFlws).filter(Boolean).length;

    var handleLaunch = function() {
        var selected = Object.entries(selectedFlws).filter(function(e) { return e[1]; }).map(function(e) { return e[0]; });
        if (selected.length === 0) return;
        setLaunching(true);
        onUpdateState({
            selected_workers: selected,
            selected_flws: selected,
            title: title || definition.name,
            tag: tag,
            gs_app_id: gsAppId,
            app_version_op: appVersionOp,
            app_version_val: appVersionVal,
            worker_results: {},
            flw_results: {},
        }).then(function() {
            setStep('dashboard');
            setLaunching(false);
        }).catch(function() { setLaunching(false); });
    };

    // Sort helper — supports nested keys like 'cases_still_eligible.pct'
    var getNestedValue = function(obj, key) {
        if (!obj || !key) return undefined;
        var parts = key.split('.');
        var val = obj;
        for (var i = 0; i < parts.length; i++) {
            if (val == null) return undefined;
            val = val[parts[i]];
        }
        return val;
    };

    var sortRows = function(rows, sortState) {
        var col = sortState.col;
        var dir = sortState.dir;
        return rows.slice().sort(function(a, b) {
            var va = getNestedValue(a, col);
            var vb = getNestedValue(b, col);
            if (va == null && vb == null) return 0;
            if (va == null) return 1;
            if (vb == null) return -1;
            if (typeof va === 'string') {
                var cmp = va.localeCompare(vb);
                return dir === 'asc' ? cmp : -cmp;
            }
            return dir === 'asc' ? va - vb : vb - va;
        });
    };

    var toggleSort = function(setter, current, col) {
        if (current.col === col) {
            setter({ col: col, dir: current.dir === 'asc' ? 'desc' : 'asc' });
        } else {
            setter({ col: col, dir: 'asc' });
        }
    };

    var sortIcon = function(sortState, col) {
        if (sortState.col !== col) return '';
        return sortState.dir === 'asc' ? ' \u25B2' : ' \u25BC';
    };

    var pctColor = function(val, goodThreshold, badThreshold) {
        if (val == null) return 'text-gray-400';
        if (val >= goodThreshold) return 'text-green-700';
        if (val >= badThreshold) return 'text-amber-600';
        return 'text-red-700';
    };

    var resultBadge = function(result) {
        if (!result) return null;
        var colors = {
            eligible_for_renewal: 'bg-green-100 text-green-800',
            probation: 'bg-amber-100 text-amber-800',
            suspended: 'bg-red-100 text-red-800',
        };
        return React.createElement('span', {
            className: 'px-2 py-0.5 rounded text-xs font-medium ' + (colors[result] || 'bg-gray-100 text-gray-700')
        }, result.replace(/_/g, ' '));
    };

    // Save worker assessment result (optimistic UI — updates instantly, reverts on error)
    // Toggle behavior: clicking the active status clears it
    var handleAssessment = function(username, result) {
        if (!actions || !actions.saveWorkerResult) {
            showToast('Assessment not available — please hard-refresh (Cmd+Shift+R)');
            return;
        }
        // Toggle: if already set to this result, clear it
        var currentResult = (workerResults[username] || {}).result;
        var newResult = currentResult === result ? null : result;

        // Optimistic: update UI immediately
        var previous = Object.assign({}, workerResults);
        var updated = Object.assign({}, workerResults);
        updated[username] = { result: newResult, notes: (workerResults[username] || {}).notes || '' };
        setWorkerResults(updated);

        // Save to backend (UI already updated, no need to disable buttons)
        actions.saveWorkerResult(instance.id, { username: username, result: newResult, notes: updated[username].notes })
            .then(function(resp) {
                if (resp && resp.success !== false) {
                    showToast(newResult ? 'Assessment saved: ' + newResult.replace(/_/g, ' ') : 'Assessment cleared');
                } else {
                    setWorkerResults(previous);
                    showToast('Failed to save: ' + (resp.error || 'Unknown error'));
                }
            })
            .catch(function(err) {
                setWorkerResults(previous);
                console.error('Assessment save failed:', err);
                showToast('Assessment save failed: ' + (err.message || err));
            });
    };

    // Complete session
    var handleComplete = function() {
        if (!actions || !actions.completeRun) {
            showToast('Complete not available — please hard-refresh (Cmd+Shift+R)');
            return;
        }
        setCompleting(true);
        actions.completeRun(instance.id, { overall_result: 'completed', notes: completeNotes })
            .then(function(resp) {
                if (resp && resp.success !== false) {
                    setShowCompleteModal(false);
                    setCompleting(false);
                    window.location.reload();
                } else {
                    showToast('Failed to complete: ' + (resp.error || 'Unknown error'));
                    setCompleting(false);
                }
            })
            .catch(function(err) {
                console.error('Complete failed:', err);
                showToast('Complete failed: ' + (err.message || err));
                setCompleting(false);
            });
    };

    // GPS detail fetch
    var fetchGpsDetail = function(username) {
        if (expandedGps === username) { setExpandedGps(null); return; }
        setExpandedGps(username);
        setGpsDetailLoading(true);
        var end = new Date();
        var start = new Date();
        start.setDate(end.getDate() - 30);
        var params = new URLSearchParams({
            start_date: start.toISOString().split('T')[0],
            end_date: end.toISOString().split('T')[0]
        });
        fetch('/custom_analysis/mbw_monitoring/api/gps/' + username + '/?' + params.toString())
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.success) setGpsDetail(data);
                setGpsDetailLoading(false);
            })
            .catch(function() { setGpsDetailLoading(false); });
    };

    // Toast helper
    var showToast = function(msg) {
        setToastMessage(msg);
        setTimeout(function() { setToastMessage(''); }, 3000);
    };

    // Filter helpers
    var addToFilter = function(username) {
        setFilterFlws(function(prev) {
            if (prev.indexOf(username) >= 0) return prev;
            return prev.concat([username]);
        });
        var flwNames = dashData?.flw_names || {};
        showToast('Filtered to ' + (flwNames[username] || username));
    };

    var resetFilters = function() {
        setFilterFlws([]);
        setFilterMothers([]);
        var needsRefresh = appliedAppVersionOp !== 'gte' || appliedAppVersionVal !== '14';
        setAppVersionOp('gte');
        setAppVersionVal('14');
        setAppliedAppVersionOp('gte');
        setAppliedAppVersionVal('14');
        if (needsRefresh) {
            setRefreshTrigger(function(n) { return n + 1; });
            setDashData(null);
            setSseComplete(false);
        }
    };

    // FLW Notes modal helpers
    var openFlwNotesModal = function(username) {
        var wr = workerResults[username] || {};
        setFlwNotesUsername(username);
        setFlwNotesText(wr.notes || '');
        setFlwNotesResult(wr.result || null);
        setShowFlwNotesModal(true);
    };

    var saveFlwNotes = function() {
        if (!actions || !actions.saveWorkerResult) {
            showToast('Save not available — please hard-refresh (Cmd+Shift+R)');
            return;
        }
        var username = flwNotesUsername;
        var result = flwNotesResult;
        var notes = flwNotesText;
        actions.saveWorkerResult(instance.id, { username: username, result: result, notes: notes })
            .then(function(resp) {
                if (resp && resp.success !== false) {
                    var updated = Object.assign({}, workerResults);
                    updated[username] = { result: result, notes: notes };
                    setWorkerResults(updated);
                    showToast('Notes saved');
                } else {
                    showToast('Failed to save notes: ' + (resp.error || 'Unknown error'));
                }
                setShowFlwNotesModal(false);
            })
            .catch(function(err) {
                console.error('Notes save failed:', err);
                showToast('Notes save failed: ' + (err.message || err));
            });
    };

    // Visit status style helper (inline styles to avoid Tailwind purge)
    var getVisitStatusStyle = function(status) {
        if (!status) return { backgroundColor: '#f3f4f6', color: '#1f2937' };
        if (status === 'Completed - On Time') return { backgroundColor: '#dcfce7', color: '#166534' };
        if (status === 'Completed - Late') return { backgroundColor: '#f0fdf4', color: '#15803d' };
        if (status === 'Due - On Time') return { backgroundColor: '#fef9c3', color: '#854d0e' };
        if (status === 'Due - Late') return { backgroundColor: '#ffedd5', color: '#9a3412' };
        if (status === 'Missed') return { backgroundColor: '#fee2e2', color: '#991b1b' };
        return { backgroundColor: '#f3f4f6', color: '#1f2937' };
    };

    // =========================================================================
    // RENDER: STEP 1 - FLW SELECTION
    // =========================================================================
    if (step === 'select') {
        var filteredWorkers = workers;
        if (selSearch) {
            var q = selSearch.toLowerCase();
            filteredWorkers = workers.filter(function(w) {
                return (w.name || '').toLowerCase().indexOf(q) >= 0
                    || (w.username || '').toLowerCase().indexOf(q) >= 0;
            });
        }

        // Sort filtered workers
        var sortCol = selSort.col;
        var sortDir = selSort.dir;
        filteredWorkers = filteredWorkers.slice().sort(function(a, b) {
            var ha = flwHistory[a.username] || {};
            var hb = flwHistory[b.username] || {};
            var va, vb;
            if (sortCol === 'name') { va = (a.name || a.username || '').toLowerCase(); vb = (b.name || b.username || '').toLowerCase(); }
            else if (sortCol === 'username') { va = (a.username || '').toLowerCase(); vb = (b.username || '').toLowerCase(); }
            else if (sortCol === 'audit_count') { va = ha.audit_count || 0; vb = hb.audit_count || 0; }
            else if (sortCol === 'last_audit_date') { va = ha.last_audit_date || ''; vb = hb.last_audit_date || ''; }
            else if (sortCol === 'last_audit_result') { va = ha.last_audit_result || ''; vb = hb.last_audit_result || ''; }
            else if (sortCol === 'open_task_count') { va = ha.open_task_count || 0; vb = hb.open_task_count || 0; }
            else { va = ''; vb = ''; }
            var cmp = typeof va === 'number' ? va - vb : String(va).localeCompare(String(vb));
            return sortDir === 'asc' ? cmp : -cmp;
        });

        var selSortHeader = function(col, label, align) {
            var active = selSort.col === col;
            return (
                <th className={'px-4 py-2 text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100 select-none' + (align === 'center' ? ' text-center' : ' text-left')}
                    onClick={function() { setSelSort({ col: col, dir: active && selSort.dir === 'asc' ? 'desc' : 'asc' }); }}>
                    {label} {active ? (selSort.dir === 'asc' ? '\u25B2' : '\u25BC') : ''}
                </th>
            );
        };

        return (
            <div className="space-y-6">
                <div className="bg-white rounded-lg shadow-sm p-6">
                    <h2 className="text-xl font-bold text-gray-900">Select FLWs for Monitoring</h2>
                    <p className="text-gray-600 mt-1">Choose which frontline workers to include in this monitoring session.</p>
                    <div className="grid grid-cols-3 gap-4 mt-4">
                        <div>
                            <label className="text-sm font-medium text-gray-700">Session Title</label>
                            <input type="text" value={title} onChange={function(e) { setTitle(e.target.value); }}
                                   placeholder="e.g., March 2025 Review"
                                   className="mt-1 w-full border rounded-md px-3 py-2 text-sm" />
                        </div>
                        <div>
                            <label className="text-sm font-medium text-gray-700">Tag (optional)</label>
                            <input type="text" value={tag} onChange={function(e) { setTag(e.target.value); }}
                                   placeholder="e.g., monthly-review"
                                   className="mt-1 w-full border rounded-md px-3 py-2 text-sm" />
                        </div>
                        <div>
                            <label className="text-sm font-medium text-gray-700">GS App ID</label>
                            <input type="text" value={gsAppId} onChange={function(e) { setGsAppId(e.target.value); }}
                                   placeholder="CommCare HQ app ID for Gold Standard forms"
                                   className="mt-1 w-full border rounded-md px-3 py-2 text-sm font-mono text-xs" />
                            <p className="text-xs text-gray-400 mt-0.5">Supervisor app containing Gold Standard Visit Checklist</p>
                        </div>
                    </div>
                </div>

                <div className="bg-white rounded-lg shadow-sm overflow-hidden">
                    {historyLoading && (
                        <div className="px-4 py-2 text-xs text-gray-400 bg-gray-50 border-b">Loading audit history...</div>
                    )}
                    <div className="px-4 py-2 bg-gray-50 border-b flex items-center gap-2">
                        <input type="text" value={selSearch} onChange={function(e) { setSelSearch(e.target.value); }}
                               placeholder="Search FLWs..." className="border rounded px-2 py-1 text-sm flex-1" />
                        <span className="text-sm text-gray-500">{selectedCount} selected</span>
                    </div>
                    <div className="max-h-96 overflow-y-auto">
                        <table className="min-w-full divide-y divide-gray-200">
                            <thead className="bg-gray-50 sticky top-0">
                                <tr>
                                    <th className="px-4 py-2 text-left w-10">
                                        <input type="checkbox"
                                               checked={workers.length > 0 && workers.every(function(w) { return selectedFlws[w.username]; })}
                                               onChange={toggleAll} />
                                    </th>
                                    {selSortHeader('name', 'FLW (' + workers.length + ')')}
                                    {selSortHeader('username', 'Connect ID')}
                                    {selSortHeader('audit_count', 'Past Audits', 'center')}
                                    {selSortHeader('last_audit_date', 'Last Audit Date')}
                                    {selSortHeader('last_audit_result', 'Last Result')}
                                    {selSortHeader('open_task_count', 'Open Tasks')}
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-200">
                                {filteredWorkers.map(function(w) {
                                    var h = flwHistory[w.username] || {};
                                    return (
                                        <tr key={w.username} className="hover:bg-gray-50 cursor-pointer" onClick={function() { toggleFlw(w.username); }}>
                                            <td className="px-4 py-2">
                                                <input type="checkbox" checked={!!selectedFlws[w.username]}
                                                       onChange={function() { toggleFlw(w.username); }}
                                                       onClick={function(e) { e.stopPropagation(); }} />
                                            </td>
                                            <td className="px-4 py-2">
                                                <div className="font-medium text-sm">{w.name || w.username}</div>
                                            </td>
                                            <td className="px-4 py-2 text-xs text-gray-500 font-mono">{w.username}</td>
                                            <td className="px-4 py-2 text-center text-sm text-gray-600">
                                                {h.audit_count > 0 ? h.audit_count : <span className="text-gray-300">{'\u2014'}</span>}
                                            </td>
                                            <td className="px-4 py-2 text-sm text-gray-600">
                                                {h.last_audit_date ? (
                                                    new Date(h.last_audit_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
                                                ) : <span className="text-gray-300">{'\u2014'}</span>}
                                            </td>
                                            <td className="px-4 py-2 text-sm">
                                                {h.last_audit_result ? (
                                                    <span className={
                                                        h.last_audit_result === 'eligible_for_renewal' ? 'text-green-700 bg-green-50 px-2 py-0.5 rounded text-xs' :
                                                        h.last_audit_result === 'probation' ? 'text-amber-700 bg-amber-50 px-2 py-0.5 rounded text-xs' :
                                                        h.last_audit_result === 'suspended' ? 'text-red-700 bg-red-50 px-2 py-0.5 rounded text-xs' :
                                                        'text-gray-600 text-xs'
                                                    }>{h.last_audit_result.replace(/_/g, ' ')}</span>
                                                ) : <span className="text-gray-300">{'\u2014'}</span>}
                                            </td>
                                            <td className="px-4 py-2">
                                                {h.open_task_count > 0 ? (
                                                    <span className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded">
                                                        {h.open_task_count} open
                                                    </span>
                                                ) : <span className="text-gray-300 text-sm">{'\u2014'}</span>}
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div className="flex justify-end">
                    <button onClick={handleLaunch} disabled={selectedCount === 0 || launching}
                            className="px-6 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:opacity-50">
                        {launching ? 'Launching...' : 'Launch Dashboard (' + selectedCount + ' FLWs)'}
                    </button>
                </div>
            </div>
        );
    }

    // =========================================================================
    // RENDER: STEP 2 - DASHBOARD
    // =========================================================================
    var sessionFlws = instance.state?.selected_workers || instance.state?.selected_flws || [];
    var totalFlws = sessionFlws.length;
    var assessedCount = Object.values(workerResults).filter(function(r) { return r && r.result; }).length;
    var progressPct = totalFlws > 0 ? Math.round((assessedCount / totalFlws) * 100) : 0;
    var isCompleted = instance.status === 'completed';
    var monitoringSession = dashData?.monitoring_session || null;
    var isSessionActive = monitoringSession ? monitoringSession.status === 'in_progress' : !isCompleted;

    // ---- OAuth expired state ----
    if (oauthStatus && (!oauthStatus.connect?.active || !oauthStatus.commcare?.active)) {
        var expiredServices = [];
        if (!oauthStatus.connect?.active) expiredServices.push({ name: 'Connect', key: 'connect', url: oauthStatus.connect?.authorize_url });
        if (!oauthStatus.commcare?.active) expiredServices.push({ name: 'CommCare HQ', key: 'commcare', url: oauthStatus.commcare?.authorize_url });
        if (!oauthStatus.ocs?.active) expiredServices.push({ name: 'OCS', key: 'ocs', url: oauthStatus.ocs?.authorize_url });
        var activeServices = [];
        if (oauthStatus.connect?.active) activeServices.push('Connect');
        if (oauthStatus.commcare?.active) activeServices.push('CommCare HQ');
        if (oauthStatus.ocs?.active) activeServices.push('OCS');

        return (
            <div className="space-y-4">
                <div className="bg-white rounded-lg shadow-sm p-6">
                    <h2 className="text-xl font-bold text-gray-900">{instance.state?.title || 'MBW Monitoring'}</h2>
                    <p className="text-gray-500 mt-1">Authentication required before loading data</p>
                </div>
                <div className="bg-red-50 border border-red-300 rounded-lg p-5">
                    <div className="flex items-center gap-2 mb-3">
                        <i className="fa-solid fa-triangle-exclamation text-red-600"></i>
                        <span className="font-semibold text-red-800">OAuth tokens expired</span>
                    </div>
                    <p className="text-sm text-red-700 mb-4">
                        One or more authentication tokens have expired. Please re-authorize before loading data.
                    </p>
                    <div className="space-y-2 mb-4">
                        {expiredServices.map(function(svc) {
                            return (
                                <div key={svc.key} className="flex items-center gap-3">
                                    <i className="fa-solid fa-circle-xmark text-red-500"></i>
                                    <span className="text-sm font-medium text-gray-800 w-32">{svc.name}</span>
                                    {svc.url ? (
                                        <a href={svc.url} className="px-3 py-1.5 bg-red-600 text-white text-sm rounded hover:bg-red-700 no-underline">
                                            Authorize {svc.name}
                                        </a>
                                    ) : (
                                        <span className="text-sm text-gray-500">No authorization URL available</span>
                                    )}
                                </div>
                            );
                        })}
                        {activeServices.map(function(name) {
                            return (
                                <div key={name} className="flex items-center gap-3">
                                    <i className="fa-solid fa-circle-check text-green-500"></i>
                                    <span className="text-sm font-medium text-gray-800 w-32">{name}</span>
                                    <span className="text-sm text-green-600">Active</span>
                                </div>
                            );
                        })}
                    </div>
                    <button onClick={function() { setRefreshTrigger(function(c) { return c + 1; }); }}
                            className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700">
                        <i className="fa-solid fa-rotate-right mr-1"></i> Retry
                    </button>
                </div>
            </div>
        );
    }

    // ---- Loading state ----
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
    }

    // ---- Dashboard data is loaded ----
    var overviewFlws = (dashData?.overview_data?.flw_summaries || []);
    var gpsData = dashData?.gps_data || {};
    var gpsFlws = (gpsData.flw_summaries || []);
    var followupData = dashData?.followup_data || {};
    var fuFlws = (followupData.flw_summaries || []);
    var fuDrilldown = followupData.flw_drilldown || {};
    var visitDist = dashData?.overview_data?.visit_status_distribution || {};
    var openTasks = dashData?.open_tasks || {};
    var openTaskUsernames = dashData?.open_task_usernames || Object.keys(openTasks);
    var flwNames = dashData?.flw_names || {};
    var activeUsernames = dashData?.active_usernames || [];

    // Build mother IDs from drilldown
    var allMotherIds = [];
    var motherNamesMap = {};
    Object.keys(fuDrilldown).forEach(function(u) {
        (fuDrilldown[u] || []).forEach(function(m) {
            if (m.mother_case_id && !motherNamesMap[m.mother_case_id]) {
                motherNamesMap[m.mother_case_id] = m.mother_name || m.mother_case_id;
                allMotherIds.push(m.mother_case_id);
            }
        });
    });
    allMotherIds.sort(function(a, b) {
        return (motherNamesMap[a] || a).localeCompare(motherNamesMap[b] || b);
    });

    // ---- Build FLW prompt for OCS AI Assistant ----
    var buildFLWPrompt = function(username) {
        var ov = overviewFlws.find(function(f) { return f.username === username; }) || {};
        var fu = fuFlws.find(function(f) { return f.username === username; }) || {};
        var vtKeys = ['anc', 'postnatal', 'week1', 'month1', 'month3', 'month6'];
        var vtLabels = { anc: 'ANC', postnatal: 'Postnatal', week1: 'Week 1-2', month1: 'Month 1', month3: 'Month 3', month6: 'Month 6' };

        // Red flag detection
        var redFlags = [];
        if (ov.first_gs_score != null && ov.first_gs_score < 50) redFlags.push({ label: 'Low Gold Standard Score', detail: 'GS Score: ' + ov.first_gs_score + '% (below 50% threshold)' });
        if (ov.followup_rate != null && ov.followup_rate < 50) redFlags.push({ label: 'Low Follow-Up Visit Rate', detail: 'Follow-up Rate: ' + ov.followup_rate + '% (below 50% threshold)' });
        if (ov.cases_still_eligible && ov.cases_still_eligible.pct != null && ov.cases_still_eligible.pct < 50) redFlags.push({ label: 'Low Case Eligibility Rate', detail: 'Eligible 5+: ' + ov.cases_still_eligible.pct + '% (below 50% threshold)' });
        if (ov.median_meters_per_visit != null && ov.median_meters_per_visit < 100) redFlags.push({ label: 'Low Travel Distance Per Visit', detail: 'Meter/Visit: ' + ov.median_meters_per_visit + 'm (below 100m threshold)' });
        if (ov.phone_dup_pct != null && ov.phone_dup_pct > 30) redFlags.push({ label: 'High Phone Duplicate Rate', detail: 'Phone Dup: ' + ov.phone_dup_pct + '% (above 30% threshold)' });
        if (ov.anc_pnc_same_date_count != null && ov.anc_pnc_same_date_count >= 5) redFlags.push({ label: 'ANC/PNC Same-Date Anomaly', detail: 'ANC=PNC same date: ' + ov.anc_pnc_same_date_count + ' cases (5+ threshold)' });
        if (ov.ebf_pct != null && (ov.ebf_pct <= 30 || ov.ebf_pct > 95)) redFlags.push({ label: 'Abnormal EBF Rate', detail: 'EBF Rate: ' + ov.ebf_pct + '% (' + (ov.ebf_pct <= 30 ? 'below 30%' : 'above 95%') + ' threshold)' });

        var behavior = redFlags.length > 0
            ? redFlags.map(function(r) { return r.label; }).join(', ')
            : 'General Performance Review';

        var lines = [];
        lines.push('FLW Name: ' + (ov.display_name || username));
        lines.push('Username: ' + username);
        lines.push('');
        lines.push('Behavior Being Investigated: ' + behavior);
        lines.push('');
        lines.push('Performance Summary:');
        lines.push('- Mothers registered: ' + (ov.cases_registered != null ? ov.cases_registered : '\u2014'));
        lines.push('- Eligible mothers: ' + (ov.eligible_mothers != null ? ov.eligible_mothers : '\u2014'));
        lines.push('- GS Score: ' + (ov.first_gs_score != null ? ov.first_gs_score + '%' : '\u2014'));
        lines.push('- Follow-up Rate: ' + (ov.followup_rate != null ? ov.followup_rate + '%' : '\u2014'));
        lines.push('- Cases still eligible (5+): ' + (ov.cases_still_eligible && ov.cases_still_eligible.pct != null ? ov.cases_still_eligible.pct + '% (' + ov.cases_still_eligible.eligible + '/' + ov.cases_still_eligible.total + ')' : '\u2014'));
        lines.push('- % EBF (Exclusive Breastfeeding): ' + (ov.ebf_pct != null ? ov.ebf_pct + '%' : '\u2014'));
        lines.push('');
        lines.push('Visit Overview:');
        var completionPct = fu.total_visits > 0 ? Math.round(fu.completed_total / fu.total_visits * 100) : 0;
        lines.push('- Total visits: ' + (fu.total_visits || 0));
        lines.push('- Completed: ' + (fu.completed_total || 0) + ' (' + completionPct + '% completion rate)');
        lines.push('- Currently due (late): ' + (fu.due_late || 0));
        lines.push('- Missed: ' + (fu.missed_total || 0));
        lines.push('');
        lines.push('Breakdown by visit type:');
        vtKeys.forEach(function(vt) {
            var comp = (fu[vt + '_completed_on_time'] || 0) + (fu[vt + '_completed_late'] || 0);
            var dueLate = fu[vt + '_due_late'] || 0;
            var missed = fu[vt + '_missed'] || 0;
            lines.push('- ' + (vtLabels[vt] || vt) + ': ' + comp + ' completed, ' + dueLate + ' due late, ' + missed + ' missed');
        });
        lines.push('');
        if (redFlags.length > 0) {
            lines.push('Red Flag Indicators:');
            redFlags.forEach(function(r) { lines.push('- ' + r.detail); });
        } else {
            lines.push('Red Flag Indicators:');
            lines.push('No red flag indicators detected.');
        }
        return lines.join('\\n');
    };

    // ---- OCS Modal handlers ----
    var openOcsModal = function(f) {
        setOcsModalFlw(f);
        setOcsError('');
        setOcsCreating(false);
        setSelectedBot('');
        setOcsPrompt(buildFLWPrompt(f.username));
        setShowOcsModal(true);
        setOcsLoading(true);
        actions.listOCSBots().then(function(result) {
            setOcsLoading(false);
            if (result.success && result.bots) {
                setOcsBots(result.bots);
                if (result.bots.length === 1) setSelectedBot(result.bots[0].id);
            } else if (result.needs_oauth) {
                setOcsError('OCS authentication required. Please contact admin.');
            } else {
                setOcsError(result.error || 'Failed to load bots');
            }
        });
    };

    var handleCreateTaskWithOCS = function() {
        if (!selectedBot) { setOcsError('Please select a bot'); return; }
        if (!ocsPrompt.trim()) { setOcsError('Prompt instructions cannot be empty'); return; }
        var f = ocsModalFlw;
        var today = new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });

        setOcsCreating(true);
        setOcsError('');
        actions.createTaskWithOCS({
            username: f.username,
            flw_name: f.display_name || f.username,
            title: 'MBW Follow-up: ' + (f.display_name || f.username) + ' - ' + today,
            description: 'MBW Follow-up',
            priority: 'medium',
            ocs: {
                experiment: selectedBot,
                prompt_text: ocsPrompt,
            },
        }).then(function(result) {
            setOcsCreating(false);
            if (result.success) {
                setShowOcsModal(false);
                setCreatedTaskUsernames(function(prev) { return prev.concat([f.username]); });
                showToast('Task created' + (result.ocs && result.ocs.success ? ' and AI session initiated' : '') + ' for ' + (f.display_name || f.username));
            } else {
                setOcsError(result.error || 'Failed to create task');
            }
        });
    };

    // ---- Inline task handlers ----
    var toggleTaskExpand = function(username) {
        if (expandedTaskFlw === username) {
            setExpandedTaskFlw(null);
            setTaskDetail(null);
            setTaskTranscript(null);
            setShowCloseForm(false);
            return;
        }
        var taskInfo = openTasks[username];
        if (!taskInfo) return;
        setExpandedTaskFlw(username);
        setTaskLoading(true);
        setTaskDetail(null);
        setTaskTranscript(null);
        setShowCloseForm(false);
        setCloseAction('none');
        setCloseNote('');
        if (!actions || !actions.getTaskDetail) {
            showToast('Task detail not available — please hard-refresh (Cmd+Shift+R)');
            setTaskLoading(false);
            return;
        }
        actions.getTaskDetail(taskInfo.task_id).then(function(result) {
            if (result.success && result.task) {
                setTaskDetail(result.task);
                setTaskStatus(result.task.status || 'investigating');
                setTaskOriginalStatus(result.task.status || 'investigating');
                return actions.getAITranscript(taskInfo.task_id);
            } else {
                setTaskLoading(false);
                showToast('Failed to load task: ' + (result.error || 'Unknown error'));
            }
        }).then(function(transcriptResult) {
            setTaskLoading(false);
            if (transcriptResult && transcriptResult.success) {
                setTaskTranscript(transcriptResult.messages || []);
            } else if (transcriptResult) {
                // Transcript not available — set empty array so UI shows "No messages yet" with error context
                setTaskTranscript([]);
            }
        }).catch(function(err) {
            setTaskLoading(false);
            console.error('Error loading task:', err);
        });
    };

    var handleTaskSave = function() {
        if (!taskDetail || taskStatus === taskOriginalStatus) return;
        setTaskSaving(true);
        actions.updateTask(taskDetail.id, { status: taskStatus }).then(function(result) {
            setTaskSaving(false);
            if (result.success) {
                setTaskOriginalStatus(taskStatus);
                showToast('Task status updated');
            } else {
                showToast('Failed to update: ' + (result.error || 'Unknown error'));
            }
        }).catch(function() { setTaskSaving(false); });
    };

    var handleTaskClose = function() {
        if (!taskDetail) return;
        setTaskSaving(true);
        actions.updateTask(taskDetail.id, {
            status: 'closed',
            resolution_details: { official_action: closeAction, resolution_note: closeNote }
        }).then(function(result) {
            setTaskSaving(false);
            if (result.success) {
                showToast('Task closed');
                // Remove from local open_tasks
                var newOpenTasks = Object.assign({}, openTasks);
                delete newOpenTasks[expandedTaskFlw];
                if (dashData) {
                    setDashData(Object.assign({}, dashData, {
                        open_tasks: newOpenTasks,
                        open_task_usernames: Object.keys(newOpenTasks)
                    }));
                }
                setExpandedTaskFlw(null);
                setTaskDetail(null);
                setTaskTranscript(null);
                setShowCloseForm(false);
            } else {
                showToast('Failed to close: ' + (result.error || 'Unknown error'));
            }
        }).catch(function() { setTaskSaving(false); });
    };

    var handleTaskRefreshTranscript = function() {
        if (!taskDetail) return;
        setTaskLoading(true);
        actions.getAITranscript(taskDetail.id, undefined, true).then(function(result) {
            setTaskLoading(false);
            if (result.success) {
                setTaskTranscript(result.messages || []);
                showToast('Transcript refreshed');
            }
        }).catch(function() { setTaskLoading(false); });
    };

    var TASK_STATUS_OPTIONS = [
        { value: 'investigating', label: 'Investigating', color: 'blue' },
        { value: 'flw_action_in_progress', label: 'FLW Action In Progress', color: 'yellow' },
        { value: 'flw_action_completed', label: 'FLW Action Completed', color: 'green' },
        { value: 'review_needed', label: 'Review Needed', color: 'purple' },
    ];

    // Apply filters
    var flwFilterSet = filterFlws.length > 0 ? filterFlws : null;
    var motherFilterSet = filterMothers.length > 0 ? filterMothers : null;

    var filteredOverview = overviewFlws.filter(function(f) {
        if (flwFilterSet && flwFilterSet.indexOf(f.username) < 0) return false;
        return true;
    });
    if (overviewSearch) {
        var sq = overviewSearch.toLowerCase();
        filteredOverview = filteredOverview.filter(function(f) {
            return (f.display_name || '').toLowerCase().indexOf(sq) >= 0
                || (f.username || '').toLowerCase().indexOf(sq) >= 0;
        });
    }

    var filteredGpsFlws = gpsFlws.filter(function(f) {
        if (flwFilterSet && flwFilterSet.indexOf(f.username) < 0) return false;
        return true;
    });

    var filteredFuFlws = fuFlws.filter(function(f) {
        if (flwFilterSet && flwFilterSet.indexOf(f.username) < 0) return false;
        if (motherFilterSet) {
            var mothers = fuDrilldown[f.username] || [];
            return mothers.some(function(m) { return motherFilterSet.indexOf(m.mother_case_id) >= 0; });
        }
        return true;
    });

    var sortedOverview = sortRows(filteredOverview, overviewSort);
    var sortedGps = sortRows(filteredGpsFlws, gpsSort);
    var sortedFu = sortRows(filteredFuFlws, fuSort);

    // Compute overall follow-up rate
    var overallFuRate = 0;
    if (filteredFuFlws.length > 0) {
        var totalRate = 0;
        filteredFuFlws.forEach(function(f) { totalRate += (f.completion_rate || 0); });
        overallFuRate = Math.round(totalRate / filteredFuFlws.length);
    }

    // Count FLWs by result for complete modal
    var countByResult = function(resultVal) {
        var count = 0;
        sessionFlws.forEach(function(u) {
            var wr = workerResults[u] || {};
            if (resultVal === null) {
                if (!wr.result) count++;
            } else {
                if (wr.result === resultVal) count++;
            }
        });
        return count;
    };

    // Table header helper
    var Th = function(props) {
        return (
            <th className={'px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer select-none hover:bg-gray-100 whitespace-nowrap ' + (props.className || '')}
                onClick={props.onClick}
                title={props.tooltip || ''}>
                {props.children}{props.sortIndicator || ''}
            </th>
        );
    };

    // Non-sortable header helper
    var ThStatic = function(props) {
        return (
            <th className={'px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider whitespace-nowrap ' + (props.className || '')}
                title={props.tooltip || ''}>
                {props.children}
            </th>
        );
    };

    // FLW Notes Modal
    var FlwNotesModal = function() {
        if (!showFlwNotesModal) return null;
        return (
            <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                <div className="relative bg-white rounded-lg shadow-xl max-w-md w-full">
                    <div className="px-4 pt-5 pb-4 sm:p-6">
                        <h3 className="text-lg font-medium text-gray-900 mb-3">
                            Notes for {flwNames[flwNotesUsername] || flwNotesUsername}
                        </h3>
                        <textarea value={flwNotesText} onChange={function(e) { setFlwNotesText(e.target.value); }}
                                  rows={4} placeholder="Add notes about this FLW's assessment..."
                                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-indigo-500 focus:border-indigo-500 text-sm" />
                        <div className="mt-3 flex items-center gap-2">
                            <span className="text-sm text-gray-600">Result:</span>
                            <button onClick={function() { setFlwNotesResult('eligible_for_renewal'); }}
                                    className={'px-3 py-1 rounded text-xs font-medium border transition-colors ' +
                                        (flwNotesResult === 'eligible_for_renewal' ? 'bg-green-600 text-white border-green-600' : 'bg-green-50 text-green-800 hover:bg-green-100 border-green-300')}>
                                <i className="fa-solid fa-circle-check mr-1"></i> Eligible
                            </button>
                            <button onClick={function() { setFlwNotesResult('probation'); }}
                                    className={'px-3 py-1 rounded text-xs font-medium border transition-colors ' +
                                        (flwNotesResult === 'probation' ? 'bg-amber-600 text-white border-amber-600' : 'bg-amber-50 text-amber-800 hover:bg-amber-100 border-amber-300')}>
                                <i className="fa-solid fa-triangle-exclamation mr-1"></i> Probation
                            </button>
                            <button onClick={function() { setFlwNotesResult('suspended'); }}
                                    className={'px-3 py-1 rounded text-xs font-medium border transition-colors ' +
                                        (flwNotesResult === 'suspended' ? 'bg-red-600 text-white border-red-600' : 'bg-red-50 text-red-800 hover:bg-red-100 border-red-300')}>
                                <i className="fa-solid fa-ban mr-1"></i> Suspended
                            </button>
                            {flwNotesResult && (
                                <button onClick={function() { setFlwNotesResult(null); }}
                                        className="px-3 py-1 rounded text-xs text-gray-600 hover:bg-gray-100 border border-gray-300">
                                    Clear
                                </button>
                            )}
                        </div>
                    </div>
                    <div className="bg-gray-50 px-4 py-3 sm:flex sm:flex-row-reverse rounded-b-lg">
                        <button onClick={saveFlwNotes}
                                className="w-full inline-flex justify-center rounded-md border border-transparent shadow-sm px-4 py-2 bg-indigo-600 text-base font-medium text-white hover:bg-indigo-700 sm:ml-3 sm:w-auto sm:text-sm">
                            Save
                        </button>
                        <button onClick={function() { setShowFlwNotesModal(false); }}
                                className="mt-3 w-full inline-flex justify-center rounded-md border border-gray-300 shadow-sm px-4 py-2 bg-white text-base font-medium text-gray-700 hover:bg-gray-50 sm:mt-0 sm:w-auto sm:text-sm">
                            Cancel
                        </button>
                    </div>
                </div>
            </div>
        );
    };

    // Complete modal
    var CompleteModal = function() {
        if (!showCompleteModal) return null;
        return (
            <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                <div className="relative bg-white rounded-lg shadow-xl max-w-md w-full">
                    <div className="px-4 pt-5 pb-4 sm:p-6">
                        <h3 className="text-lg font-medium text-gray-900 mb-3">Complete Monitoring Audit</h3>
                        <p className="text-sm text-gray-600 mb-4">
                            {assessedCount} of {totalFlws} FLWs have been assessed.
                        </p>
                        <div className="mb-4">
                            <label className="block text-sm font-medium text-gray-700 mb-2">Assessment Summary</label>
                            <div className="space-y-1.5 text-sm">
                                <div className="flex items-center gap-2">
                                    <span className="w-2.5 h-2.5 rounded-full bg-green-500 inline-block"></span>
                                    <span className="text-gray-700">Eligible for Renewal:</span>
                                    <span className="font-medium">{countByResult('eligible_for_renewal')}</span>
                                </div>
                                <div className="flex items-center gap-2">
                                    <span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block"></span>
                                    <span className="text-gray-700">Probation:</span>
                                    <span className="font-medium">{countByResult('probation')}</span>
                                </div>
                                <div className="flex items-center gap-2">
                                    <span className="w-2.5 h-2.5 rounded-full bg-red-500 inline-block"></span>
                                    <span className="text-gray-700">Suspended:</span>
                                    <span className="font-medium">{countByResult('suspended')}</span>
                                </div>
                                <div className="flex items-center gap-2">
                                    <span className="w-2.5 h-2.5 rounded-full bg-gray-400 inline-block"></span>
                                    <span className="text-gray-700">Not assessed:</span>
                                    <span className="font-medium">{countByResult(null)}</span>
                                </div>
                            </div>
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">Notes</label>
                            <textarea value={completeNotes} onChange={function(e) { setCompleteNotes(e.target.value); }}
                                      rows={3} className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                                      placeholder="Overall monitoring notes..." />
                        </div>
                    </div>
                    <div className="bg-gray-50 px-4 py-3 sm:flex sm:flex-row-reverse rounded-b-lg">
                        <button onClick={handleComplete} disabled={completing}
                                className="w-full inline-flex justify-center rounded-md border border-transparent shadow-sm px-4 py-2 bg-indigo-600 text-base font-medium text-white hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed sm:ml-3 sm:w-auto sm:text-sm">
                            {completing ? 'Completing...' : 'Complete Audit'}
                        </button>
                        <button onClick={function() { setShowCompleteModal(false); }}
                                className="mt-3 w-full inline-flex justify-center rounded-md border border-gray-300 shadow-sm px-4 py-2 bg-white text-base font-medium text-gray-700 hover:bg-gray-50 sm:mt-0 sm:w-auto sm:text-sm">
                            Cancel
                        </button>
                    </div>
                </div>
            </div>
        );
    };

    // Helper: get visible mothers for follow-up drilldown
    var getVisibleMothers = function(mothers) {
        if (!mothers) return [];
        var filtered = mothers;
        if (showEligibleOnly) {
            filtered = filtered.filter(function(m) { return m.eligible; });
        }
        if (motherFilterSet) {
            filtered = filtered.filter(function(m) { return motherFilterSet.indexOf(m.mother_case_id) >= 0; });
        }
        return filtered;
    };

    // Helper: get visible visits for a mother
    var getVisibleVisits = function(mother) {
        if (!mother || !mother.visits) return [];
        if (showAllVisits) return mother.visits;
        return mother.visits.filter(function(v) {
            return v.status && v.status.indexOf('Due') >= 0;
        });
    };

    // Helper: get GPS trailing 7 days max
    var getMaxDailyTravel = function(flw) {
        if (!flw.trailing_7_days || flw.trailing_7_days.length === 0) return 1;
        var maxVal = 0;
        flw.trailing_7_days.forEach(function(d) {
            if (d.distance_km > maxVal) maxVal = d.distance_km;
        });
        return maxVal || 1;
    };

    // Per-visit-type column keys
    var visitTypes = ['anc', 'postnatal', 'week1', 'month1', 'month3', 'month6'];
    var visitTypeLabels = { anc: 'ANC', postnatal: 'Postnatal', week1: 'Week 1', month1: 'Month 1', month3: 'Month 3', month6: 'Month 6' };

    return (
        <div className="space-y-4">
            {FlwNotesModal()}
            {CompleteModal()}

            {/* OCS Task + AI Assistant Modal */}
            {showOcsModal && ocsModalFlw && (
                <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={function() { if (!ocsCreating) setShowOcsModal(false); }}>
                    <div className="absolute inset-0 bg-black bg-opacity-50" style={{ backdropFilter: 'blur(4px)', WebkitBackdropFilter: 'blur(4px)' }}></div>
                    <div className="relative bg-white rounded-xl shadow-2xl max-w-lg w-full mx-4 overflow-hidden" onClick={function(e) { e.stopPropagation(); }}>
                        {/* FLW Header */}
                        <div className="bg-gradient-to-r from-purple-600 to-purple-500 px-6 py-4 flex items-center justify-between">
                            <div className="flex items-center">
                                <div className="w-10 h-10 rounded-full bg-white bg-opacity-20 flex items-center justify-center text-white font-bold mr-3">
                                    {(ocsModalFlw.display_name || ocsModalFlw.username || '').charAt(0).toUpperCase()}
                                </div>
                                <div>
                                    <div className="text-white font-semibold">{ocsModalFlw.display_name || ocsModalFlw.username}</div>
                                    <div className="text-purple-200 text-xs">{ocsModalFlw.username}</div>
                                </div>
                            </div>
                            <button onClick={function() { if (!ocsCreating) setShowOcsModal(false); }}
                                    className="text-white text-opacity-70 hover:text-opacity-100 transition-colors"
                                    disabled={ocsCreating}>
                                <i className="fa-solid fa-times text-lg"></i>
                            </button>
                        </div>

                        {/* Modal Body */}
                        <div className="px-6 py-5 space-y-4">
                            <div>
                                <h3 className="text-lg font-semibold text-gray-900">Create Task & Initiate AI</h3>
                                <p className="text-sm text-gray-500 mt-1">Configure and initiate an AI assistant conversation for this FLW.</p>
                            </div>

                            {/* Bot Selector */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                    Bot <span className="text-red-500">*</span>
                                </label>
                                {ocsLoading ? (
                                    <div className="flex items-center text-sm text-gray-500 py-2">
                                        <i className="fa-solid fa-spinner fa-spin mr-2"></i> Loading bots...
                                    </div>
                                ) : (
                                    <select value={selectedBot} onChange={function(e) { setSelectedBot(e.target.value); setOcsError(''); }}
                                            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-purple-500 focus:border-purple-500">
                                        <option value="">-- Select a bot --</option>
                                        {ocsBots.map(function(bot) {
                                            return <option key={bot.id} value={bot.id}>{bot.name}{bot.version ? ' (v' + bot.version + ')' : ''}</option>;
                                        })}
                                    </select>
                                )}
                            </div>

                            {/* Prompt Instructions */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                    Prompt Instructions <span className="text-red-500">*</span>
                                </label>
                                <textarea value={ocsPrompt} onChange={function(e) { setOcsPrompt(e.target.value); setOcsError(''); }}
                                          rows={16}
                                          className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-purple-500 focus:border-purple-500 font-mono"
                                          placeholder="Instructions for the bot..." />
                                <p className="text-xs text-gray-400 mt-1">Auto-populated from dashboard data. You can edit before sending.</p>
                            </div>

                            {/* Error Display */}
                            {ocsError && (
                                <div className="bg-red-50 border border-red-200 rounded-md px-3 py-2 text-sm text-red-700">
                                    <i className="fa-solid fa-circle-exclamation mr-1"></i> {ocsError}
                                </div>
                            )}
                        </div>

                        {/* Footer Buttons */}
                        <div className="bg-gray-50 px-6 py-4 flex justify-end gap-3 border-t border-gray-200">
                            <button onClick={function() { setShowOcsModal(false); }}
                                    disabled={ocsCreating}
                                    className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50">
                                Cancel
                            </button>
                            <button onClick={handleCreateTaskWithOCS}
                                    disabled={ocsCreating || ocsLoading || !selectedBot}
                                    className="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-green-600 border border-transparent rounded-md hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed">
                                {ocsCreating ? (
                                    <span><i className="fa-solid fa-spinner fa-spin mr-2"></i> Creating...</span>
                                ) : (
                                    <span><i className="fa-solid fa-robot mr-2"></i> Create Task & Initiate AI</span>
                                )}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Toast Notification */}
            {toastMessage && (
                <div className="fixed bottom-4 right-4 z-50 bg-gray-900 text-white px-4 py-3 rounded-lg shadow-lg text-sm">
                    {toastMessage}
                </div>
            )}

            {/* Monitoring Session Header */}
            <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-4 mb-4">
                <div className="flex justify-between items-center">
                    <div>
                        <h2 className="font-semibold text-indigo-900">{instance.state?.title || definition.name}</h2>
                        <p className="text-sm text-indigo-700 mt-1">
                            Progress: <span className="font-medium">{assessedCount}</span> / <span className="font-medium">{totalFlws}</span> FLWs assessed
                        </p>
                    </div>
                    <div className="flex gap-2">
                        <a href="/labs/workflow/" className="inline-flex items-center px-3 py-1.5 text-sm text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50">
                            <i className="fa-solid fa-arrow-left mr-1"></i> Back to Workflows
                        </a>
                        {isCompleted ? (
                            <span className="inline-flex items-center px-3 py-1.5 text-sm text-green-700 bg-green-50 border border-green-200 rounded-md">
                                <i className="fa-solid fa-check-circle mr-1"></i> Completed
                            </span>
                        ) : (
                            <button onClick={function() { setShowCompleteModal(true); }}
                                    className="inline-flex items-center px-3 py-1.5 text-sm text-white bg-indigo-600 rounded-md hover:bg-indigo-700">
                                <i className="fa-solid fa-check mr-1"></i> Complete Audit
                            </button>
                        )}
                    </div>
                </div>
                {/* Progress bar */}
                <div className="mt-3 bg-indigo-100 rounded-full h-2">
                    <div className="bg-indigo-600 h-2 rounded-full transition-all"
                         style={{ width: progressPct + '%' }}></div>
                </div>
                {dashData?.from_cache && (
                    <div className="mt-2 text-xs text-gray-400">Data loaded from cache</div>
                )}
            </div>

            {/* Tab Navigation */}
            <div className="border-b border-gray-200 mb-4 flex items-end">
                <nav className="-mb-px flex space-x-6">
                    {[
                        { id: 'overview', label: 'Overview', icon: 'fa-chart-line' },
                        { id: 'gps', label: 'GPS Analysis', icon: 'fa-location-dot' },
                        { id: 'followup', label: 'Follow-Up Rate', icon: 'fa-clipboard-check' },
                        { id: 'performance', label: 'FLW Performance', icon: 'fa-ranking-star' },
                    ].map(function(t) {
                        var active = activeTab === t.id;
                        return (
                            <button key={t.id} onClick={function() { setActiveTab(t.id); }}
                                    className={'whitespace-nowrap py-3 px-1 border-b-2 font-medium text-sm transition-colors ' +
                                        (active
                                            ? 'border-blue-500 text-blue-600'
                                            : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300')}>
                                <i className={'fa-solid ' + t.icon + ' mr-1'}></i> {t.label}
                            </button>
                        );
                    })}
                </nav>
                <div className="flex items-center gap-3 ml-auto">
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
                        {'\u21BB'} Refresh Data
                    </button>
                </div>
            </div>

            {/* Filter Bar */}
            <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm mb-4">
                <div className="flex flex-wrap items-end gap-4">
                    <div>
                        <label className="block text-xs font-medium text-gray-700 mb-1">Start Date <span className="text-gray-400">(GPS only)</span></label>
                        <input type="date" value={filterStartDate}
                               onChange={function(e) { setFilterStartDate(e.target.value); }}
                               className="border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:ring-blue-500 focus:border-blue-500" />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-gray-700 mb-1">End Date <span className="text-gray-400">(GPS only)</span></label>
                        <input type="date" value={filterEndDate}
                               onChange={function(e) { setFilterEndDate(e.target.value); }}
                               className="border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:ring-blue-500 focus:border-blue-500" />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-gray-700 mb-1">App Version <span className="text-gray-400">(GPS only)</span></label>
                        <div className="flex gap-1">
                            <select value={appVersionOp}
                                    onChange={function(e) { setAppVersionOp(e.target.value); }}
                                    className="border border-gray-300 rounded-md px-2 py-1.5 text-sm focus:ring-blue-500 focus:border-blue-500">
                                <option value="">No filter</option>
                                <option value="gte">{'>='}</option>
                                <option value="eq">{'='}</option>
                                <option value="lte">{'<='}</option>
                            </select>
                            <input type="number" value={appVersionVal}
                                   onChange={function(e) { setAppVersionVal(e.target.value); }}
                                   placeholder="#"
                                   disabled={!appVersionOp}
                                   className="border border-gray-300 rounded-md px-2 py-1.5 text-sm focus:ring-blue-500 focus:border-blue-500 w-16" />
                        </div>
                    </div>
                    <div className="flex-1 min-w-[180px]">
                        <label className="block text-xs font-medium text-gray-700 mb-1">Filter by FLW</label>
                        <select multiple value={filterFlws}
                                onChange={function(e) {
                                    var opts = e.target.options;
                                    var vals = [];
                                    for (var i = 0; i < opts.length; i++) {
                                        if (opts[i].selected) vals.push(opts[i].value);
                                    }
                                    setFilterFlws(vals);
                                }}
                                className="border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:ring-blue-500 focus:border-blue-500 w-full"
                                style={{ minHeight: '34px', maxHeight: '80px' }}>
                            {activeUsernames.map(function(u) {
                                return <option key={u} value={u}>{flwNames[u] || u}</option>;
                            })}
                        </select>
                    </div>
                    <div className="flex-1 min-w-[180px]">
                        <label className="block text-xs font-medium text-gray-700 mb-1">Filter by Mother</label>
                        <select multiple value={filterMothers}
                                onChange={function(e) {
                                    var opts = e.target.options;
                                    var vals = [];
                                    for (var i = 0; i < opts.length; i++) {
                                        if (opts[i].selected) vals.push(opts[i].value);
                                    }
                                    setFilterMothers(vals);
                                }}
                                className="border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:ring-blue-500 focus:border-blue-500 w-full"
                                style={{ minHeight: '34px', maxHeight: '80px' }}>
                            {allMotherIds.map(function(m) {
                                return <option key={m} value={m}>{motherNamesMap[m] || m}</option>;
                            })}
                        </select>
                    </div>
                    <button onClick={function() {
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
                    </button>
                    <button onClick={resetFilters}
                            className="inline-flex items-center px-4 py-1.5 text-sm text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50">
                        Reset
                    </button>
                </div>
            </div>

            {/* ============================================================ */}
            {/* OVERVIEW TAB */}
            {/* ============================================================ */}
            {activeTab === 'overview' && (
                <div>
                    {/* FLW Overview Table */}
                    <div className="bg-white border border-gray-200 rounded-lg shadow-sm">
                        <div className="px-6 py-3 border-b border-gray-200 bg-gray-50">
                            <div className="flex items-center gap-3">
                                <h2 className="text-lg font-semibold text-gray-900">
                                    FLW Overview <span className="text-sm text-gray-600 font-normal">({filteredOverview.length} FLWs)</span>
                                </h2>
                                <div style={{ position: 'relative' }}>
                                    <button onClick={function() { setShowColPicker(!showColPicker); }}
                                            className="inline-flex items-center px-3 py-1.5 border border-gray-300 rounded-md text-sm text-gray-700 bg-white hover:bg-gray-50">
                                        <i className="fa-solid fa-table-columns mr-2"></i>
                                        Columns
                                        <span className="ml-1.5 bg-gray-100 text-gray-600 text-xs px-1.5 py-0.5 rounded-full">
                                            {visibleCols.length - 2}/{OVERVIEW_COLUMNS.length - 2}
                                        </span>
                                    </button>
                                    {showColPicker && (
                                        <div style={{ position: 'fixed', inset: 0, zIndex: 40 }}
                                             onClick={function() { setShowColPicker(false); }}></div>
                                    )}
                                    {showColPicker && (
                                        <div style={{ position: 'absolute', left: 0, top: '100%', marginTop: '4px', zIndex: 50, width: '220px', backgroundColor: 'white', border: '1px solid #e5e7eb', borderRadius: '8px', boxShadow: '0 10px 15px -3px rgba(0,0,0,0.1)' }}>
                                            <div className="px-3 py-2 border-b border-gray-200">
                                                <span className="text-xs font-medium text-gray-500 uppercase">Toggle Columns</span>
                                            </div>
                                            <div style={{ maxHeight: '300px', overflowY: 'auto' }} className="py-1">
                                                {OVERVIEW_COLUMNS.map(function(col) {
                                                    return (
                                                        <label key={col.id}
                                                               className={'flex items-center px-3 py-1.5 text-sm cursor-pointer hover:bg-gray-50' + (col.locked ? ' opacity-50 cursor-default' : '')}
                                                               style={col.locked ? { pointerEvents: 'none' } : {}}>
                                                            <input type="checkbox"
                                                                   checked={isColVisible(col.id)}
                                                                   disabled={!!col.locked}
                                                                   onChange={function() { toggleCol(col.id); }}
                                                                   className="mr-2 rounded border-gray-300"
                                                                   style={{ accentColor: '#2563eb' }} />
                                                            {col.label}
                                                        </label>
                                                    );
                                                })}
                                            </div>
                                            <div className="px-3 py-2 border-t border-gray-200 flex gap-3">
                                                <button onClick={function() { setVisibleCols(OVERVIEW_COLUMNS.map(function(c) { return c.id; })); }}
                                                        className="text-xs text-blue-600 hover:text-blue-800 font-medium">Show All</button>
                                                <button onClick={function() { setVisibleCols(OVERVIEW_COLUMNS.filter(function(c) { return c.locked; }).map(function(c) { return c.id; })); }}
                                                        className="text-xs text-gray-600 hover:text-gray-800 font-medium">Minimal</button>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                        <div style={{ width: 0, minWidth: '100%', overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
                            <table data-sticky-header className="divide-y divide-gray-200" style={{ width: 'max-content', minWidth: '100%' }}>
                                <thead className="bg-gray-50">
                                    <tr>
                                        {isColVisible('flw_name') && <Th onClick={function() { toggleSort(setOverviewSort, overviewSort, 'display_name'); }}
                                            sortIndicator={sortIcon(overviewSort, 'display_name')}
                                            tooltip="Frontline worker name and ID">FLW Name</Th>}
                                        {isColVisible('mothers') && <Th onClick={function() { toggleSort(setOverviewSort, overviewSort, 'cases_registered'); }}
                                            sortIndicator={sortIcon(overviewSort, 'cases_registered')}
                                            tooltip="Unique mothers from CCHQ registration forms. Eligible count in parentheses."># Mothers</Th>}
                                        {isColVisible('gs_score') && <Th onClick={function() { toggleSort(setOverviewSort, overviewSort, 'first_gs_score'); }}
                                            sortIndicator={sortIcon(overviewSort, 'first_gs_score')}
                                            tooltip="Oldest Gold Standard Visit Checklist score">GS Score</Th>}
                                        {isColVisible('post_test') && <ThStatic tooltip="Post-test attempts - TBD">Post-Test</ThStatic>}
                                        {isColVisible('followup_rate') && <Th onClick={function() { toggleSort(setOverviewSort, overviewSort, 'followup_rate'); }}
                                            sortIndicator={sortIcon(overviewSort, 'followup_rate')}
                                            tooltip="Completed / total visits due 5+ days ago">Follow-up Rate</Th>}
                                        {isColVisible('eligible_5') && <Th onClick={function() { toggleSort(setOverviewSort, overviewSort, 'cases_still_eligible.pct'); }}
                                            sortIndicator={sortIcon(overviewSort, 'cases_still_eligible.pct')}
                                            tooltip="Eligible mothers still on track">Eligible 5+</Th>}
                                        {isColVisible('ebf_pct') && <Th onClick={function() { toggleSort(setOverviewSort, overviewSort, 'ebf_pct'); }}
                                            sortIndicator={sortIcon(overviewSort, 'ebf_pct')}
                                            tooltip="% of FLW's postnatal visits reporting exclusive breastfeeding (EBF)">% EBF</Th>}
                                        {isColVisible('revisit_dist') && <Th onClick={function() { toggleSort(setOverviewSort, overviewSort, 'revisit_distance_km'); }}
                                            sortIndicator={sortIcon(overviewSort, 'revisit_distance_km')}
                                            tooltip="Median haversine distance (km) between successive GPS">Revisit Dist.</Th>}
                                        {isColVisible('meter_visit') && <Th onClick={function() { toggleSort(setOverviewSort, overviewSort, 'median_meters_per_visit'); }}
                                            sortIndicator={sortIcon(overviewSort, 'median_meters_per_visit')}
                                            tooltip="Median haversine distance (m) between consecutive visits">Meter/Visit</Th>}
                                        {isColVisible('minute_visit') && <Th onClick={function() { toggleSort(setOverviewSort, overviewSort, 'median_minutes_per_visit'); }}
                                            sortIndicator={sortIcon(overviewSort, 'median_minutes_per_visit')}
                                            tooltip="Median time gap (min) between consecutive form submissions">Minute/Visit</Th>}
                                        {isColVisible('phone_dup') && <Th onClick={function() { toggleSort(setOverviewSort, overviewSort, 'phone_dup_pct'); }}
                                            sortIndicator={sortIcon(overviewSort, 'phone_dup_pct')}
                                            tooltip="% of FLW's mothers sharing a phone number">Phone Dup %</Th>}
                                        {isColVisible('anc_pnc') && <Th onClick={function() { toggleSort(setOverviewSort, overviewSort, 'anc_pnc_same_date_count'); }}
                                            sortIndicator={sortIcon(overviewSort, 'anc_pnc_same_date_count')}
                                            tooltip="Count of mothers where ANC and PNC same date">{'ANC = PNC'}</Th>}
                                        {isColVisible('parity') && <Th onClick={function() { toggleSort(setOverviewSort, overviewSort, 'parity_concentration.pct_duplicate'); }}
                                            sortIndicator={sortIcon(overviewSort, 'parity_concentration.pct_duplicate')}
                                            tooltip="% of FLW's mothers with duplicate parity value">Parity</Th>}
                                        {isColVisible('age') && <Th onClick={function() { toggleSort(setOverviewSort, overviewSort, 'age_concentration.pct_duplicate'); }}
                                            sortIndicator={sortIcon(overviewSort, 'age_concentration.pct_duplicate')}
                                            tooltip="% of FLW's mothers with duplicate age value">Age</Th>}
                                        {isColVisible('age_reg') && <Th onClick={function() { toggleSort(setOverviewSort, overviewSort, 'age_equals_reg_pct'); }}
                                            sortIndicator={sortIcon(overviewSort, 'age_equals_reg_pct')}
                                            tooltip="% of mothers whose DOB month+day matches registration date">{'Age = Reg'}</Th>}
                                        {isColVisible('actions') && <ThStatic className="text-right">Actions</ThStatic>}
                                    </tr>
                                </thead>
                                <tbody className="bg-white divide-y divide-gray-200">
                                    {sortedOverview.map(function(f) {
                                        var wr = workerResults[f.username] || {};
                                        var cse = f.cases_still_eligible || {};
                                        var hasNotes = wr.notes && wr.notes.length > 0;
                                        return (
                                            <React.Fragment key={f.username}>
                                            <tr className="hover:bg-gray-50">
                                                {/* FLW Name */}
                                                {isColVisible('flw_name') && (
                                                <td className="px-4 py-3 text-sm">
                                                    <div className="flex items-center">
                                                        <div className="w-8 h-8 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-bold mr-2">
                                                            {(f.display_name || f.username || '').charAt(0).toUpperCase()}
                                                        </div>
                                                        <div>
                                                            <div className="font-medium text-gray-900">{f.display_name || f.username}</div>
                                                            {f.display_name !== f.username && (
                                                                <div className="text-xs text-gray-500">{f.username}</div>
                                                            )}
                                                        </div>
                                                    </div>
                                                </td>
                                                )}
                                                {/* # Mothers */}
                                                {isColVisible('mothers') && (
                                                <td className="px-4 py-3 text-sm text-gray-900">
                                                    {f.cases_registered || 0}
                                                    <span className="text-xs text-gray-400 ml-1">({f.eligible_mothers || 0} eligible)</span>
                                                </td>
                                                )}
                                                {/* GS Score */}
                                                {isColVisible('gs_score') && (
                                                <td className="px-4 py-3 text-sm">
                                                    {f.first_gs_score != null ? (
                                                        <span className={Number(f.first_gs_score) >= 70 ? 'text-green-600 font-medium' : Number(f.first_gs_score) >= 50 ? 'text-yellow-600' : 'text-red-600'}>
                                                            {f.first_gs_score}%
                                                        </span>
                                                    ) : <span className="text-gray-400">{'\u2014'}</span>}
                                                </td>
                                                )}
                                                {/* Post-Test */}
                                                {isColVisible('post_test') && (
                                                <td className="px-4 py-3 text-sm text-gray-400">{'\u2014'}</td>
                                                )}
                                                {/* Follow-up Rate */}
                                                {isColVisible('followup_rate') && (
                                                <td className="px-4 py-3 text-sm">
                                                    <div className="flex items-center">
                                                        <div className="w-16 bg-gray-200 rounded-full h-2 mr-2">
                                                            <div className={'h-2 rounded-full transition-all ' +
                                                                    ((f.followup_rate || 0) >= 75 ? 'bg-green-500' : (f.followup_rate || 0) >= 50 ? 'bg-yellow-500' : 'bg-red-500')}
                                                                 style={{ width: Math.min(100, f.followup_rate || 0) + '%' }}></div>
                                                        </div>
                                                        <span className={'font-bold text-xs ' +
                                                                ((f.followup_rate || 0) >= 75 ? 'text-green-600' : (f.followup_rate || 0) >= 50 ? 'text-yellow-600' : 'text-red-600')}>
                                                            {f.followup_rate != null ? f.followup_rate + '%' : '\u2014'}
                                                        </span>
                                                    </div>
                                                </td>
                                                )}
                                                {/* Eligible 5+ */}
                                                {isColVisible('eligible_5') && (
                                                <td className="px-4 py-3 text-sm">
                                                    {cse.total > 0 ? (
                                                        <span className={cse.pct >= 70 ? 'text-green-600 font-medium' : cse.pct >= 50 ? 'text-yellow-600' : 'text-red-600'}>
                                                            {cse.eligible}/{cse.total} ({cse.pct}%)
                                                        </span>
                                                    ) : <span className="text-gray-400">{'\u2014'}</span>}
                                                </td>
                                                )}
                                                {/* % EBF */}
                                                {isColVisible('ebf_pct') && (
                                                <td className="px-4 py-3 text-sm">
                                                    {f.ebf_pct != null ? (
                                                        <span className={
                                                            f.ebf_pct >= 50 && f.ebf_pct <= 85 ? 'text-green-600 font-medium' :
                                                            (f.ebf_pct >= 31 && f.ebf_pct < 50) || (f.ebf_pct > 85 && f.ebf_pct <= 95) ? 'text-yellow-600' :
                                                            'text-red-600'
                                                        }>
                                                            {f.ebf_pct}%
                                                        </span>
                                                    ) : <span className="text-gray-400">{'\u2014'}</span>}
                                                </td>
                                                )}
                                                {/* Revisit Dist */}
                                                {isColVisible('revisit_dist') && (
                                                <td className="px-4 py-3 text-sm text-gray-900">
                                                    {f.revisit_distance_km != null ? f.revisit_distance_km + ' km' : <span className="text-gray-400">{'\u2014'}</span>}
                                                </td>
                                                )}
                                                {/* Meter/Visit */}
                                                {isColVisible('meter_visit') && (
                                                <td className="px-4 py-3 text-sm">
                                                    {f.median_meters_per_visit != null ? (
                                                        <span className={f.median_meters_per_visit >= 1000 ? 'text-green-600 font-medium' : f.median_meters_per_visit >= 100 ? 'text-yellow-600' : 'text-red-600'}>
                                                            {f.median_meters_per_visit + ' m'}
                                                        </span>
                                                    ) : <span className="text-gray-400">{'\u2014'}</span>}
                                                </td>
                                                )}
                                                {/* Minute/Visit */}
                                                {isColVisible('minute_visit') && (
                                                <td className="px-4 py-3 text-sm text-gray-900">
                                                    {f.median_minutes_per_visit != null ? f.median_minutes_per_visit + ' min' : <span className="text-gray-400">{'\u2014'}</span>}
                                                </td>
                                                )}
                                                {/* Phone Dup % */}
                                                {isColVisible('phone_dup') && (
                                                <td className="px-4 py-3 text-sm">
                                                    {f.phone_dup_pct != null ? (
                                                        <span className={f.phone_dup_pct <= 10 ? 'text-green-600 font-medium' : f.phone_dup_pct <= 30 ? 'text-yellow-600' : 'text-red-600'}>
                                                            {f.phone_dup_pct}%
                                                        </span>
                                                    ) : <span className="text-gray-400">{'\u2014'}</span>}
                                                </td>
                                                )}
                                                {/* ANC != PNC */}
                                                {isColVisible('anc_pnc') && (
                                                <td className="px-4 py-3 text-sm">
                                                    {f.anc_pnc_same_date_count != null ? (
                                                        <span className={f.anc_pnc_same_date_count <= 1 ? 'text-green-600 font-medium' : f.anc_pnc_same_date_count < 5 ? 'text-yellow-600' : 'text-red-600'}>
                                                            {f.anc_pnc_same_date_count}
                                                        </span>
                                                    ) : <span className="text-gray-400">{'\u2014'}</span>}
                                                </td>
                                                )}
                                                {/* Parity */}
                                                {isColVisible('parity') && (
                                                <td className="px-4 py-3 text-sm text-gray-900">
                                                    {f.parity_concentration ? (
                                                        <div>
                                                            <span>{f.parity_concentration.pct_duplicate}%</span>
                                                            <div className="text-xs text-gray-400">
                                                                {f.parity_concentration.mode_pct}% / {f.parity_concentration.mode_value}
                                                            </div>
                                                        </div>
                                                    ) : <span className="text-gray-400">{'\u2014'}</span>}
                                                </td>
                                                )}
                                                {/* Age */}
                                                {isColVisible('age') && (
                                                <td className="px-4 py-3 text-sm text-gray-900">
                                                    {f.age_concentration ? (
                                                        <div>
                                                            <span>{f.age_concentration.pct_duplicate}%</span>
                                                            <div className="text-xs text-gray-400">
                                                                {f.age_concentration.mode_pct}% / {f.age_concentration.mode_value}
                                                            </div>
                                                        </div>
                                                    ) : <span className="text-gray-400">{'\u2014'}</span>}
                                                </td>
                                                )}
                                                {/* Age != Reg */}
                                                {isColVisible('age_reg') && (
                                                <td className="px-4 py-3 text-sm text-gray-900">
                                                    {f.age_equals_reg_pct != null ? (
                                                        <span>{f.age_equals_reg_pct}%</span>
                                                    ) : <span className="text-gray-400">{'\u2014'}</span>}
                                                </td>
                                                )}
                                                {/* Actions */}
                                                {isColVisible('actions') && (
                                                <td className="px-4 py-3 text-sm text-right whitespace-nowrap">
                                                    <div className="flex items-center justify-end gap-1">
                                                        {/* Assessment buttons */}
                                                        {isSessionActive && (
                                                            <div className="inline-flex items-center gap-1 mr-2">
                                                                <button onClick={function() { handleAssessment(f.username, 'eligible_for_renewal'); }}
                                                                        disabled={!!savingResult}
                                                                        className={'px-2 py-1 rounded text-xs font-medium border transition-colors ' +
                                                                            (wr.result === 'eligible_for_renewal' ? 'bg-green-600 text-white border-green-600' : 'bg-green-50 text-green-800 border-green-300 hover:bg-green-100')}
                                                                        title="Eligible for Renewal">
                                                                    <i className="fa-solid fa-circle-check"></i>
                                                                </button>
                                                                <button onClick={function() { handleAssessment(f.username, 'probation'); }}
                                                                        disabled={!!savingResult}
                                                                        className={'px-2 py-1 rounded text-xs font-medium border transition-colors ' +
                                                                            (wr.result === 'probation' ? 'bg-amber-600 text-white border-amber-600' : 'bg-amber-50 text-amber-800 border-amber-300 hover:bg-amber-100')}
                                                                        title="Probation">
                                                                    <i className="fa-solid fa-triangle-exclamation"></i>
                                                                </button>
                                                                <button onClick={function() { handleAssessment(f.username, 'suspended'); }}
                                                                        disabled={!!savingResult}
                                                                        className={'px-2 py-1 rounded text-xs font-medium border transition-colors ' +
                                                                            (wr.result === 'suspended' ? 'bg-red-600 text-white border-red-600' : 'bg-red-50 text-red-800 border-red-300 hover:bg-red-100')}
                                                                        title="Suspended">
                                                                    <i className="fa-solid fa-ban"></i>
                                                                </button>
                                                                <button onClick={function() { openFlwNotesModal(f.username); }}
                                                                        className={'px-2 py-1 rounded text-xs border transition-colors ' +
                                                                            (hasNotes ? 'bg-yellow-100 text-yellow-800 border-yellow-300' : 'bg-gray-100 text-gray-700 border-gray-300 hover:bg-gray-200')}
                                                                        title="Notes">
                                                                    <i className="fa-solid fa-note-sticky"></i>
                                                                </button>
                                                            </div>
                                                        )}
                                                        {!isSessionActive && wr.result && (
                                                            <div className="mr-2">{resultBadge(wr.result)}</div>
                                                        )}
                                                        <button onClick={function() { addToFilter(f.username); }}
                                                                className="inline-flex items-center px-2 py-1 border border-gray-300 rounded text-xs text-gray-700 hover:bg-gray-100"
                                                                title="Add this FLW to filter">
                                                            <i className="fa-solid fa-filter mr-1"></i> Filter
                                                        </button>
                                                        {(openTaskUsernames.indexOf(f.username) >= 0 || openTasks[f.username]) ? (
                                                            <button onClick={function() { toggleTaskExpand(f.username); }}
                                                                className={'inline-flex items-center px-2 py-1 border rounded text-xs ' +
                                                                    (expandedTaskFlw === f.username
                                                                        ? 'border-purple-400 text-purple-700 bg-purple-50'
                                                                        : 'border-gray-300 text-gray-500 hover:bg-gray-100')}
                                                                title="View open task">
                                                                <i className={'fa-solid mr-1 ' + (expandedTaskFlw === f.username ? 'fa-chevron-up' : 'fa-clipboard-list')}></i> Task
                                                            </button>
                                                        ) : (
                                                            <button onClick={function() {
                                                                        if (!actions || !actions.createTaskWithOCS) {
                                                                            showToast('Task creation not available — please hard-refresh (Cmd+Shift+R)');
                                                                            return;
                                                                        }
                                                                        openOcsModal(f);
                                                                    }}
                                                                    disabled={createdTaskUsernames.indexOf(f.username) >= 0}
                                                                    className={'inline-flex items-center px-2 py-1 border rounded text-xs ' +
                                                                        (createdTaskUsernames.indexOf(f.username) >= 0
                                                                            ? 'border-gray-200 text-gray-400 cursor-not-allowed'
                                                                            : 'border-blue-300 text-blue-700 hover:bg-blue-50')}
                                                                    title={createdTaskUsernames.indexOf(f.username) >= 0 ? 'Task recently created' : 'Create task & initiate AI for this FLW'}>
                                                                <i className="fa-solid fa-plus mr-1"></i> Task
                                                            </button>
                                                        )}
                                                    </div>
                                                </td>
                                                )}
                                            </tr>
                                            {expandedTaskFlw === f.username && (
                                                <tr key={f.username + '-task'}>
                                                    <td colSpan={visibleCols.length} className="px-0 py-0 bg-gray-50" style={{position: 'relative'}}>
                                                        <div className="border-t border-b border-purple-200 bg-white mx-4 my-2 rounded-lg shadow-sm overflow-hidden" style={{maxWidth: 'calc(100vw - 220px)'}}>
                                                            {taskLoading && !taskDetail && (
                                                                <div className="p-6 text-center text-gray-500">
                                                                    <i className="fa-solid fa-spinner fa-spin mr-2"></i> Loading task...
                                                                </div>
                                                            )}
                                                            {taskDetail && (
                                                                <div>
                                                                    {/* Task header */}
                                                                    <div className="px-4 py-3 bg-purple-50 border-b border-purple-100 flex items-center justify-between">
                                                                        <div className="flex items-center gap-2">
                                                                            <i className="fa-solid fa-clipboard-list text-purple-600"></i>
                                                                            <span className="font-medium text-sm text-purple-900">{taskDetail.title}</span>
                                                                            <span className={'px-2 py-0.5 rounded-full text-xs font-medium ' +
                                                                                (taskStatus === 'investigating' ? 'bg-blue-100 text-blue-700' :
                                                                                 taskStatus === 'flw_action_in_progress' ? 'bg-yellow-100 text-yellow-700' :
                                                                                 taskStatus === 'flw_action_completed' ? 'bg-green-100 text-green-700' :
                                                                                 taskStatus === 'review_needed' ? 'bg-purple-100 text-purple-700' :
                                                                                 'bg-gray-100 text-gray-700')}>
                                                                                {(TASK_STATUS_OPTIONS.find(function(s) { return s.value === taskStatus; }) || {}).label || taskStatus}
                                                                            </span>
                                                                        </div>
                                                                        <button onClick={function() { setExpandedTaskFlw(null); }}
                                                                                className="text-gray-400 hover:text-gray-600 text-sm">
                                                                            <i className="fa-solid fa-xmark"></i>
                                                                        </button>
                                                                    </div>

                                                                    <div className="flex flex-col lg:flex-row" style={{minWidth: 0}}>
                                                                        {/* AI Conversation panel */}
                                                                        <div className="border-r border-gray-100" style={{flex: '1 1 0%', minWidth: 0, overflow: 'hidden'}}>
                                                                            <div className="px-4 py-2 bg-gray-50 border-b border-gray-100 flex items-center justify-between">
                                                                                <span className="text-xs font-medium text-gray-600">
                                                                                    <i className="fa-solid fa-comments mr-1"></i> AI Conversation
                                                                                </span>
                                                                                <button onClick={handleTaskRefreshTranscript}
                                                                                        disabled={taskLoading}
                                                                                        className="text-xs text-blue-600 hover:text-blue-800 disabled:text-gray-400"
                                                                                        title="Refresh from OCS">
                                                                                    <i className={'fa-solid fa-rotate-right' + (taskLoading ? ' fa-spin' : '')}></i> Refresh
                                                                                </button>
                                                                            </div>
                                                                            <div className="p-3 overflow-y-auto space-y-2" style={{minHeight: '120px', maxHeight: '520px'}}>
                                                                                {taskTranscript && taskTranscript.length > 0 ? (
                                                                                    taskTranscript.map(function(msg, idx) {
                                                                                        var isAssistant = msg.role === 'assistant';
                                                                                        return (
                                                                                            <div key={idx} className={'flex ' + (isAssistant ? 'justify-start' : 'justify-end')}>
                                                                                                <div className={'rounded-lg px-3 py-2 text-sm ' +
                                                                                                    (isAssistant ? 'bg-gray-100 text-gray-800' : 'bg-blue-500 text-white')}
                                                                                                    style={{maxWidth: '90%'}}>
                                                                                                    <div className="whitespace-pre-wrap break-words" style={{overflowWrap: 'anywhere'}}>{msg.content}</div>
                                                                                                    {msg.created_at && (
                                                                                                        <div className={'text-xs mt-1 ' + (isAssistant ? 'text-gray-400' : 'text-blue-200')}>
                                                                                                            {new Date(msg.created_at).toLocaleString()}
                                                                                                        </div>
                                                                                                    )}
                                                                                                </div>
                                                                                            </div>
                                                                                        );
                                                                                    })
                                                                                ) : taskTranscript && taskTranscript.length === 0 ? (
                                                                                    <div className="text-center text-gray-400 text-sm py-4">
                                                                                        <i className="fa-solid fa-comment-slash mr-1"></i> No messages yet
                                                                                    </div>
                                                                                ) : !taskLoading ? (
                                                                                    <div className="text-center text-gray-400 text-sm py-4">
                                                                                        <i className="fa-solid fa-circle-info mr-1"></i> Transcript not available
                                                                                    </div>
                                                                                ) : null}
                                                                            </div>
                                                                        </div>

                                                                        {/* Task controls panel */}
                                                                        <div className="w-full lg:w-64 p-4 space-y-3 bg-gray-50">
                                                                            {/* Status dropdown */}
                                                                            <div>
                                                                                <label className="block text-xs font-medium text-gray-600 mb-1">Status</label>
                                                                                <select value={taskStatus}
                                                                                        onChange={function(e) { setTaskStatus(e.target.value); }}
                                                                                        className="w-full text-sm border border-gray-300 rounded px-2 py-1.5 focus:ring-1 focus:ring-purple-400 focus:border-purple-400">
                                                                                    {TASK_STATUS_OPTIONS.map(function(opt) {
                                                                                        return <option key={opt.value} value={opt.value}>{opt.label}</option>;
                                                                                    })}
                                                                                </select>
                                                                            </div>

                                                                            {/* Save / Discard */}
                                                                            <div className="flex gap-2">
                                                                                <button onClick={handleTaskSave}
                                                                                        disabled={taskSaving || taskStatus === taskOriginalStatus}
                                                                                        className={'flex-1 px-3 py-1.5 rounded text-xs font-medium ' +
                                                                                            (taskStatus !== taskOriginalStatus
                                                                                                ? 'bg-purple-600 text-white hover:bg-purple-700'
                                                                                                : 'bg-gray-200 text-gray-400 cursor-not-allowed')}>
                                                                                    {taskSaving ? 'Saving...' : 'Save'}
                                                                                </button>
                                                                                <button onClick={function() { setTaskStatus(taskOriginalStatus); }}
                                                                                        disabled={taskStatus === taskOriginalStatus}
                                                                                        className={'flex-1 px-3 py-1.5 rounded text-xs font-medium border ' +
                                                                                            (taskStatus !== taskOriginalStatus
                                                                                                ? 'border-gray-300 text-gray-700 hover:bg-gray-100'
                                                                                                : 'border-gray-200 text-gray-400 cursor-not-allowed')}>
                                                                                    Discard
                                                                                </button>
                                                                            </div>

                                                                            {/* Close Task */}
                                                                            <div className="border-t border-gray-200 pt-3">
                                                                                {!showCloseForm ? (
                                                                                    <button onClick={function() { setShowCloseForm(true); }}
                                                                                            className="w-full px-3 py-1.5 rounded text-xs font-medium border border-red-300 text-red-600 hover:bg-red-50">
                                                                                        <i className="fa-solid fa-circle-xmark mr-1"></i> Close Task
                                                                                    </button>
                                                                                ) : (
                                                                                    <div className="space-y-2">
                                                                                        <div className="text-xs font-medium text-gray-600">Outcome</div>
                                                                                        <div className="space-y-1">
                                                                                            {[{v:'none', l:'None'}, {v:'satisfactory', l:'Satisfactory'}, {v:'warned', l:'Warned'}, {v:'suspended', l:'Suspended'}].map(function(o) {
                                                                                                return (
                                                                                                    <label key={o.v} className="flex items-center gap-2 text-xs cursor-pointer">
                                                                                                        <input type="radio" name="close_action" value={o.v}
                                                                                                               checked={closeAction === o.v}
                                                                                                               onChange={function() { setCloseAction(o.v); }}
                                                                                                               className="text-purple-600 focus:ring-purple-500" />
                                                                                                        {o.l}
                                                                                                    </label>
                                                                                                );
                                                                                            })}
                                                                                        </div>
                                                                                        <textarea value={closeNote}
                                                                                                  onChange={function(e) { setCloseNote(e.target.value); }}
                                                                                                  placeholder="Resolution note (optional)"
                                                                                                  rows={2}
                                                                                                  className="w-full text-xs border border-gray-300 rounded px-2 py-1 focus:ring-1 focus:ring-purple-400" />
                                                                                        <div className="flex gap-2">
                                                                                            <button onClick={handleTaskClose}
                                                                                                    disabled={taskSaving}
                                                                                                    className="flex-1 px-3 py-1.5 rounded text-xs font-medium bg-red-600 text-white hover:bg-red-700">
                                                                                                {taskSaving ? 'Closing...' : 'Confirm Close'}
                                                                                            </button>
                                                                                            <button onClick={function() { setShowCloseForm(false); }}
                                                                                                    className="flex-1 px-3 py-1.5 rounded text-xs font-medium border border-gray-300 text-gray-600 hover:bg-gray-100">
                                                                                                Cancel
                                                                                            </button>
                                                                                        </div>
                                                                                    </div>
                                                                                )}
                                                                            </div>
                                                                        </div>
                                                                    </div>
                                                                </div>
                                                            )}
                                                        </div>
                                                    </td>
                                                </tr>
                                            )}
                                        </React.Fragment>
                                        );
                                    })}
                                    {sortedOverview.length === 0 && (
                                        <tr><td colSpan={visibleCols.length} className="px-4 py-8 text-center text-sm text-gray-500">No FLW data available</td></tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            )}

            {/* ============================================================ */}
            {/* GPS ANALYSIS TAB */}
            {/* ============================================================ */}
            {activeTab === 'gps' && (
                <div>
                    {/* GPS Summary Cards */}
                    <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm mb-4">
                        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                            <div className="border-l-4 border-blue-500 pl-3">
                                <div className="text-xs text-gray-600">Total Visits</div>
                                <div className="text-xl font-bold text-gray-900">{gpsData.total_visits || 0}</div>
                            </div>
                            <div className="border-l-4 border-red-500 pl-3">
                                <div className="text-xs text-gray-600">Flagged</div>
                                <div className={'text-xl font-bold ' + ((gpsData.total_flagged || 0) > 0 ? 'text-red-600' : 'text-gray-900')}>
                                    {gpsData.total_flagged || 0}
                                </div>
                            </div>
                            <div className="border-l-4 border-green-500 pl-3">
                                <div className="text-xs text-gray-600">Date Range</div>
                                <div className="text-sm font-medium text-gray-900">
                                    {gpsData.date_range_start || '-'} to {gpsData.date_range_end || '-'}
                                </div>
                            </div>
                            <div className="border-l-4 border-purple-500 pl-3">
                                <div className="text-xs text-gray-600">Flag Threshold</div>
                                <div className="text-lg font-bold text-gray-900">5 km</div>
                            </div>
                        </div>
                    </div>

                    {/* GPS FLW Table */}
                    <div className="bg-white border border-gray-200 rounded-lg shadow-sm" style={{overflow: 'clip'}}>
                        <div className="px-6 py-3 border-b border-gray-200 bg-gray-50">
                            <h2 className="text-lg font-semibold text-gray-900">
                                FLW GPS Analysis <span className="text-sm text-gray-600 font-normal">({filteredGpsFlws.length} FLWs)</span>
                            </h2>
                        </div>
                        <div className="overflow-x-auto">
                            <table data-sticky-header className="min-w-full divide-y divide-gray-200">
                                <thead className="bg-gray-50">
                                    <tr>
                                        <Th onClick={function() { toggleSort(setGpsSort, gpsSort, 'display_name'); }}
                                            sortIndicator={sortIcon(gpsSort, 'display_name')}
                                            tooltip="Frontline worker name and ID">FLW Name</Th>
                                        <Th onClick={function() { toggleSort(setGpsSort, gpsSort, 'total_visits'); }}
                                            sortIndicator={sortIcon(gpsSort, 'total_visits')}
                                            tooltip="Total form submissions within the selected date range.">Total Visits</Th>
                                        <ThStatic tooltip="Visits with parseable GPS coordinates (lat, lon).">With GPS</ThStatic>
                                        <Th onClick={function() { toggleSort(setGpsSort, gpsSort, 'flagged_visits'); }}
                                            sortIndicator={sortIcon(gpsSort, 'flagged_visits')}
                                            tooltip="Visits flagged for anomalous GPS">Flagged</Th>
                                        <ThStatic tooltip="Count of distinct mother case IDs visited by this FLW.">Unique Cases</ThStatic>
                                        <Th onClick={function() { toggleSort(setGpsSort, gpsSort, 'avg_case_distance_km'); }}
                                            sortIndicator={sortIcon(gpsSort, 'avg_case_distance_km')}
                                            tooltip="Average haversine distance (km) between GPS coordinates">Avg Case Dist</Th>
                                        <ThStatic tooltip="Largest haversine distance (km) observed">Max Case Dist</ThStatic>
                                        <ThStatic tooltip="Daily visit count sparkline for the last 7 days">Trailing 7 Days</ThStatic>
                                        <ThStatic className="text-right">Actions</ThStatic>
                                    </tr>
                                </thead>
                                <tbody className="bg-white divide-y divide-gray-200">
                                    {sortedGps.map(function(g) {
                                        var isExpanded = expandedGps === g.username;
                                        var gpsPct = g.total_visits > 0 ? Math.round(g.visits_with_gps / g.total_visits * 100) : 0;
                                        var maxTravel = getMaxDailyTravel(g);
                                        return React.createElement(React.Fragment, { key: g.username },
                                            <tr className="hover:bg-gray-50">
                                                {/* FLW Name */}
                                                <td className="px-4 py-3 text-sm">
                                                    <div className="flex items-center">
                                                        <div className="w-8 h-8 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-bold mr-2">
                                                            {(g.display_name || g.username || '').charAt(0).toUpperCase()}
                                                        </div>
                                                        <div>
                                                            <div className="font-medium text-gray-900">{g.display_name || g.username}</div>
                                                            {g.display_name !== g.username && (
                                                                <div className="text-xs text-gray-500">{g.username}</div>
                                                            )}
                                                        </div>
                                                    </div>
                                                </td>
                                                {/* Total Visits */}
                                                <td className="px-4 py-3 text-sm text-gray-900">{g.total_visits || 0}</td>
                                                {/* With GPS */}
                                                <td className="px-4 py-3 text-sm text-gray-900">
                                                    {g.visits_with_gps || 0}
                                                    <span className="text-gray-500 ml-1">({gpsPct}%)</span>
                                                </td>
                                                {/* Flagged */}
                                                <td className="px-4 py-3 text-sm">
                                                    <span className={(g.flagged_visits || 0) > 0 ? 'text-red-600 font-bold' : 'text-gray-900'}>
                                                        {g.flagged_visits || 0}
                                                    </span>
                                                </td>
                                                {/* Unique Cases */}
                                                <td className="px-4 py-3 text-sm text-gray-900">{g.unique_cases || 0}</td>
                                                {/* Avg Case Dist */}
                                                <td className="px-4 py-3 text-sm text-gray-900">
                                                    {g.avg_case_distance_km != null ? g.avg_case_distance_km + ' km' : <span className="text-gray-400">-</span>}
                                                </td>
                                                {/* Max Case Dist */}
                                                <td className="px-4 py-3 text-sm">
                                                    {g.max_case_distance_km != null ? (
                                                        <span className={g.max_case_distance_km > 5 ? 'text-red-600 font-bold' : 'text-gray-900'}>
                                                            {g.max_case_distance_km} km
                                                        </span>
                                                    ) : <span className="text-gray-400">-</span>}
                                                </td>
                                                {/* Trailing 7 Days - BAR CHART */}
                                                <td className="px-4 py-3 text-sm">
                                                    {g.trailing_7_days && g.trailing_7_days.length > 0 ? (
                                                        <div className="flex items-center gap-2">
                                                            <div className="inline-flex items-end gap-0.5" style={{ height: '24px' }}>
                                                                {g.trailing_7_days.map(function(day, idx) {
                                                                    var barH = Math.max(2, Math.min(24, (day.distance_km / maxTravel) * 24));
                                                                    return (
                                                                        <span key={idx}
                                                                              className="w-2 rounded-sm bg-blue-500"
                                                                              style={{ height: barH + 'px' }}
                                                                              title={day.date + ': ' + day.distance_km + ' km'}></span>
                                                                    );
                                                                })}
                                                            </div>
                                                            <span className="text-xs text-gray-500">Avg: {g.avg_daily_travel_km || '-'} km/d</span>
                                                        </div>
                                                    ) : <span className="text-gray-400">-</span>}
                                                </td>
                                                {/* Actions */}
                                                <td className="px-4 py-3 text-sm text-right whitespace-nowrap">
                                                    <div className="flex items-center justify-end gap-1">
                                                        <button onClick={function() { addToFilter(g.username); }}
                                                                className="inline-flex items-center px-2 py-1 border border-gray-300 rounded text-xs text-gray-700 hover:bg-gray-100"
                                                                title="Add this FLW to filter">
                                                            <i className="fa-solid fa-filter mr-1"></i> Filter
                                                        </button>
                                                        <button onClick={function() { fetchGpsDetail(g.username); }}
                                                                className="inline-flex items-center px-2 py-1 border border-blue-300 rounded text-xs text-blue-700 hover:bg-blue-50">
                                                            <i className={'fa-solid mr-1 ' + (isExpanded ? 'fa-chevron-up' : 'fa-chevron-down')}></i>
                                                            {isExpanded ? 'Hide' : 'Details'}
                                                        </button>
                                                    </div>
                                                </td>
                                            </tr>,
                                            /* GPS Drill-Down Panel - rendered as a separate panel below the table */
                                        );
                                    })}
                                    {sortedGps.length === 0 && (
                                        <tr><td colSpan={9} className="px-4 py-8 text-center text-sm text-gray-500">No GPS data available</td></tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>

                    {/* GPS Drill-Down Panel (below table) */}
                    {expandedGps && (
                        <div className="mt-4 bg-white border border-gray-200 rounded-lg shadow-sm" style={{overflow: 'clip'}}>
                            <div className="px-6 py-3 border-b border-gray-200 bg-gray-50 flex justify-between items-center">
                                <h3 className="text-lg font-semibold text-gray-900">
                                    Visit Details for {(gpsFlws.find(function(f) { return f.username === expandedGps; }) || {}).display_name || expandedGps}
                                </h3>
                                <button onClick={function() { setExpandedGps(null); }} className="text-gray-500 hover:text-gray-700">
                                    <i className="fa-solid fa-times"></i>
                                </button>
                            </div>
                            {gpsDetailLoading ? (
                                <div className="p-6 text-center">
                                    <i className="fa-solid fa-spinner fa-spin text-blue-600 mr-2"></i> Loading visit details...
                                </div>
                            ) : gpsDetail ? (
                                <div className="overflow-x-auto">
                                    <table data-sticky-header className="min-w-full divide-y divide-gray-200">
                                        <thead className="bg-gray-50">
                                            <tr>
                                                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Date</th>
                                                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Form</th>
                                                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Entity</th>
                                                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">GPS</th>
                                                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Dist from Prev</th>
                                                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                                            </tr>
                                        </thead>
                                        <tbody className="bg-white divide-y divide-gray-200">
                                            {(gpsDetail.visits || []).map(function(v, vi) {
                                                return (
                                                    <tr key={vi} className={v.is_flagged ? 'bg-red-50' : 'hover:bg-gray-50'}>
                                                        <td className="px-4 py-2 text-sm text-gray-900">{v.visit_date || '-'}</td>
                                                        <td className="px-4 py-2 text-sm text-gray-900">{v.form_name || '-'}</td>
                                                        <td className="px-4 py-2 text-sm text-gray-900">{v.entity_name || '-'}</td>
                                                        <td className="px-4 py-2 text-sm text-gray-500">
                                                            {v.gps ? (
                                                                <span>{v.gps.latitude.toFixed(4)}, {v.gps.longitude.toFixed(4)}</span>
                                                            ) : <span className="text-gray-400">No GPS</span>}
                                                        </td>
                                                        <td className="px-4 py-2 text-sm">
                                                            {v.distance_from_prev_km != null ? (
                                                                <span className={v.distance_from_prev_km > 5 ? 'text-red-600 font-bold' : 'text-gray-900'}>
                                                                    {v.distance_from_prev_km} km
                                                                </span>
                                                            ) : <span className="text-gray-400">-</span>}
                                                        </td>
                                                        <td className="px-4 py-2 text-sm">
                                                            {v.is_flagged ? (
                                                                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800">
                                                                    <i className="fa-solid fa-flag mr-1"></i> Flagged
                                                                </span>
                                                            ) : <span className="text-green-600"><i className="fa-solid fa-check"></i></span>}
                                                        </td>
                                                    </tr>
                                                );
                                            })}
                                        </tbody>
                                    </table>
                                </div>
                            ) : (
                                <div className="p-6 text-center text-gray-500">No visits found for this FLW in the selected date range.</div>
                            )}
                        </div>
                    )}
                </div>
            )}

            {/* ============================================================ */}
            {/* FOLLOW-UP RATE TAB */}
            {/* ============================================================ */}
            {activeTab === 'followup' && (
                <div>
                    {/* Follow-up Summary Cards */}
                    <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm mb-4">
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            <div className="border-l-4 border-blue-500 pl-3">
                                <div className="text-xs text-gray-600">Total Visit Cases</div>
                                <div className="text-xl font-bold text-gray-900">{followupData.total_cases || 0}</div>
                            </div>
                            <div className="border-l-4 border-blue-500 pl-3">
                                <div className="text-xs text-gray-600">Total FLWs</div>
                                <div className="text-xl font-bold text-gray-900">{filteredFuFlws.length}</div>
                            </div>
                            <div className="border-l-4 border-green-500 pl-3">
                                <div className="text-xs text-gray-600">Avg Follow-up Rate</div>
                                <div className={'text-xl font-bold ' + (overallFuRate >= 75 ? 'text-green-600' : overallFuRate >= 50 ? 'text-yellow-600' : 'text-red-600')}>
                                    {overallFuRate}%
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Visit Status Distribution — per-visit-type stacked bar chart */}
                    {visitDist && visitDist.by_visit_type && visitDist.totals && (visitDist.totals.total > 0) && (function() {
                        var categories = [
                            { key: 'completed_on_time', label: 'Completed On Time', color: '#22c55e' },
                            { key: 'completed_late',    label: 'Completed Late',    color: '#86efac' },
                            { key: 'due_on_time',       label: 'Due On Time',       color: '#facc15' },
                            { key: 'due_late',          label: 'Due Late',          color: '#fb923c' },
                            { key: 'missed',            label: 'Missed',            color: '#ef4444' },
                            { key: 'not_due_yet',       label: 'Not Due Yet',       color: '#9ca3af' },
                        ];
                        var visibleCategories = categories.filter(function(c) { return !hiddenCategories[c.key]; });
                        var maxTotal = Math.max.apply(null, visitDist.by_visit_type.map(function(vt) {
                            var sum = 0;
                            visibleCategories.forEach(function(c) { sum += (vt[c.key] || 0); });
                            return sum;
                        }));
                        var chartHeight = 180;

                        return (
                            <div className="bg-white border border-gray-200 rounded-lg p-6 shadow-sm mb-4">
                                <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-4">Visit Status Distribution</h3>
                                {/* Bar chart */}
                                <div className="flex items-end justify-center gap-3" style={{ height: chartHeight + 30 }}>
                                    {visitDist.by_visit_type.map(function(vt) {
                                        var visibleTotal = 0;
                                        visibleCategories.forEach(function(c) { visibleTotal += (vt[c.key] || 0); });
                                        var barHeight = maxTotal > 0 ? Math.round((visibleTotal / maxTotal) * chartHeight) : 0;

                                        return (
                                            <div key={vt.visit_type} className="flex flex-col items-center" style={{ flex: '1 1 0', maxWidth: 80 }}>
                                                {/* Stacked bar */}
                                                <div className="w-full flex flex-col-reverse rounded-t overflow-hidden border border-gray-200"
                                                     style={{ height: Math.max(barHeight, 2) }}>
                                                    {visibleCategories.map(function(c) {
                                                        var count = vt[c.key] || 0;
                                                        if (count === 0) return null;
                                                        var segPct = visibleTotal > 0 ? (count / visibleTotal * 100) : 0;
                                                        return (
                                                            <div key={c.key}
                                                                 style={{ height: segPct + '%', backgroundColor: c.color, transition: 'all 0.3s', minHeight: count > 0 ? 2 : 0 }}
                                                                 title={c.label + ': ' + count + ' (' + Math.round(segPct) + '%)'}></div>
                                                        );
                                                    })}
                                                </div>
                                                {/* Total count */}
                                                <div className="text-xs text-gray-500 mt-1 font-medium">{visibleTotal}</div>
                                                {/* Visit type label */}
                                                <div className="text-xs text-gray-700 font-medium mt-0.5 text-center">{vt.visit_type}</div>
                                            </div>
                                        );
                                    })}
                                </div>
                                {/* Interactive legend */}
                                <div className="flex flex-wrap justify-center gap-3 mt-4">
                                    {categories.map(function(c) {
                                        var isHidden = !!hiddenCategories[c.key];
                                        return (
                                            <button key={c.key}
                                                    onClick={function() {
                                                        setHiddenCategories(function(prev) {
                                                            var next = Object.assign({}, prev);
                                                            if (next[c.key]) { delete next[c.key]; } else { next[c.key] = true; }
                                                            return next;
                                                        });
                                                    }}
                                                    className="inline-flex items-center gap-1.5 px-2 py-1 rounded text-xs cursor-pointer border border-transparent hover:border-gray-300"
                                                    style={{ opacity: isHidden ? 0.4 : 1, textDecoration: isHidden ? 'line-through' : 'none' }}>
                                                <span className="inline-block w-3 h-3 rounded" style={{ backgroundColor: c.color }}></span>
                                                {c.label}
                                            </button>
                                        );
                                    })}
                                </div>
                            </div>
                        );
                    })()}

                    {/* Follow-up FLW Table */}
                    <div className="bg-white border border-gray-200 rounded-lg shadow-sm" style={{overflow: 'clip'}}>
                        <div className="px-6 py-3 border-b border-gray-200 bg-gray-50">
                            <h2 className="text-lg font-semibold text-gray-900">
                                FLW Follow-Up Rates <span className="text-sm text-gray-600 font-normal">({filteredFuFlws.length} FLWs)</span>
                            </h2>
                        </div>
                        <div className="overflow-x-auto">
                            <table data-sticky-header className="min-w-full divide-y divide-gray-200">
                                <thead className="bg-gray-50">
                                    <tr>
                                        <Th onClick={function() { toggleSort(setFuSort, fuSort, 'display_name'); }}
                                            sortIndicator={sortIcon(fuSort, 'display_name')}>FLW Name</Th>
                                        <Th onClick={function() { toggleSort(setFuSort, fuSort, 'completion_rate'); }}
                                            sortIndicator={sortIcon(fuSort, 'completion_rate')}
                                            tooltip="Completed / total visits due 5+ days ago">Follow-up Rate</Th>
                                        <Th onClick={function() { toggleSort(setFuSort, fuSort, 'completed_total'); }}
                                            sortIndicator={sortIcon(fuSort, 'completed_total')}
                                            tooltip="Total completed visits out of all scheduled visits">Completed</Th>
                                        <ThStatic tooltip="Visits not yet completed but not past expiry">Due</ThStatic>
                                        <ThStatic tooltip="Visits past their expiry date that were never completed.">Missed</ThStatic>
                                        {visitTypes.map(function(vt) {
                                            return (
                                                <ThStatic key={vt} tooltip="Per-visit-type breakdown">{visitTypeLabels[vt]}</ThStatic>
                                            );
                                        })}
                                        <ThStatic className="text-right">Actions</ThStatic>
                                    </tr>
                                </thead>
                                {sortedFu.map(function(f) {
                                    var isExpanded = expandedFu === f.username;
                                    var statusColor = f.status_color || 'red';
                                    var barColorClass = statusColor === 'green' ? 'bg-green-500' : statusColor === 'yellow' ? 'bg-yellow-500' : 'bg-red-500';
                                    var textColorClass = statusColor === 'green' ? 'text-green-600' : statusColor === 'yellow' ? 'text-yellow-600' : 'text-red-600';
                                    var avatarClass = statusColor === 'green' ? 'bg-green-100 text-green-700' : statusColor === 'yellow' ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700';
                                    var dueTotalVal = (f.due_on_time || 0) + (f.due_late || 0);
                                    var completedPct = f.total_visits > 0 ? Math.round(f.completed_total / f.total_visits * 100) : 0;
                                    var drillMothers = fuDrilldown[f.username] || [];

                                    return (
                                        <tbody key={f.username} className="divide-y divide-gray-200">
                                            {/* FLW summary row */}
                                            <tr className={'hover:bg-gray-50 cursor-pointer ' + (isExpanded ? 'bg-blue-50' : 'bg-white')}
                                                onClick={function() { setExpandedFu(isExpanded ? null : f.username); }}>
                                                {/* FLW Name */}
                                                <td className="px-4 py-3 text-sm">
                                                    <div className="flex items-center">
                                                        <i className={'fa-solid fa-chevron-right text-gray-400 mr-2 text-xs transition-transform duration-200 ' + (isExpanded ? 'rotate-90' : '')}
                                                           style={isExpanded ? { transform: 'rotate(90deg)' } : {}}></i>
                                                        <div className={'w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold mr-2 ' + avatarClass}>
                                                            {(f.display_name || f.username || '').charAt(0).toUpperCase()}
                                                        </div>
                                                        <div>
                                                            <div className="font-medium text-gray-900">{f.display_name || f.username}</div>
                                                            {f.display_name !== f.username && (
                                                                <div className="text-xs text-gray-500">{f.username}</div>
                                                            )}
                                                        </div>
                                                    </div>
                                                </td>
                                                {/* Follow-up Rate */}
                                                <td className="px-4 py-3 text-sm">
                                                    <div className="flex items-center">
                                                        <div className="w-16 bg-gray-200 rounded-full h-2 mr-2">
                                                            <div className={'h-2 rounded-full transition-all ' + barColorClass}
                                                                 style={{ width: Math.min(100, f.completion_rate || 0) + '%' }}></div>
                                                        </div>
                                                        <span className={'font-bold ' + textColorClass}>
                                                            {f.completion_rate != null ? f.completion_rate + '%' : '\u2014'}
                                                        </span>
                                                    </div>
                                                </td>
                                                {/* Completed */}
                                                <td className="px-4 py-3 text-sm text-gray-900">
                                                    {f.completed_total || 0}
                                                    <span className="text-xs text-gray-400 ml-1">
                                                        {f.total_visits > 0 ? '(' + completedPct + '%)' : ''}
                                                    </span>
                                                </td>
                                                {/* Due */}
                                                <td className="px-4 py-3 text-sm text-gray-900">{dueTotalVal}</td>
                                                {/* Missed */}
                                                <td className="px-4 py-3 text-sm text-gray-900">{f.missed_total || 0}</td>
                                                {/* Per-visit-type columns */}
                                                {visitTypes.map(function(vt) {
                                                    var comp = (f[vt + '_completed_on_time'] || 0) + (f[vt + '_completed_late'] || 0);
                                                    var due = (f[vt + '_due_on_time'] || 0) + (f[vt + '_due_late'] || 0);
                                                    var missed = f[vt + '_missed'] || 0;
                                                    return (
                                                        <td key={vt} className="px-4 py-3 whitespace-nowrap text-xs">
                                                            <div className="text-green-600"><i className="fa-solid fa-check mr-1"></i>{comp}</div>
                                                            <div className="text-gray-500"><i className="fa-solid fa-clock mr-1"></i>{due}</div>
                                                            <div className="text-red-500"><i className="fa-solid fa-xmark mr-1"></i>{missed}</div>
                                                        </td>
                                                    );
                                                })}
                                                {/* Actions */}
                                                <td className="px-4 py-3 text-sm text-right whitespace-nowrap" onClick={function(e) { e.stopPropagation(); }}>
                                                    <div className="flex items-center justify-end gap-1">
                                                        <button onClick={function() { addToFilter(f.username); }}
                                                                className="inline-flex items-center px-2 py-1 border border-gray-300 rounded text-xs text-gray-700 hover:bg-gray-100"
                                                                title="Add this FLW to filter">
                                                            <i className="fa-solid fa-filter mr-1"></i> Filter
                                                        </button>
                                                    </div>
                                                </td>
                                            </tr>
                                            {/* Inline drill-down row */}
                                            {isExpanded && (
                                                <tr>
                                                    <td colSpan={12} className="p-0 bg-gray-50 border-l-4 border-blue-400">
                                                        {/* Header bar */}
                                                        <div className="px-6 py-3 border-b border-gray-200 flex justify-between items-center">
                                                            <h3 className="text-sm font-semibold text-gray-900">Visits for {f.display_name || f.username}</h3>
                                                            <div className="flex items-center gap-3">
                                                                <label className="inline-flex items-center gap-1.5 text-xs text-gray-600 cursor-pointer"
                                                                       onClick={function(e) { e.stopPropagation(); }}>
                                                                    <input type="checkbox" checked={showEligibleOnly}
                                                                           onChange={function(e) { setShowEligibleOnly(e.target.checked); }}
                                                                           className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 h-3.5 w-3.5" />
                                                                    Full intervention bonus only
                                                                </label>
                                                                <label className="inline-flex items-center gap-1.5 text-xs text-gray-600 cursor-pointer"
                                                                       onClick={function(e) { e.stopPropagation(); }}>
                                                                    <input type="checkbox" checked={showAllVisits}
                                                                           onChange={function(e) { setShowAllVisits(e.target.checked); }}
                                                                           className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 h-3.5 w-3.5" />
                                                                    Show missed/completed visits
                                                                </label>
                                                                <button onClick={function(e) { e.stopPropagation(); setExpandedFu(null); }}
                                                                        className="text-gray-500 hover:text-gray-700">
                                                                    <i className="fa-solid fa-times"></i>
                                                                </button>
                                                            </div>
                                                        </div>
                                                        {/* Mother groups */}
                                                        {getVisibleMothers(drillMothers).length > 0 ? (
                                                            <div>
                                                                {getVisibleMothers(drillMothers).map(function(mother) {
                                                                    var visibleVisits = getVisibleVisits(mother);
                                                                    var fuRateColor = (mother.follow_up_rate || 0) >= 80 ? 'bg-green-100 text-green-800' : (mother.follow_up_rate || 0) >= 60 ? 'bg-yellow-100 text-yellow-800' : 'bg-red-100 text-red-800';
                                                                    return (
                                                                        <div key={mother.mother_case_id} className="border-b border-gray-100">
                                                                            {/* Mother header */}
                                                                            <div className="px-6 py-2 bg-gray-100 flex items-center justify-between">
                                                                                <span className="text-sm font-medium text-gray-700 flex items-center">
                                                                                    {mother.mother_name ? (
                                                                                        <span>
                                                                                            {mother.mother_name}
                                                                                            <span className="text-gray-400 font-normal text-xs ml-1">
                                                                                                ({mother.mother_case_id.substring(0, 8)}...)
                                                                                            </span>
                                                                                        </span>
                                                                                    ) : (
                                                                                        <span className="font-mono text-xs">{mother.mother_case_id}</span>
                                                                                    )}
                                                                                    {!mother.eligible && (
                                                                                        <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-500 ml-2">Not eligible</span>
                                                                                    )}
                                                                                </span>
                                                                                <span className={'text-xs px-2 py-1 rounded ' + fuRateColor}>
                                                                                    {mother.completed || 0}/{mother.total || 0} ({mother.follow_up_rate || 0}%)
                                                                                </span>
                                                                            </div>
                                                                            {/* Mother metadata row */}
                                                                            <div className="px-6 py-1.5 bg-gray-50 flex flex-wrap gap-x-6 gap-y-1 text-xs text-gray-500 border-b border-gray-100">
                                                                                {mother.registration_date && (
                                                                                    <span><i className="fa-solid fa-calendar-plus mr-1 text-gray-400"></i>Registered: <span className="text-gray-700">{mother.registration_date}</span></span>
                                                                                )}
                                                                                {mother.age && (
                                                                                    <span><i className="fa-solid fa-user mr-1 text-gray-400"></i>Age: <span className="text-gray-700">{mother.age}</span></span>
                                                                                )}
                                                                                {mother.phone_number && (
                                                                                    <span><i className="fa-solid fa-phone mr-1 text-gray-400"></i><span className="text-gray-700">{mother.phone_number}</span></span>
                                                                                )}
                                                                                {mother.household_size && (
                                                                                    <span><i className="fa-solid fa-people-roof mr-1 text-gray-400"></i>Household: <span className="text-gray-700">{mother.household_size}</span></span>
                                                                                )}
                                                                                {mother.preferred_time_of_visit && (
                                                                                    <span><i className="fa-solid fa-clock mr-1 text-gray-400"></i>Preferred time: <span className="text-gray-700">{mother.preferred_time_of_visit}</span></span>
                                                                                )}
                                                                                {mother.expected_delivery_date && (
                                                                                    <span><i className="fa-solid fa-calendar mr-1 text-gray-400"></i>EDD: <span className="text-gray-700">{mother.expected_delivery_date}</span></span>
                                                                                )}
                                                                                {mother.anc_completion_date && (
                                                                                    <span><i className="fa-solid fa-check-circle mr-1 text-green-500"></i>ANC completed: <span className="text-gray-700">{mother.anc_completion_date}</span></span>
                                                                                )}
                                                                                {mother.pnc_completion_date && (
                                                                                    <span><i className="fa-solid fa-check-circle mr-1 text-green-500"></i>PNC completed: <span className="text-gray-700">{mother.pnc_completion_date}</span></span>
                                                                                )}
                                                                                {mother.baby_dob && (
                                                                                    <span><i className="fa-solid fa-baby mr-1 text-gray-400"></i>Baby DOB: <span className="text-gray-700">{mother.baby_dob}</span></span>
                                                                                )}
                                                                                {!mother.registration_date && !mother.age && !mother.phone_number && !mother.household_size && !mother.preferred_time_of_visit && !mother.anc_completion_date && !mother.pnc_completion_date && !mother.expected_delivery_date && !mother.baby_dob && (
                                                                                    <span className="text-gray-400 italic">No metadata available</span>
                                                                                )}
                                                                            </div>
                                                                            {/* Visits table */}
                                                                            <table className="w-full table-fixed divide-y divide-gray-200">
                                                                                <thead>
                                                                                    <tr>
                                                                                        <th className="w-[25%] px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Visit Type</th>
                                                                                        <th className="w-[25%] px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Scheduled</th>
                                                                                        <th className="w-[25%] px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Expiry Date</th>
                                                                                        <th className="w-[25%] px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                                                                                    </tr>
                                                                                </thead>
                                                                                <tbody>
                                                                                    {visibleVisits.length > 0 ? visibleVisits.map(function(visit, vi) {
                                                                                        return (
                                                                                            <tr key={vi} className="hover:bg-gray-50">
                                                                                                <td className="px-4 py-2 text-sm text-gray-900">{visit.visit_type}</td>
                                                                                                <td className="px-4 py-2 text-sm text-gray-900">{visit.visit_date_scheduled || '-'}</td>
                                                                                                <td className="px-4 py-2 text-sm text-gray-900">{visit.visit_expiry_date || '-'}</td>
                                                                                                <td className="px-4 py-2 text-sm">
                                                                                                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium" style={getVisitStatusStyle(visit.status)}>
                                                                                                        {visit.status}
                                                                                                    </span>
                                                                                                </td>
                                                                                            </tr>
                                                                                        );
                                                                                    }) : (
                                                                                        <tr><td colSpan={4} className="px-4 py-3 text-center text-xs text-gray-400 italic">No due visits</td></tr>
                                                                                    )}
                                                                                </tbody>
                                                                            </table>
                                                                        </div>
                                                                    );
                                                                })}
                                                            </div>
                                                        ) : (
                                                            <div className="p-6 text-center text-gray-500">
                                                                {fromSnapshot ? 'Drill-down data not available in snapshot. Click "Refresh Data" to load details.' : 'No due visits found for this FLW.'}
                                                            </div>
                                                        )}
                                                    </td>
                                                </tr>
                                            )}
                                        </tbody>
                                    );
                                })}
                                {sortedFu.length === 0 && (
                                    <tbody>
                                        <tr><td colSpan={12} className="px-4 py-8 text-center text-sm text-gray-500">No follow-up data available. Ensure CommCare HQ is authorized.</td></tr>
                                    </tbody>
                                )}
                            </table>
                        </div>
                    </div>
                </div>
            )}

            {/* ========== FLW PERFORMANCE TAB ========== */}
            {activeTab === 'performance' && (
                <div>
                    <div className="bg-white rounded-lg shadow-sm border border-gray-200" style={{overflow: 'clip'}}>
                        <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
                            <h3 className="text-sm font-semibold text-gray-700">
                                <i className="fa-solid fa-ranking-star mr-1"></i> FLW Performance by Assessment Status
                            </h3>
                            <p className="text-xs text-gray-500 mt-1">
                                Aggregated case metrics grouped by each FLW's latest known assessment outcome across all completed monitoring runs.
                            </p>
                        </div>
                        <div className="overflow-x-auto">
                            <table data-sticky-header className="min-w-full divide-y divide-gray-200 text-sm">
                                <thead className="bg-gray-50">
                                    <tr>
                                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                                        <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase tracking-wider"># FLWs</th>
                                        <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Total Cases</th>
                                        <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Eligible at Reg</th>
                                        <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Still Eligible</th>
                                        <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">% Still Eligible</th>
                                        <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase tracking-wider" title="Cases with 0 or 1 missed visits / all cases">% &le;1 Missed</th>
                                        <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase tracking-wider" title="Cases with 3+ completed visits among those whose Month 1 visit is due (5-day buffer)">% 4 Visits On Track</th>
                                        <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase tracking-wider" title="Cases with 4+ completed visits among those whose Month 3 visit is due (5-day buffer)">% 5 Visits Complete</th>
                                        <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase tracking-wider" title="Cases with 5+ completed visits among those whose Month 6 visit is due (5-day buffer)">% 6 Visits Complete</th>
                                    </tr>
                                </thead>
                                <tbody className="bg-white divide-y divide-gray-200">
                                    {(dashData?.performance_data || []).map(function(row) {
                                        var statusColors = {
                                            eligible_for_renewal: '#22c55e',
                                            probation: '#eab308',
                                            suspended: '#ef4444',
                                            none: '#9ca3af',
                                        };
                                        var color = statusColors[row.status_key] || '#9ca3af';
                                        return (
                                            <tr key={row.status_key} className="hover:bg-gray-50">
                                                <td className="px-3 py-2 whitespace-nowrap">
                                                    <span className="inline-flex items-center gap-1.5">
                                                        <span style={{width: 10, height: 10, borderRadius: '50%', backgroundColor: color, display: 'inline-block'}}></span>
                                                        <span className="font-medium text-gray-900">{row.status}</span>
                                                    </span>
                                                </td>
                                                <td className="px-3 py-2 text-right text-gray-700">{row.num_flws}</td>
                                                <td className="px-3 py-2 text-right text-gray-700">{row.total_cases}</td>
                                                <td className="px-3 py-2 text-right text-gray-700">{row.total_cases_eligible_at_registration}</td>
                                                <td className="px-3 py-2 text-right text-gray-700">{row.total_cases_still_eligible}</td>
                                                <td className="px-3 py-2 text-right font-medium" style={{color: row.pct_still_eligible >= 80 ? '#22c55e' : row.pct_still_eligible >= 60 ? '#eab308' : '#ef4444'}}>{row.pct_still_eligible}%</td>
                                                <td className="px-3 py-2 text-right text-gray-700">{row.pct_missed_1_or_less_visits}%</td>
                                                <td className="px-3 py-2 text-right text-gray-700">{row.pct_4_visits_on_track}%</td>
                                                <td className="px-3 py-2 text-right text-gray-700">{row.pct_5_visits_complete}%</td>
                                                <td className="px-3 py-2 text-right text-gray-700">{row.pct_6_visits_complete}%</td>
                                            </tr>
                                        );
                                    })}
                                    {/* Totals row */}
                                    {(function() {
                                        var perf = dashData?.performance_data || [];
                                        if (perf.length === 0) return null;
                                        var totals = {
                                            num_flws: 0, total_cases: 0,
                                            total_cases_eligible_at_registration: 0,
                                            total_cases_still_eligible: 0,
                                        };
                                        perf.forEach(function(r) {
                                            totals.num_flws += r.num_flws;
                                            totals.total_cases += r.total_cases;
                                            totals.total_cases_eligible_at_registration += r.total_cases_eligible_at_registration;
                                            totals.total_cases_still_eligible += r.total_cases_still_eligible;
                                        });
                                        var pctStill = totals.total_cases_eligible_at_registration > 0
                                            ? Math.round(totals.total_cases_still_eligible / totals.total_cases_eligible_at_registration * 100) : 0;
                                        // Weighted averages for percentage columns
                                        var totalMissedNum = 0;
                                        var total4Num = 0; var total4Den = 0;
                                        var total5Num = 0; var total5Den = 0;
                                        var total6Num = 0; var total6Den = 0;
                                        perf.forEach(function(r) {
                                            totalMissedNum += Math.round(r.pct_missed_1_or_less_visits * r.total_cases / 100);
                                        });
                                        var pctMissed = totals.total_cases > 0 ? Math.round(totalMissedNum / totals.total_cases * 100) : 0;
                                        return (
                                            <tr className="bg-gray-50 font-semibold border-t-2 border-gray-300">
                                                <td className="px-3 py-2 text-gray-900">Total</td>
                                                <td className="px-3 py-2 text-right text-gray-900">{totals.num_flws}</td>
                                                <td className="px-3 py-2 text-right text-gray-900">{totals.total_cases}</td>
                                                <td className="px-3 py-2 text-right text-gray-900">{totals.total_cases_eligible_at_registration}</td>
                                                <td className="px-3 py-2 text-right text-gray-900">{totals.total_cases_still_eligible}</td>
                                                <td className="px-3 py-2 text-right text-gray-900">{pctStill}%</td>
                                                <td className="px-3 py-2 text-right text-gray-900">{pctMissed}%</td>
                                                <td className="px-3 py-2 text-right text-gray-500">-</td>
                                                <td className="px-3 py-2 text-right text-gray-500">-</td>
                                                <td className="px-3 py-2 text-right text-gray-500">-</td>
                                            </tr>
                                        );
                                    })()}
                                </tbody>
                            </table>
                        </div>
                        {(!dashData?.performance_data || dashData.performance_data.length === 0) && (
                            <div className="px-4 py-8 text-center text-sm text-gray-500">
                                No performance data available. Data will appear after the dashboard finishes loading.
                            </div>
                        )}
                    </div>
                </div>
            )}
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
    "pipeline_schema": None,
}
