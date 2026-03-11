"""
SAM Follow-up Timeline Workflow Template.

Dashboard-first view for SAM (Severe Acute Malnutrition) follow-up programs.
Tracks children across multiple follow-up visits with MUAC measurements,
photos, and referral compliance.

All data is extracted visit-level and grouped by child_case_id
client-side in the React component.
"""

DEFINITION = {
    "name": "SAM Follow-up Timeline",
    "description": "Track SAM follow-up visits per child with MUAC measurements, photos, and referral compliance",
    "version": 1,
    "templateType": "sam_followup",
    "statuses": [
        {"id": "active_red", "label": "SAM (Red)", "color": "red"},
        {"id": "active_yellow", "label": "MAM (Yellow)", "color": "yellow"},
        {"id": "recovered", "label": "Recovered (Green)", "color": "green"},
        {"id": "lost_to_followup", "label": "Lost to Follow-up", "color": "gray"},
    ],
    "config": {
        "showSummaryCards": False,
        "showFilters": False,
    },
    "pipeline_sources": [],
}

PIPELINE_SCHEMAS = [
    {
        "alias": "visits",
        "name": "SAM Follow-up Visit Data",
        "description": "Visit-level data for SAM follow-up beneficiaries, grouped by child_case_id",
        "schema": {
            "data_source": {"type": "connect_csv"},
            "grouping_key": "username",
            "terminal_stage": "visit_level",
            "linking_field": "child_case_id",
            "fields": [
                # --- Identity (from additional_case_info) ---
                {
                    "name": "child_case_id",
                    "paths": [
                        "form.case.@case_id",
                        "form.additional_case_info.child_case_id",
                    ],
                    "aggregation": "first",
                },
                {
                    "name": "child_name",
                    "path": "form.additional_case_info.child_name",
                    "aggregation": "first",
                },
                {
                    "name": "childs_age_in_month",
                    "path": "form.additional_case_info.childs_age_in_month",
                    "aggregation": "first",
                },
                {
                    "name": "childs_gender",
                    "path": "form.additional_case_info.childs_gender",
                    "aggregation": "first",
                },
                {
                    "name": "childs_dob",
                    "path": "form.additional_case_info.childs_dob",
                    "aggregation": "first",
                    "transform": "date",
                },
                {
                    "name": "household_name",
                    "path": "form.additional_case_info.household_name",
                    "aggregation": "first",
                },
                {
                    "name": "household_phone",
                    "path": "form.additional_case_info.household_phone",
                    "aggregation": "first",
                },
                {
                    "name": "hh_village_name",
                    "path": "form.additional_case_info.hh_village_name",
                    "aggregation": "first",
                },
                # --- Visit tracking ---
                {
                    "name": "followup_number",
                    "path": "form.followup_number",
                    "aggregation": "first",
                },
                {
                    "name": "fu_visit_date",
                    "path": "form.fu_visit_date",
                    "aggregation": "first",
                    "transform": "date",
                },
                {
                    "name": "previous_followup_date",
                    "path": "form.previous_followup_date",
                    "aggregation": "first",
                    "transform": "date",
                },
                {
                    "name": "all_followup_visit_count",
                    "path": "form.all_followup_visit_count",
                    "aggregation": "first",
                },
                {
                    "name": "time_end",
                    "path": "form.meta.timeEnd",
                    "aggregation": "first",
                },
                {
                    "name": "flw_username",
                    "path": "form.meta.username",
                    "aggregation": "first",
                },
                # --- MUAC clinical (dual paths for first vs subsequent follow-ups) ---
                {
                    "name": "muac_cm",
                    "paths": [
                        "form.first_followup_muac.muac_display_group_1.soliciter_sam_followup_muac_cm",
                        "form.next_followup.followup_muac_display_group_1.followup_soliciter_sam_followup_muac_cm",
                    ],
                    "aggregation": "first",
                    "transform": "float",
                },
                {
                    "name": "muac_color",
                    "paths": [
                        "form.first_followup_muac.first_followup_muac_colour",
                        "form.next_followup.followup_muac_display_group_1.next_followup_muac_colour",
                        "form.final_muac_color",
                    ],
                    "aggregation": "first",
                },
                {
                    "name": "child_status_reported",
                    "paths": [
                        "form.first_followup_muac.muac_display_group_1.child_status_reported",
                        "form.next_followup.followup_muac_display_group_1.followup_child_status_reported",
                    ],
                    "aggregation": "first",
                },
                # --- Referral tracking (dual paths) ---
                {
                    "name": "visited_facility",
                    "paths": [
                        "form.first_followup_muac.question_list_1.visited_facility",
                        "form.next_followup.followup_visited_facility",
                    ],
                    "aggregation": "first",
                },
                {
                    "name": "which_facility_visited",
                    "paths": [
                        "form.first_followup_muac.visited_facility.which_facility_visited",
                        "form.next_followup.followup_with_visit_facility.followup_facility_visited",
                    ],
                    "aggregation": "first",
                },
                {
                    "name": "treatment_received",
                    "paths": [
                        "form.first_followup_muac.visited_facility.treatment_received",
                        "form.next_followup.followup_with_visit_facility.followup_treatment_received",
                    ],
                    "aggregation": "first",
                },
                {
                    "name": "treatment_adherence",
                    "paths": [
                        "form.first_followup_muac.visited_facility.treatment_adherence",
                        "form.next_followup.followup_with_visit_facility.followup_treatment_adherence",
                    ],
                    "aggregation": "first",
                },
                {
                    "name": "caregiver_satisfaction",
                    "paths": [
                        "form.first_followup_muac.visited_facility.caregiver_satisfaction",
                        "form.next_followup.followup_with_visit_facility.followup_caregiver_satisfaction",
                    ],
                    "aggregation": "first",
                },
                {
                    "name": "reason_no_visit",
                    "paths": [
                        "form.first_followup_muac.no_visited_facility.reason_no_visit",
                        "form.next_followup.followup_with_no_visit_facility.followup_reason_no_visit",
                    ],
                    "aggregation": "first",
                },
                # --- Consent & outcome ---
                {
                    "name": "sam_followup_consent",
                    "path": "form.consent.sam_followup_consent_group.sam_followup_consent",
                    "aggregation": "first",
                },
                {
                    "name": "consent_next_follow_up",
                    "path": "form.next_followup.followup_muac_display_group_1.consent_next_follow_up",
                    "aggregation": "first",
                },
                {
                    "name": "child_recovered",
                    "path": "form.child_recovered",
                    "aggregation": "first",
                },
                {
                    "name": "delivery_status",
                    "path": "form.final_check.sam_followup_muac_delivery_status",
                    "aggregation": "first",
                },
                # --- Location ---
                {
                    "name": "gps",
                    "path": "form.location_blocks.gps_block.normalized_location",
                    "aggregation": "first",
                },
            ],
        },
    },
]

RENDER_CODE = """function WorkflowUI({ definition, instance, workers, pipelines, links, actions, onUpdateState }) {

    // ========================================================================
    // UTILITY FUNCTIONS
    // ========================================================================

    // --- Utility: days since a date string ---
    function daysSince(dateStr) {
        if (!dateStr) return null;
        var parsed = new Date(dateStr);
        if (isNaN(parsed.getTime())) return null;
        return Math.floor((Date.now() - parsed.getTime()) / 86400000);
    }

    // --- Utility: MUAC color badge classes ---
    function getMuacColorClass(color) {
        if (!color) return 'bg-gray-100 text-gray-800';
        var c = String(color).toLowerCase();
        if (c === 'red') return 'bg-red-100 text-red-800';
        if (c === 'yellow') return 'bg-yellow-100 text-yellow-800';
        if (c === 'green') return 'bg-green-100 text-green-800';
        return 'bg-gray-100 text-gray-800';
    }

    // --- Utility: MUAC dot hex color ---
    function getMuacDotColor(color) {
        if (!color) return '#9ca3af';
        var c = String(color).toLowerCase();
        if (c === 'red') return '#ef4444';
        if (c === 'yellow') return '#f59e0b';
        if (c === 'green') return '#10b981';
        return '#9ca3af';
    }

    // --- Utility: format display value ---
    function formatValue(val, suffix) {
        if (val == null || val === '') return '\\u2014';
        var str = typeof val === 'number' ? val.toLocaleString() : String(val);
        return suffix ? str + suffix : str;
    }

    // ========================================================================
    // DATA PROCESSING
    // ========================================================================

    // --- Group flat visit rows by child_case_id ---
    function groupVisitsByChild(visitRows) {
        var grouped = {};
        visitRows.forEach(function(row) {
            var caseId = row.child_case_id;
            if (!caseId) return;
            if (!grouped[caseId]) {
                grouped[caseId] = [];
            }
            grouped[caseId].push(row);
        });

        return Object.keys(grouped).map(function(caseId) {
            var rows = grouped[caseId].slice().sort(function(a, b) {
                var da = a.fu_visit_date ? new Date(a.fu_visit_date) : (a.time_end ? new Date(a.time_end) : new Date(0));
                var db = b.fu_visit_date ? new Date(b.fu_visit_date) : (b.time_end ? new Date(b.time_end) : new Date(0));
                return da - db;
            });

            // Pull demographics from the first row that has data
            var findFirst = function(field) {
                for (var i = 0; i < rows.length; i++) {
                    if (rows[i][field] != null && rows[i][field] !== '') return rows[i][field];
                }
                return null;
            };

            var childName = findFirst('child_name');
            var childsAge = findFirst('childs_age_in_month');
            var childsGender = findFirst('childs_gender');
            var childsDob = findFirst('childs_dob');
            var householdName = findFirst('household_name');
            var householdPhone = findFirst('household_phone');
            var villageName = findFirst('hh_village_name');
            var flwUsername = findFirst('flw_username');

            // Latest MUAC values (from most recent visit)
            var latestMuac = null;
            var latestMuacColor = null;
            for (var i = rows.length - 1; i >= 0; i--) {
                if (rows[i].muac_cm != null && rows[i].muac_cm !== '') {
                    latestMuac = parseFloat(rows[i].muac_cm);
                    break;
                }
            }
            for (var j = rows.length - 1; j >= 0; j--) {
                if (rows[j].muac_color != null && rows[j].muac_color !== '') {
                    latestMuacColor = rows[j].muac_color;
                    break;
                }
            }

            var visitCount = rows.length;
            var lastRow = rows[rows.length - 1];
            var lastVisitDate = lastRow ? (lastRow.fu_visit_date || lastRow.time_end) : null;
            var daysSinceLastVisit = daysSince(lastVisitDate);
            var isOverdue = daysSinceLastVisit != null ? daysSinceLastVisit > 14 : false;

            // Check if recovered
            var recovered = false;
            for (var k = rows.length - 1; k >= 0; k--) {
                if (rows[k].child_recovered === 'yes') {
                    recovered = true;
                    break;
                }
            }
            if (!recovered && latestMuacColor && String(latestMuacColor).toLowerCase() === 'green') {
                recovered = true;
            }

            // Referral compliance: count visits where visited_facility=yes
            var referralCompliance = 0;
            rows.forEach(function(r) {
                if (r.visited_facility && String(r.visited_facility).toLowerCase() === 'yes') {
                    referralCompliance++;
                }
            });

            return {
                child_case_id: caseId,
                child_name: childName,
                childs_age_in_month: childsAge,
                childs_gender: childsGender,
                childs_dob: childsDob,
                household_name: householdName,
                household_phone: householdPhone,
                hh_village_name: villageName,
                flw_username: flwUsername,
                latestMuac: latestMuac,
                latestMuacColor: latestMuacColor,
                visitCount: visitCount,
                lastVisitDate: lastVisitDate,
                daysSinceLastVisit: daysSinceLastVisit,
                isOverdue: isOverdue,
                recovered: recovered,
                referralCompliance: referralCompliance,
                visits: rows,
            };
        });
    }

    // --- Compute KPIs from grouped children ---
    function computeKPIs(children) {
        var totalChildren = children.length;
        var redCount = 0;
        var yellowCount = 0;
        var greenCount = 0;
        var overdueCount = 0;
        var totalReferralVisits = 0;
        var totalVisitsWithFacilityData = 0;

        children.forEach(function(c) {
            var color = c.latestMuacColor ? String(c.latestMuacColor).toLowerCase() : '';
            if (c.recovered || color === 'green') {
                greenCount++;
            } else if (color === 'red') {
                redCount++;
            } else if (color === 'yellow') {
                yellowCount++;
            }
            if (c.isOverdue) overdueCount++;

            c.visits.forEach(function(v) {
                if (v.visited_facility != null && v.visited_facility !== '') {
                    totalVisitsWithFacilityData++;
                    if (String(v.visited_facility).toLowerCase() === 'yes') {
                        totalReferralVisits++;
                    }
                }
            });
        });

        var referralCompliancePct = totalVisitsWithFacilityData > 0
            ? Math.round((totalReferralVisits / totalVisitsWithFacilityData) * 100)
            : 0;

        return {
            totalChildren: totalChildren,
            redCount: redCount,
            yellowCount: yellowCount,
            greenCount: greenCount,
            overdueCount: overdueCount,
            referralCompliancePct: referralCompliancePct,
        };
    }

    // ========================================================================
    // STATE
    // ========================================================================

    var _currentView = React.useState('dashboard');
    var currentView = _currentView[0];
    var setCurrentView = _currentView[1];

    var _selectedChildId = React.useState(null);
    var selectedChildId = _selectedChildId[0];
    var setSelectedChildId = _selectedChildId[1];

    var _childListFilter = React.useState('all');
    var childListFilter = _childListFilter[0];
    var setChildListFilter = _childListFilter[1];

    var _searchText = React.useState('');
    var searchText = _searchText[0];
    var setSearchText = _searchText[1];

    var _sortBy = React.useState('name');
    var sortBy = _sortBy[0];
    var setSortBy = _sortBy[1];

    var _sortDir = React.useState('asc');
    var sortDir = _sortDir[0];
    var setSortDir = _sortDir[1];

    var _selectedVisitIdx = React.useState(0);
    var selectedVisitIdx = _selectedVisitIdx[0];
    var setSelectedVisitIdx = _selectedVisitIdx[1];

    var _imageData = React.useState({});
    var imageData = _imageData[0];
    var setImageData = _imageData[1];

    var _imageLoading = React.useState(false);
    var imageLoading = _imageLoading[0];
    var setImageLoading = _imageLoading[1];

    var _expandedSections = React.useState({
        muac: true,
        referral: true,
        barriers: true,
        visit_info: true,
    });
    var expandedSections = _expandedSections[0];
    var setExpandedSections = _expandedSections[1];

    // --- Dashboard chart refs ---
    var muacDistChartRef = React.useRef(null);
    var muacDistChartInstance = React.useRef(null);
    var visitsChartRef = React.useRef(null);
    var visitsChartInstance = React.useRef(null);

    // --- Timeline chart refs ---
    var timelineChartRef = React.useRef(null);
    var timelineChartInstanceRef = React.useRef(null);

    // ========================================================================
    // COMPUTED DATA
    // ========================================================================

    var visitRows = pipelines && pipelines.visits ? (pipelines.visits.rows || []) : [];
    var children = React.useMemo(function() { return groupVisitsByChild(visitRows); }, [visitRows]);
    var kpis = React.useMemo(function() { return computeKPIs(children); }, [children]);

    // --- Weekly data for dashboard charts ---
    var weeklyData = React.useMemo(function() {
        if (children.length === 0) return { muacDist: [], visits: [] };

        // Helper: get ISO week string (YYYY-WXX)
        var getWeekKey = function(dateStr) {
            if (!dateStr) return null;
            var d = new Date(dateStr);
            if (isNaN(d.getTime())) return null;
            var jan1 = new Date(d.getFullYear(), 0, 1);
            var weekNum = Math.ceil(((d - jan1) / 86400000 + jan1.getDay() + 1) / 7);
            return d.getFullYear() + '-W' + String(weekNum).padStart(2, '0');
        };

        // Get the Monday date for a week key
        var weekKeyToDate = function(weekKey) {
            var parts = weekKey.split('-W');
            var year = parts[0];
            var wStr = parts[1];
            var jan1 = new Date(parseInt(year), 0, 1);
            var dayOffset = (jan1.getDay() + 6) % 7;
            var firstMonday = new Date(jan1);
            firstMonday.setDate(jan1.getDate() - dayOffset);
            firstMonday.setDate(firstMonday.getDate() + (parseInt(wStr) - 1) * 7);
            return firstMonday.toISOString().split('T')[0];
        };

        // MUAC distribution by week: count red/yellow/green per week
        var muacByWeek = {};
        var visitsByWeek = {};

        children.forEach(function(c) {
            c.visits.forEach(function(v) {
                var dateStr = v.fu_visit_date || v.time_end;
                var week = getWeekKey(dateStr);
                if (!week) return;

                // Visit count per week
                visitsByWeek[week] = (visitsByWeek[week] || 0) + 1;

                // MUAC color per week
                var color = v.muac_color ? String(v.muac_color).toLowerCase() : '';
                if (!muacByWeek[week]) {
                    muacByWeek[week] = { red: 0, yellow: 0, green: 0 };
                }
                if (color === 'red') muacByWeek[week].red++;
                else if (color === 'yellow') muacByWeek[week].yellow++;
                else if (color === 'green') muacByWeek[week].green++;
            });
        });

        var allWeeks = Object.keys(muacByWeek).concat(Object.keys(visitsByWeek));
        var uniqueWeeks = [];
        var seen = {};
        allWeeks.forEach(function(w) {
            if (!seen[w]) {
                seen[w] = true;
                uniqueWeeks.push(w);
            }
        });
        uniqueWeeks.sort();

        var muacDist = uniqueWeeks.map(function(week) {
            var data = muacByWeek[week] || { red: 0, yellow: 0, green: 0 };
            return { week: week, date: weekKeyToDate(week), red: data.red, yellow: data.yellow, green: data.green };
        });

        var visits = uniqueWeeks.map(function(week) {
            return { week: week, date: weekKeyToDate(week), count: visitsByWeek[week] || 0 };
        });

        return { muacDist: muacDist, visits: visits };
    }, [children]);

    // ========================================================================
    // DASHBOARD CHARTS
    // ========================================================================

    // --- MUAC Color Distribution Over Time (stacked bar) ---
    React.useEffect(function() {
        if (currentView !== 'dashboard') return;
        if (!muacDistChartRef.current || !window.Chart || weeklyData.muacDist.length === 0) return;

        if (muacDistChartInstance.current) muacDistChartInstance.current.destroy();

        var ctx = muacDistChartRef.current.getContext('2d');
        muacDistChartInstance.current = new window.Chart(ctx, {
            type: 'bar',
            data: {
                labels: weeklyData.muacDist.map(function(d) { return d.date; }),
                datasets: [
                    {
                        label: 'Red (SAM)',
                        data: weeklyData.muacDist.map(function(d) { return d.red; }),
                        backgroundColor: 'rgba(239, 68, 68, 0.7)',
                        borderColor: '#ef4444',
                        borderWidth: 1,
                    },
                    {
                        label: 'Yellow (MAM)',
                        data: weeklyData.muacDist.map(function(d) { return d.yellow; }),
                        backgroundColor: 'rgba(245, 158, 11, 0.7)',
                        borderColor: '#f59e0b',
                        borderWidth: 1,
                    },
                    {
                        label: 'Green (Normal)',
                        data: weeklyData.muacDist.map(function(d) { return d.green; }),
                        backgroundColor: 'rgba(16, 185, 129, 0.7)',
                        borderColor: '#10b981',
                        borderWidth: 1,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: true, position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } },
                },
                scales: {
                    x: {
                        type: 'time',
                        time: { unit: 'week', tooltipFormat: 'MMM d, yyyy' },
                        stacked: true,
                        title: { display: false },
                        ticks: { font: { size: 10 } },
                    },
                    y: {
                        stacked: true,
                        beginAtZero: true,
                        title: { display: false },
                        ticks: { font: { size: 10 }, stepSize: 1 },
                    },
                },
            },
        });

        return function() {
            if (muacDistChartInstance.current) {
                muacDistChartInstance.current.destroy();
                muacDistChartInstance.current = null;
            }
        };
    }, [currentView, weeklyData]);

    // --- Follow-up Visits Per Week (bar) ---
    React.useEffect(function() {
        if (currentView !== 'dashboard') return;
        if (!visitsChartRef.current || !window.Chart || weeklyData.visits.length === 0) return;

        if (visitsChartInstance.current) visitsChartInstance.current.destroy();

        var ctx = visitsChartRef.current.getContext('2d');
        visitsChartInstance.current = new window.Chart(ctx, {
            type: 'bar',
            data: {
                labels: weeklyData.visits.map(function(d) { return d.date; }),
                datasets: [{
                    label: 'Visits',
                    data: weeklyData.visits.map(function(d) { return d.count; }),
                    backgroundColor: 'rgba(59, 130, 246, 0.6)',
                    borderColor: '#3b82f6',
                    borderWidth: 1,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                },
                scales: {
                    x: {
                        type: 'time',
                        time: { unit: 'week', tooltipFormat: 'MMM d, yyyy' },
                        title: { display: false },
                        ticks: { font: { size: 10 } },
                    },
                    y: {
                        beginAtZero: true,
                        title: { display: false },
                        ticks: { font: { size: 10 }, stepSize: 1 },
                    },
                },
            },
        });

        return function() {
            if (visitsChartInstance.current) {
                visitsChartInstance.current.destroy();
                visitsChartInstance.current = null;
            }
        };
    }, [currentView, weeklyData]);

    // ========================================================================
    // LOADING & EMPTY STATES
    // ========================================================================

    if (!pipelines || !pipelines.visits || !pipelines.visits.rows) {
        return (
            <div className="flex items-center justify-center py-20">
                <div className="text-center">
                    <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-gray-200 border-t-blue-600 mb-4"></div>
                    <p className="text-gray-500 text-sm">Loading visit data...</p>
                </div>
            </div>
        );
    }

    if (visitRows.length === 0) {
        return (
            <div className="text-center py-16">
                <div className="inline-block p-4 rounded-full bg-gray-100 mb-4">
                    <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
                    </svg>
                </div>
                <p className="text-gray-500 text-lg">No SAM follow-up visit data found</p>
                <p className="text-gray-400 text-sm mt-1">Pipeline data may still be loading, or no visits have been recorded for this opportunity.</p>
            </div>
        );
    }

    // ========================================================================
    // HANDLERS
    // ========================================================================

    function handleCardClick(filter) {
        setChildListFilter(filter);
        setCurrentView('childList');
    }

    function handleBackToDashboard() {
        setCurrentView('dashboard');
        setSelectedChildId(null);
        setChildListFilter('all');
    }

    // ========================================================================
    // TIMELINE HOOKS (at parent level to avoid remount loops)
    // ========================================================================

    // Derive selected child data (safe when no child selected)
    var timelineChild = selectedChildId ? children.find(function(c) { return c.child_case_id === selectedChildId; }) : null;
    var timelineSortedVisits = timelineChild ? timelineChild.visits.slice().reverse() : [];

    // --- MUAC Trend Chart (deferred to allow canvas to mount) ---
    React.useEffect(function() {
        if (!timelineChild || currentView !== 'timeline') return;
        if (!window.Chart) return;

        // Defer to next frame so the canvas element is in the DOM
        var frameId = requestAnimationFrame(function() {
            if (!timelineChartRef.current) return;
            renderTimelineChart();
        });
        return function() {
            cancelAnimationFrame(frameId);
            if (timelineChartInstanceRef.current) {
                timelineChartInstanceRef.current.destroy();
                timelineChartInstanceRef.current = null;
            }
        };

        function renderTimelineChart() {
        if (!timelineChartRef.current) return;

        var chartVisits = timelineChild.visits.filter(function(v) { return v.muac_cm != null && v.muac_cm !== ''; });
        if (chartVisits.length === 0) return;

        if (timelineChartInstanceRef.current) {
            timelineChartInstanceRef.current.destroy();
        }

        var chartLabels = chartVisits.map(function(v) { return v.fu_visit_date || v.time_end; });
        var chartMuacs = chartVisits.map(function(v) { return parseFloat(v.muac_cm); });

        var selVisit = timelineSortedVisits[selectedVisitIdx];
        var selectedChartIdx = selVisit ? chartVisits.findIndex(function(v) { return v === selVisit; }) : -1;

        var pointBackgroundColors = chartMuacs.map(function(m, i) {
            if (i === selectedChartIdx) return '#3b82f6';
            if (m < 11.5) return '#ef4444';
            if (m <= 12.5) return '#f59e0b';
            return '#10b981';
        });
        var pointRadii = chartMuacs.map(function(_, i) { return i === selectedChartIdx ? 8 : 4; });

        var ctx = timelineChartRef.current.getContext('2d');
        timelineChartInstanceRef.current = new window.Chart(ctx, {
            type: 'line',
            data: {
                labels: chartLabels,
                datasets: [
                    {
                        label: 'MUAC (cm)',
                        data: chartMuacs,
                        borderColor: '#6b7280',
                        backgroundColor: 'rgba(107, 114, 128, 0.1)',
                        fill: true,
                        tension: 0.3,
                        pointBackgroundColor: pointBackgroundColors,
                        pointBorderColor: pointBackgroundColors,
                        pointRadius: pointRadii,
                        pointHoverRadius: 8,
                    },
                    {
                        label: 'SAM (11.5 cm)',
                        data: chartLabels.map(function() { return 11.5; }),
                        borderColor: '#ef4444',
                        borderDash: [6, 4],
                        borderWidth: 1,
                        pointRadius: 0,
                        fill: false,
                    },
                    {
                        label: 'MAM (12.5 cm)',
                        data: chartLabels.map(function() { return 12.5; }),
                        borderColor: '#f59e0b',
                        borderDash: [6, 4],
                        borderWidth: 1,
                        pointRadius: 0,
                        fill: false,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                onClick: function(e, elements) {
                    if (elements.length > 0) {
                        var chartIdx = elements[0].index;
                        var clickedVisit = chartVisits[chartIdx];
                        var sortedIdx = timelineSortedVisits.findIndex(function(v) { return v === clickedVisit; });
                        if (sortedIdx >= 0) {
                            setSelectedVisitIdx(sortedIdx);
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'bottom',
                        labels: { boxWidth: 12, font: { size: 11 } },
                    },
                    tooltip: {
                        callbacks: {
                            label: function(tooltipCtx) {
                                if (tooltipCtx.datasetIndex === 0) {
                                    return tooltipCtx.parsed.y.toFixed(1) + ' cm';
                                }
                                return tooltipCtx.dataset.label + ': ' + tooltipCtx.parsed.y + ' cm';
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        type: 'time',
                        time: { unit: 'day', tooltipFormat: 'MMM d, yyyy' },
                        title: { display: true, text: 'Visit Date', font: { size: 11 } },
                    },
                    y: {
                        title: { display: true, text: 'MUAC (cm)', font: { size: 11 } },
                        beginAtZero: false,
                    },
                },
            },
        });

        }
    }, [selectedChildId, currentView, selectedVisitIdx]);

    // --- Photo filmstrip: JIT loading ---
    React.useEffect(function() {
        if (!selectedChildId || currentView !== 'timeline') return;
        if (!timelineChild) return;
        var visitIds = timelineChild.visits.map(function(v) { return v.id; }).filter(Boolean);
        if (visitIds.length === 0) return;
        setImageLoading(true);
        var opportunityId = instance.opportunity_id;
        var url = '/labs/workflow/api/' + opportunityId + '/visit-images/?visit_ids=' + visitIds.join(',');
        fetch(url, { credentials: 'same-origin' })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                setImageData(data.visit_images || {});
                setImageLoading(false);
            })
            .catch(function() { setImageLoading(false); });
    }, [selectedChildId, currentView]);

    // --- Build photo filmstrip data ---
    var filmstripPhotos = React.useMemo(function() {
        if (!timelineChild) return [];
        var photos = [];
        timelineChild.visits.forEach(function(visit, visitIdx) {
            var visitId = visit.id;
            if (!visitId || !imageData[visitId]) return;
            var images = imageData[visitId];
            images.forEach(function(img) {
                if (!img.blob_id) return;
                var opportunityId = instance.opportunity_id;
                photos.push({
                    visitIdx: visitIdx,
                    visit: visit,
                    url: '/labs/workflow/api/image/' + opportunityId + '/' + img.blob_id + '/',
                    date: visit.fu_visit_date || visit.time_end,
                    muacColor: visit.muac_color,
                    muacCm: visit.muac_cm,
                });
            });
        });
        return photos;
    }, [selectedChildId, imageData]);

    // ========================================================================
    // CHILD TIMELINE VIEW
    // ========================================================================

    function ChildTimeline() {
        if (!timelineChild) return <div className="p-8 text-center text-gray-500">Child not found</div>;

        var child = timelineChild;
        var sortedVisits = timelineSortedVisits;
        var selectedVisit = sortedVisits[selectedVisitIdx] || {};

        var toggleSection = function(key) {
            var updated = {};
            Object.keys(expandedSections).forEach(function(k) {
                updated[k] = k === key ? !expandedSections[k] : expandedSections[k];
            });
            setExpandedSections(updated);
        };

        // --- Detail sections for selected visit ---
        var detailSections = [
            {
                key: 'muac',
                title: 'MUAC',
                fields: [
                    { label: 'Measurement', value: selectedVisit.muac_cm, suffix: ' cm' },
                    { label: 'Color', value: selectedVisit.muac_color, isBadge: true },
                    { label: 'Caregiver Report', value: selectedVisit.child_status_reported },
                ],
            },
            {
                key: 'referral',
                title: 'Referral',
                show: true,
                fields: [
                    { label: 'Visited Facility', value: selectedVisit.visited_facility },
                    { label: 'Which Facility', value: selectedVisit.which_facility_visited },
                    { label: 'Treatment Received', value: selectedVisit.treatment_received },
                    { label: 'Adherence', value: selectedVisit.treatment_adherence },
                    { label: 'Satisfaction', value: selectedVisit.caregiver_satisfaction },
                ],
            },
            {
                key: 'barriers',
                title: 'Barriers',
                show: selectedVisit.visited_facility && String(selectedVisit.visited_facility).toLowerCase() !== 'yes',
                fields: [
                    { label: 'Reason Not Visited', value: selectedVisit.reason_no_visit },
                ],
            },
            {
                key: 'visit_info',
                title: 'Visit Info',
                fields: [
                    { label: 'Date', value: selectedVisit.fu_visit_date },
                    { label: 'Follow-up #', value: selectedVisit.followup_number },
                    { label: 'Delivery Status', value: selectedVisit.delivery_status },
                ],
            },
        ];

        var visibleSections = detailSections.filter(function(s) {
            return s.show !== false;
        });

        var chartVisits = child.visits.filter(function(v) { return v.muac_cm != null && v.muac_cm !== ''; });

        var handleBackToList = function() {
            setCurrentView('childList');
            setSelectedChildId(null);
            setSelectedVisitIdx(0);
        };

        // Status badge
        var getStatusBadge = function() {
            if (child.recovered) {
                return { label: 'Recovered', bg: 'bg-green-100', text: 'text-green-800' };
            }
            var color = child.latestMuacColor ? String(child.latestMuacColor).toLowerCase() : '';
            if (child.isOverdue) {
                return { label: 'Lost to Follow-up', bg: 'bg-gray-100', text: 'text-gray-800' };
            }
            if (color === 'red') {
                return { label: 'SAM (Red)', bg: 'bg-red-100', text: 'text-red-800' };
            }
            if (color === 'yellow') {
                return { label: 'MAM (Yellow)', bg: 'bg-yellow-100', text: 'text-yellow-800' };
            }
            return { label: 'Active', bg: 'bg-blue-100', text: 'text-blue-800' };
        };
        var status = getStatusBadge();

        return (
            <div className="space-y-4">
                {/* 3-column body layout */}
                <div style={{display: 'grid', gridTemplateColumns: '256px 1fr 384px', gap: '16px'}}>
                    {/* Left: Visit History Sidebar */}
                    <div className="bg-white rounded-lg shadow-sm overflow-hidden" style={{borderRight: '1px solid #e5e7eb'}}>
                        <div className="px-3 py-2 bg-gray-50 border-b">
                            <button
                                onClick={handleBackToList}
                                className="inline-flex items-center text-sm text-blue-600 hover:text-blue-800 font-medium mb-2"
                            >
                                &larr; Back to List
                            </button>
                            <div className="text-xs font-medium text-gray-500 uppercase">
                                Visits ({child.visits.length})
                            </div>
                        </div>
                        <div style={{maxHeight: '500px', overflowY: 'auto'}}>
                            {sortedVisits.map(function(visit, idx) {
                                var muacDot = getMuacDotColor(visit.muac_color);
                                var muacVal = visit.muac_cm != null && visit.muac_cm !== '' ? parseFloat(visit.muac_cm).toFixed(1) : null;
                                return (
                                    <div
                                        key={idx}
                                        onClick={function() { setSelectedVisitIdx(idx); }}
                                        className={
                                            "px-3 py-2 cursor-pointer border-b border-gray-50 " +
                                            (selectedVisitIdx === idx ? "bg-blue-50 border-l-2 border-l-blue-500" : "hover:bg-gray-50")
                                        }
                                    >
                                        <div className="flex items-center gap-2">
                                            <span style={{
                                                display: 'inline-block',
                                                width: '10px',
                                                height: '10px',
                                                borderRadius: '50%',
                                                backgroundColor: muacDot,
                                                flexShrink: 0,
                                            }}></span>
                                            <div className="text-sm font-medium text-gray-900">
                                                {'Follow-up #' + (visit.followup_number || (child.visits.length - idx))}
                                            </div>
                                        </div>
                                        <div className="text-xs text-gray-500 ml-5">
                                            {visit.fu_visit_date || 'No date'}
                                        </div>
                                        {muacVal && (
                                            <div className="text-xs text-gray-600 mt-0.5 ml-5">
                                                {muacVal + ' cm'}
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    </div>

                    {/* Center: MUAC Trend Chart + Photo Filmstrip */}
                    <div className="space-y-4">
                        <div className="bg-white rounded-lg shadow-sm p-4">
                            <h3 className="text-sm font-medium text-gray-700 mb-2">MUAC Trend</h3>
                            {chartVisits.length > 0 ? (
                                <div style={{height: '250px'}}>
                                    <canvas ref={timelineChartRef}></canvas>
                                </div>
                            ) : (
                                <p className="text-gray-400 text-sm text-center py-8">No MUAC data available</p>
                            )}
                        </div>

                        {/* MUAC Photo Filmstrip */}
                        <div className="bg-white rounded-lg shadow-sm p-4">
                            <div className="flex items-center justify-between mb-3">
                                <h3 className="text-sm font-medium text-gray-700">MUAC Photos</h3>
                                {!imageLoading && filmstripPhotos.length > 0 && (
                                    <span className="text-xs text-gray-400">{filmstripPhotos.length} photo{filmstripPhotos.length !== 1 ? 's' : ''}</span>
                                )}
                            </div>
                            {imageLoading ? (
                                <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: '8px'}}>
                                    {[0,1,2,3].map(function(i) {
                                        return (
                                            <div key={i} style={{borderRadius: '8px', overflow: 'hidden', backgroundColor: '#f3f4f6'}}>
                                                <div className="animate-pulse" style={{width: '100%', height: '100px', backgroundColor: '#e5e7eb'}}></div>
                                                <div style={{padding: '6px', textAlign: 'center'}}>
                                                    <div className="animate-pulse" style={{height: '10px', backgroundColor: '#e5e7eb', borderRadius: '4px', width: '75%', margin: '0 auto 4px'}}></div>
                                                    <div className="animate-pulse" style={{height: '10px', backgroundColor: '#e5e7eb', borderRadius: '4px', width: '50%', margin: '0 auto'}}></div>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            ) : filmstripPhotos.length > 0 ? (
                                <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: '8px', maxHeight: '320px', overflowY: 'auto'}}>
                                    {filmstripPhotos.map(function(photo, pIdx) {
                                        var isSelected = photo.visitIdx === (child.visits.length - 1 - selectedVisitIdx);
                                        return (
                                            <div
                                                key={pIdx}
                                                onClick={function() {
                                                    var sortedIdx = child.visits.length - 1 - photo.visitIdx;
                                                    setSelectedVisitIdx(sortedIdx);
                                                }}
                                                style={{
                                                    border: isSelected ? '2px solid #3b82f6' : '1px solid #e5e7eb',
                                                    borderRadius: '8px',
                                                    overflow: 'hidden',
                                                    cursor: 'pointer',
                                                    backgroundColor: '#fff',
                                                }}
                                            >
                                                <img
                                                    src={photo.url}
                                                    alt="MUAC photo"
                                                    style={{width: '100%', height: '100px', objectFit: 'cover', display: 'block'}}
                                                />
                                                <div style={{padding: '4px 6px', textAlign: 'center'}}>
                                                    <div style={{fontSize: '11px', color: '#6b7280'}}>{photo.date || ''}</div>
                                                    {photo.muacCm && (
                                                        <div style={{fontSize: '11px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '4px'}}>
                                                            <span style={{
                                                                display: 'inline-block',
                                                                width: '8px',
                                                                height: '8px',
                                                                borderRadius: '50%',
                                                                backgroundColor: getMuacDotColor(photo.muacColor),
                                                            }}></span>
                                                            {parseFloat(photo.muacCm).toFixed(1) + ' cm'}
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            ) : (
                                <p className="text-gray-400 text-sm text-center py-4">No MUAC photos available</p>
                            )}
                        </div>
                    </div>

                    {/* Right: Detail Panel */}
                    <div className="bg-white rounded-lg shadow-sm overflow-hidden" style={{borderLeft: '1px solid #e5e7eb'}}>
                        {/* Header card: child name, status, age/gender */}
                        <div className="px-4 py-3 bg-gray-50 border-b">
                            <div className="flex items-center justify-between">
                                <h3 className="text-sm font-semibold text-gray-900">
                                    {child.child_name || 'Unknown Child'}
                                </h3>
                                <span className={"inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium " + status.bg + " " + status.text}>
                                    {status.label}
                                </span>
                            </div>
                            <p className="text-xs text-gray-500 mt-1">
                                {child.childs_age_in_month ? child.childs_age_in_month + ' months' : ''}
                                {child.childs_age_in_month && child.childs_gender ? ' \\u2022 ' : ''}
                                {child.childs_gender || ''}
                            </p>
                        </div>

                        {/* Info grid */}
                        <div className="px-4 py-3 border-b border-gray-100">
                            <div className="grid grid-cols-2 gap-2">
                                <div>
                                    <span className="text-xs text-gray-500">DOB</span>
                                    <div className="text-sm text-gray-900">{child.childs_dob || '-'}</div>
                                </div>
                                <div>
                                    <span className="text-xs text-gray-500">Village</span>
                                    <div className="text-sm text-gray-900">{child.hh_village_name || '-'}</div>
                                </div>
                                <div>
                                    <span className="text-xs text-gray-500">Household</span>
                                    <div className="text-sm text-gray-900">{child.household_name || '-'}</div>
                                </div>
                                <div>
                                    <span className="text-xs text-gray-500">Phone</span>
                                    <div className="text-sm text-gray-900">{child.household_phone || '-'}</div>
                                </div>
                                <div>
                                    <span className="text-xs text-gray-500">FLW</span>
                                    <div className="text-sm text-gray-900">{child.flw_username || '-'}</div>
                                </div>
                                <div>
                                    <span className="text-xs text-gray-500">Total Follow-ups</span>
                                    <div className="text-sm text-gray-900">{child.visitCount}</div>
                                </div>
                            </div>
                        </div>

                        {/* Selected visit details (collapsible sections) */}
                        <div className="px-4 py-2 bg-gray-50 border-b">
                            <h4 className="text-xs font-medium text-gray-500 uppercase">
                                {'Follow-up #' + (selectedVisit.followup_number || '')} Details
                            </h4>
                        </div>
                        <div style={{maxHeight: '360px', overflowY: 'auto'}}>
                            {visibleSections.map(function(section) {
                                return (
                                    <div key={section.key} className="border-b border-gray-100 last:border-b-0">
                                        <button
                                            onClick={function() { toggleSection(section.key); }}
                                            className="w-full px-4 py-2 flex justify-between items-center text-left hover:bg-gray-50"
                                        >
                                            <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                                                {section.title}
                                            </span>
                                            <span className="text-gray-400 text-xs">
                                                {expandedSections[section.key] ? '\\u25B2' : '\\u25BC'}
                                            </span>
                                        </button>
                                        {expandedSections[section.key] && (
                                            <div className="px-4 pb-3">
                                                {section.fields.map(function(field) {
                                                    return (
                                                        <div key={field.label} className="flex justify-between py-1">
                                                            <span className="text-xs text-gray-500">{field.label}</span>
                                                            <span className="text-sm text-gray-900 text-right">
                                                                {field.isBadge && field.value ? (
                                                                    <span className={"inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium " + getMuacColorClass(field.value)}>
                                                                        {field.value}
                                                                    </span>
                                                                ) : (
                                                                    formatValue(field.value, field.suffix)
                                                                )}
                                                            </span>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    // ========================================================================
    // CHILD LIST VIEW
    // ========================================================================

    function ChildList() {
        var filterOptions = [
            { value: 'all', label: 'All' },
            { value: 'red', label: 'Red MUAC' },
            { value: 'yellow', label: 'Yellow MUAC' },
            { value: 'green', label: 'Green / Recovered' },
            { value: 'overdue', label: 'Overdue' },
            { value: 'no_facility', label: 'Not Visiting Facility' },
        ];

        // Apply status filter
        var statusFiltered = children.filter(function(child) {
            if (childListFilter === 'all') return true;
            var color = child.latestMuacColor ? String(child.latestMuacColor).toLowerCase() : '';
            if (childListFilter === 'red') return color === 'red';
            if (childListFilter === 'yellow') return color === 'yellow';
            if (childListFilter === 'green') return child.recovered || color === 'green';
            if (childListFilter === 'overdue') return child.isOverdue;
            if (childListFilter === 'no_facility') {
                // Check if most recent visit has visited_facility !== 'yes'
                var lastVisit = child.visits[child.visits.length - 1];
                return lastVisit && lastVisit.visited_facility && String(lastVisit.visited_facility).toLowerCase() !== 'yes';
            }
            return true;
        });

        // Apply search filter
        var filteredChildren = statusFiltered.filter(function(child) {
            if (!searchText) return true;
            var q = searchText.toLowerCase();
            var cn = (child.child_name || '').toLowerCase();
            var hn = (child.household_name || '').toLowerCase();
            return cn.indexOf(q) !== -1 || hn.indexOf(q) !== -1;
        });

        // Sort
        var handleSort = function(col) {
            if (sortBy === col) {
                setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
            } else {
                setSortBy(col);
                setSortDir('asc');
            }
        };

        var sortedChildren = filteredChildren.slice().sort(function(a, b) {
            var cmp = 0;
            if (sortBy === 'name') cmp = (a.child_name || '').localeCompare(b.child_name || '');
            else if (sortBy === 'age') cmp = (parseInt(a.childs_age_in_month) || 0) - (parseInt(b.childs_age_in_month) || 0);
            else if (sortBy === 'muacColor') {
                var order = { red: 0, yellow: 1, green: 2 };
                var ac = a.latestMuacColor ? String(a.latestMuacColor).toLowerCase() : '';
                var bc = b.latestMuacColor ? String(b.latestMuacColor).toLowerCase() : '';
                cmp = (order[ac] != null ? order[ac] : 3) - (order[bc] != null ? order[bc] : 3);
            }
            else if (sortBy === 'muac') cmp = (a.latestMuac || 0) - (b.latestMuac || 0);
            else if (sortBy === 'visits') cmp = a.visitCount - b.visitCount;
            else if (sortBy === 'lastVisit') cmp = (daysSince(a.lastVisitDate) || 9999) - (daysSince(b.lastVisitDate) || 9999);
            else if (sortBy === 'facility') {
                var aFac = a.visits.length > 0 && a.visits[a.visits.length - 1].visited_facility;
                var bFac = b.visits.length > 0 && b.visits[b.visits.length - 1].visited_facility;
                cmp = String(aFac || '').localeCompare(String(bFac || ''));
            }
            else if (sortBy === 'flw') cmp = (a.flw_username || '').localeCompare(b.flw_username || '');
            return sortDir === 'asc' ? cmp : -cmp;
        });

        var sortArrow = function(col) {
            if (sortBy !== col) return '';
            return sortDir === 'asc' ? ' \\u2191' : ' \\u2193';
        };

        var columns = [
            { key: 'name', label: 'Child Name' },
            { key: 'age', label: 'Age' },
            { key: 'muacColor', label: 'MUAC Color' },
            { key: 'muac', label: 'MUAC (cm)' },
            { key: 'visits', label: 'Follow-ups' },
            { key: 'lastVisit', label: 'Last Visit' },
            { key: 'facility', label: 'Facility Visited' },
            { key: 'flw', label: 'FLW' },
        ];

        return (
            <div className="space-y-4">
                {/* Filter bar */}
                <div className="bg-white rounded-lg shadow-sm p-4 flex flex-wrap items-center gap-4">
                    <button
                        onClick={handleBackToDashboard}
                        className="inline-flex items-center text-sm text-blue-600 hover:text-blue-800 font-medium"
                    >
                        &larr; Back to Dashboard
                    </button>
                    <select
                        value={childListFilter}
                        onChange={function(e) { setChildListFilter(e.target.value); }}
                        className="border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                        {filterOptions.map(function(opt) {
                            return <option key={opt.value} value={opt.value}>{opt.label}</option>;
                        })}
                    </select>
                    <input
                        type="text"
                        placeholder="Search by child or household name..."
                        value={searchText}
                        onChange={function(e) { setSearchText(e.target.value); }}
                        className="border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 flex-1 min-w-[200px]"
                    />
                    <span className="text-sm text-gray-500">
                        {'Showing ' + sortedChildren.length + ' of ' + children.length + ' children'}
                    </span>
                </div>

                {/* Table */}
                <div className="bg-white rounded-lg shadow-sm overflow-hidden">
                    <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200">
                            <thead className="bg-gray-50">
                                <tr>
                                    {columns.map(function(col) {
                                        return (
                                            <th
                                                key={col.key}
                                                onClick={function() { handleSort(col.key); }}
                                                className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none"
                                            >
                                                {col.label}{sortArrow(col.key)}
                                            </th>
                                        );
                                    })}
                                </tr>
                            </thead>
                            <tbody className="bg-white divide-y divide-gray-100">
                                {sortedChildren.length === 0 ? (
                                    <tr>
                                        <td colSpan={columns.length} className="px-4 py-8 text-center text-gray-400 text-sm">
                                            No children match the current filters.
                                        </td>
                                    </tr>
                                ) : (
                                    sortedChildren.map(function(child) {
                                        var daysAgo = daysSince(child.lastVisitDate);
                                        var lastVisitText = daysAgo != null ? (daysAgo === 0 ? 'Today' : daysAgo + ' days ago') : '-';
                                        var lastVisitClass = daysAgo != null && daysAgo > 14 ? 'text-red-600 font-medium' : 'text-gray-700';
                                        var muacText = child.latestMuac != null ? child.latestMuac.toFixed(1) : '-';
                                        var lastVisitObj = child.visits.length > 0 ? child.visits[child.visits.length - 1] : null;
                                        var facilityText = lastVisitObj && lastVisitObj.visited_facility ? lastVisitObj.visited_facility : '-';

                                        return (
                                            <tr
                                                key={child.child_case_id}
                                                onClick={function() { setSelectedChildId(child.child_case_id); setCurrentView('timeline'); setSelectedVisitIdx(0); }}
                                                className="hover:bg-gray-50 cursor-pointer border-b border-gray-100"
                                            >
                                                <td className="px-4 py-3 text-sm text-gray-900">
                                                    <div className="flex items-center gap-1.5">
                                                        {child.isOverdue && (
                                                            <span className="inline-block w-2 h-2 rounded-full bg-orange-400 flex-shrink-0" title="Overdue"></span>
                                                        )}
                                                        <span>{child.child_name || 'Unknown'}</span>
                                                    </div>
                                                </td>
                                                <td className="px-4 py-3 text-sm text-gray-700">
                                                    {child.childs_age_in_month ? child.childs_age_in_month + 'mo' : '-'}
                                                </td>
                                                <td className="px-4 py-3 text-sm">
                                                    {child.latestMuacColor ? (
                                                        <span className={"inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium " + getMuacColorClass(child.latestMuacColor)}>
                                                            {child.latestMuacColor}
                                                        </span>
                                                    ) : (
                                                        <span className="text-gray-400">-</span>
                                                    )}
                                                </td>
                                                <td className="px-4 py-3 text-sm text-gray-700">{muacText}</td>
                                                <td className="px-4 py-3 text-sm text-gray-700">{child.visitCount}</td>
                                                <td className={"px-4 py-3 text-sm " + lastVisitClass}>{lastVisitText}</td>
                                                <td className="px-4 py-3 text-sm text-gray-700">{facilityText}</td>
                                                <td className="px-4 py-3 text-sm text-gray-700">{child.flw_username || '-'}</td>
                                            </tr>
                                        );
                                    })
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        );
    }

    // ========================================================================
    // NAVIGATION BAR
    // ========================================================================

    function NavigationBar() {
        var selectedChild = selectedChildId ? children.find(function(c) { return c.child_case_id === selectedChildId; }) : null;

        return (
            <div className="flex items-center gap-1 mb-4 border-b border-gray-200">
                <button
                    onClick={handleBackToDashboard}
                    className={"px-4 py-2 text-sm font-medium border-b-2 -mb-px " +
                        (currentView === 'dashboard'
                            ? "border-blue-500 text-blue-600"
                            : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300")}
                >
                    Dashboard
                </button>
                <button
                    onClick={function() { setCurrentView('childList'); }}
                    className={"px-4 py-2 text-sm font-medium border-b-2 -mb-px " +
                        (currentView === 'childList'
                            ? "border-blue-500 text-blue-600"
                            : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300")}
                >
                    {'All Children (' + children.length + ')'}
                </button>
                {currentView === 'timeline' && selectedChild && (
                    <button
                        className="px-4 py-2 text-sm font-medium border-b-2 -mb-px border-blue-500 text-blue-600"
                    >
                        {selectedChild.child_name || 'Child'}
                    </button>
                )}
            </div>
        );
    }

    // ========================================================================
    // VIEW ROUTER
    // ========================================================================

    if (currentView === 'timeline' && selectedChildId) {
        return (
            <div>
                {NavigationBar()}
                {ChildTimeline()}
            </div>
        );
    }
    if (currentView === 'childList') {
        return (
            <div>
                {NavigationBar()}
                {ChildList()}
            </div>
        );
    }

    // ========================================================================
    // DASHBOARD VIEW
    // ========================================================================

    var kpiCards = [
        {
            label: 'Total Children',
            value: kpis.totalChildren,
            bgColor: 'bg-gray-50',
            textColor: 'text-gray-900',
            borderColor: 'border-gray-400',
            filter: 'all',
        },
        {
            label: 'Red MUAC / SAM',
            value: kpis.redCount,
            bgColor: 'bg-red-50',
            textColor: 'text-red-900',
            borderColor: 'border-red-500',
            filter: 'red',
        },
        {
            label: 'Yellow MUAC / MAM',
            value: kpis.yellowCount,
            bgColor: 'bg-yellow-50',
            textColor: 'text-yellow-900',
            borderColor: 'border-yellow-500',
            filter: 'yellow',
        },
        {
            label: 'Green / Recovered',
            value: kpis.greenCount,
            bgColor: 'bg-green-50',
            textColor: 'text-green-900',
            borderColor: 'border-green-500',
            filter: 'green',
        },
        {
            label: 'Referral Compliance',
            value: kpis.referralCompliancePct + '%',
            bgColor: 'bg-blue-50',
            textColor: 'text-blue-900',
            borderColor: 'border-blue-500',
            filter: null,
        },
        {
            label: 'Overdue >14d',
            value: kpis.overdueCount,
            bgColor: 'bg-orange-50',
            textColor: 'text-orange-900',
            borderColor: 'border-orange-500',
            filter: 'overdue',
        },
    ];

    var totalVisits = children.reduce(function(sum, c) { return sum + c.visitCount; }, 0);

    return (
        <div>
            {NavigationBar()}
            <div className="space-y-6">
                {/* KPI Cards */}
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                    {kpiCards.map(function(card, idx) {
                        return (
                            <div
                                key={idx}
                                onClick={card.filter ? function() { handleCardClick(card.filter); } : undefined}
                                className={"rounded-lg shadow-sm p-5 border-l-4 " + card.bgColor + " " + card.borderColor + (card.filter ? " cursor-pointer hover:shadow-md transition-shadow" : "")}
                            >
                                <div className={"text-3xl font-bold " + card.textColor}>{card.value}</div>
                                <div className="text-sm text-gray-600 mt-1">{card.label}</div>
                            </div>
                        );
                    })}
                </div>

                {/* View All Children button */}
                <div className="flex justify-end">
                    <button
                        onClick={function() { setCurrentView('childList'); }}
                        className="text-sm text-blue-600 hover:text-blue-800 font-medium"
                    >
                        {'View All Children \\u2192'}
                    </button>
                </div>

                {/* Charts */}
                {weeklyData.muacDist.length > 0 && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="bg-white rounded-lg shadow-sm p-4">
                            <h3 className="text-sm font-medium text-gray-700 mb-2">MUAC Color Distribution Over Time</h3>
                            <div style={{height: '200px'}}>
                                <canvas ref={muacDistChartRef}></canvas>
                            </div>
                        </div>
                        <div className="bg-white rounded-lg shadow-sm p-4">
                            <h3 className="text-sm font-medium text-gray-700 mb-2">Follow-up Visits Per Week</h3>
                            <div style={{height: '200px'}}>
                                <canvas ref={visitsChartRef}></canvas>
                            </div>
                        </div>
                    </div>
                )}

                <p className="text-sm text-gray-500">
                    {totalVisits + ' total visits across ' + kpis.totalChildren + ' children'}
                </p>
            </div>
        </div>
    );
}"""

TEMPLATE = {
    "key": "sam_followup",
    "name": "SAM Follow-up Timeline",
    "description": "Track SAM follow-up visits per child with MUAC measurements, photos, and referral compliance",
    "icon": "fa-child",
    "color": "red",
    "definition": DEFINITION,
    "render_code": RENDER_CODE,
    "pipeline_schemas": PIPELINE_SCHEMAS,
}
