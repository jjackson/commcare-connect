"""
KMC Longitudinal Tracking Workflow Template.

Dashboard-first view for Kangaroo Mother Care programs. Tracks children
across multiple visits with actionable KPI cards, filterable child list,
and interactive per-child timeline with weight charts and maps.

All data is extracted visit-level and grouped by beneficiary_case_id
client-side in the React component.
"""

DEFINITION = {
    "name": "KMC Longitudinal Tracking",
    "description": "Track KMC children across visits with outcomes dashboard, child list, and timeline",
    "version": 1,
    "templateType": "kmc_longitudinal",
    "statuses": [
        {"id": "active", "label": "Active", "color": "green"},
        {"id": "discharged", "label": "Discharged", "color": "blue"},
        {"id": "lost_to_followup", "label": "Lost to Follow-up", "color": "red"},
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
        "name": "KMC Visit Data",
        "description": "Visit-level data for KMC beneficiaries, grouped by beneficiary_case_id",
        "schema": {
            "data_source": {"type": "connect_csv"},
            "grouping_key": "username",
            "terminal_stage": "visit_level",
            "linking_field": "beneficiary_case_id",
            "fields": [
                # --- Identity & Linking ---
                {
                    "name": "beneficiary_case_id",
                    "paths": ["form.case.@case_id", "form.kmc_beneficiary_case_id"],
                    "aggregation": "first",
                },
                {
                    "name": "child_name",
                    "paths": ["form.child_details.child_name", "form.svn_name"],
                    "aggregation": "first",
                },
                {
                    "name": "mother_name",
                    "paths": ["form.mothers_details.mother_name", "form.kmc_beneficiary_name"],
                    "aggregation": "first",
                },
                {
                    "name": "mother_phone",
                    "paths": [
                        "form.mothers_details.mothers_phone_number",
                        "form.deduplication_block.mothers_phone_number",
                    ],
                    "aggregation": "first",
                },
                # --- Clinical Outcomes ---
                {
                    "name": "weight",
                    "paths": [
                        "form.anthropometric.child_weight_visit",
                        "form.child_details.birth_weight_reg.child_weight_reg",
                    ],
                    "aggregation": "first",
                    "transform": "kg_to_g",
                },
                {
                    "name": "birth_weight",
                    "paths": [
                        "form.child_details.birth_weight_group.child_weight_birth",
                        "form.child_weight_birth",
                    ],
                    "aggregation": "first",
                    "transform": "kg_to_g",
                },
                {
                    "name": "height",
                    "path": "form.anthropometric.child_height",
                    "aggregation": "first",
                    "transform": "float",
                },
                # --- Visit Metadata ---
                {
                    "name": "visit_date",
                    "paths": ["form.grp_kmc_visit.visit_date", "form.reg_date"],
                    "aggregation": "first",
                    "transform": "date",
                },
                {
                    "name": "visit_number",
                    "path": "form.grp_kmc_visit.visit_number",
                    "aggregation": "first",
                },
                {
                    "name": "visit_type",
                    "path": "form.grp_kmc_visit.visit_type",
                    "aggregation": "first",
                },
                {
                    "name": "form_name",
                    "path": "form.@name",
                    "aggregation": "first",
                },
                {
                    "name": "time_end",
                    "path": "form.meta.timeEnd",
                    "aggregation": "first",
                },
                # --- Location ---
                {
                    "name": "gps",
                    "paths": ["form.visit_gps_manual", "form.reg_gps", "metadata.location"],
                    "aggregation": "first",
                },
                {
                    "name": "village",
                    "path": "form.mothers_details.village",
                    "aggregation": "first",
                },
                {
                    "name": "subcounty",
                    "paths": ["form.mothers_details.subcounty", "form.subcounty"],
                    "aggregation": "first",
                },
                # --- KMC Practice ---
                {
                    "name": "kmc_hours",
                    "path": "form.KMC_24-Hour_Recall.kmc_hours",
                    "aggregation": "first",
                },
                {
                    "name": "kmc_providers",
                    "path": "form.KMC_24-Hour_Recall.kmc_providers",
                    "aggregation": "first",
                },
                {
                    "name": "baby_position",
                    "path": "form.kmc_positioning_checklist.baby_position",
                    "aggregation": "first",
                },
                # --- Feeding ---
                {
                    "name": "feeding_provided",
                    "path": "form.KMC_24-Hour_Recall.feeding_provided",
                    "aggregation": "first",
                },
                {
                    "name": "successful_feeds",
                    "path": "form.danger_signs_checklist.successful_feeds_in_last_24_hours",
                    "aggregation": "first",
                },
                # --- Vital Signs ---
                {
                    "name": "temperature",
                    "path": "form.danger_signs_checklist.svn_temperature",
                    "aggregation": "first",
                    "transform": "float",
                },
                {
                    "name": "breath_count",
                    "path": "form.danger_signs_checklist.child_breath_count",
                    "aggregation": "first",
                },
                {
                    "name": "danger_signs",
                    "path": "form.danger_signs_checklist.danger_sign_list",
                    "aggregation": "first",
                },
                # --- Status ---
                {
                    "name": "kmc_status",
                    "paths": ["form.grp_kmc_beneficiary.kmc_status", "form.kmc_status"],
                    "aggregation": "first",
                },
                {
                    "name": "visit_location",
                    "paths": ["form.visit_location", "form.reg_location"],
                    "aggregation": "first",
                },
                {
                    "name": "visit_timeliness",
                    "path": "form.grp_kmc_visit.visit_timeliness",
                    "aggregation": "first",
                },
                # --- Demographics (header) ---
                {
                    "name": "child_dob",
                    "paths": ["form.child_DOB", "form.child_details.child_DOB"],
                    "aggregation": "first",
                    "transform": "date",
                },
                {
                    "name": "child_gender",
                    "path": "form.child_details.child_gender",
                    "aggregation": "first",
                },
                {
                    "name": "mother_age",
                    "paths": ["form.mothers_details.mother_age", "form.mother_age"],
                    "aggregation": "first",
                },
                {
                    "name": "reg_date",
                    "path": "form.reg_date",
                    "aggregation": "first",
                    "transform": "date",
                },
                # --- FLW ---
                {
                    "name": "flw_username",
                    "path": "form.meta.username",
                    "aggregation": "first",
                },
            ],
        },
    },
]

RENDER_CODE = """function WorkflowUI({ definition, instance, workers, pipelines, links, actions, onUpdateState }) {

    // --- Utility: days since a date string ---
    const daysSince = (dateStr) => {
        if (!dateStr) return null;
        const parsed = new Date(dateStr);
        if (isNaN(parsed.getTime())) return null;
        return Math.floor((Date.now() - parsed.getTime()) / 86400000);
    };

    // --- Data Processing: group flat visit rows by beneficiary_case_id ---
    const groupVisitsByChild = (visitRows) => {
        const grouped = {};
        visitRows.forEach((row) => {
            const caseId = row.beneficiary_case_id;
            if (!caseId) return;
            if (!grouped[caseId]) {
                grouped[caseId] = [];
            }
            grouped[caseId].push(row);
        });

        return Object.keys(grouped).map((caseId) => {
            const rows = grouped[caseId].slice().sort((a, b) => {
                const da = a.visit_date ? new Date(a.visit_date) : new Date(0);
                const db = b.visit_date ? new Date(b.visit_date) : new Date(0);
                return da - db;
            });

            // Pull demographics from the first row that has data
            const first = rows[0] || {};
            const findFirst = (field) => {
                for (let i = 0; i < rows.length; i++) {
                    if (rows[i][field] != null && rows[i][field] !== '') return rows[i][field];
                }
                return null;
            };

            const childName = findFirst('child_name');
            const motherName = findFirst('mother_name');
            const motherPhone = findFirst('mother_phone');
            const childDob = findFirst('child_dob');
            const childGender = findFirst('child_gender');
            const motherAge = findFirst('mother_age');
            const village = findFirst('village');
            const subcounty = findFirst('subcounty');
            const birthWeightRaw = findFirst('birth_weight');
            const regDate = findFirst('reg_date');
            const flwUsername = findFirst('flw_username');

            const birthWeight = birthWeightRaw != null ? parseFloat(birthWeightRaw) : null;

            // Current weight: most recent visit with weight data
            let currentWeight = null;
            for (let i = rows.length - 1; i >= 0; i--) {
                if (rows[i].weight != null && rows[i].weight !== '') {
                    currentWeight = parseFloat(rows[i].weight);
                    break;
                }
            }

            const visitCount = rows.length;
            const lastRow = rows[rows.length - 1];
            const lastVisitDate = lastRow ? lastRow.visit_date : null;

            // Weight gain
            const weightGain = (currentWeight != null && birthWeight != null && !isNaN(currentWeight) && !isNaN(birthWeight))
                ? currentWeight - birthWeight
                : null;

            // Is overdue: >14 days since last visit
            const daysSinceLastVisit = daysSince(lastVisitDate);
            const isOverdue = daysSinceLastVisit != null ? daysSinceLastVisit > 14 : false;

            // Reached threshold: current weight >= 2500g
            const reachedThreshold = currentWeight != null && !isNaN(currentWeight) && currentWeight >= 2500;

            // Average weight gain per week
            let avgWeightGainPerWeek = null;
            if (weightGain != null && regDate) {
                const regParsed = new Date(regDate);
                if (!isNaN(regParsed.getTime())) {
                    const msInProgram = Date.now() - regParsed.getTime();
                    const weeksInProgram = msInProgram / (7 * 86400000);
                    if (weeksInProgram > 0) {
                        avgWeightGainPerWeek = weightGain / weeksInProgram;
                    }
                }
            }

            // Most recent kmc_status
            let kmcStatus = null;
            for (let i = rows.length - 1; i >= 0; i--) {
                if (rows[i].kmc_status != null && rows[i].kmc_status !== '') {
                    kmcStatus = rows[i].kmc_status;
                    break;
                }
            }

            return {
                beneficiary_case_id: caseId,
                child_name: childName,
                mother_name: motherName,
                mother_phone: motherPhone,
                child_dob: childDob,
                child_gender: childGender,
                mother_age: motherAge,
                village: village,
                subcounty: subcounty,
                birth_weight: birthWeight,
                reg_date: regDate,
                flw_username: flwUsername,
                currentWeight: currentWeight,
                visitCount: visitCount,
                lastVisitDate: lastVisitDate,
                weightGain: weightGain,
                isOverdue: isOverdue,
                reachedThreshold: reachedThreshold,
                avgWeightGainPerWeek: avgWeightGainPerWeek,
                kmc_status: kmcStatus,
                visits: rows,
            };
        });
    };

    // --- Data Processing: compute KPIs from grouped children ---
    const computeKPIs = (children) => {
        const totalChildren = children.length;
        const activeChildren = children.filter(
            (c) => !c.isOverdue && c.kmc_status !== 'discharged'
        ).length;
        const overdueChildren = children.filter((c) => c.isOverdue).length;
        const belowAvgGain = children.filter(
            (c) => c.avgWeightGainPerWeek != null && c.avgWeightGainPerWeek < 100
        ).length;
        const reachedThreshold = children.filter((c) => c.reachedThreshold).length;
        const discharged = children.filter((c) => c.kmc_status === 'discharged').length;
        const totalVisits = children.reduce((sum, c) => sum + c.visitCount, 0);
        const avgVisitsPerChild = totalChildren > 0 ? totalVisits / totalChildren : 0;

        return {
            totalChildren,
            activeChildren,
            overdueChildren,
            belowAvgGain,
            reachedThreshold,
            discharged,
            totalVisits,
            avgVisitsPerChild,
        };
    };

    // --- State ---
    const [currentView, setCurrentView] = React.useState('dashboard');
    const [selectedChildId, setSelectedChildId] = React.useState(null);
    const [childListFilter, setChildListFilter] = React.useState('all');
    const [searchText, setSearchText] = React.useState('');
    const [sortBy, setSortBy] = React.useState('name');
    const [sortDir, setSortDir] = React.useState('asc');
    const [selectedVisitIdx, setSelectedVisitIdx] = React.useState(0);

    // --- Dashboard chart refs ---
    const enrollmentChartRef = React.useRef(null);
    const enrollmentChartInstance = React.useRef(null);
    const visitsChartRef = React.useRef(null);
    const visitsChartInstance = React.useRef(null);

    // --- Computed data ---
    const visitRows = pipelines && pipelines.visits ? (pipelines.visits.rows || []) : [];
    const children = React.useMemo(() => groupVisitsByChild(visitRows), [visitRows]);
    const kpis = React.useMemo(() => computeKPIs(children), [children]);

    // --- Weekly data for dashboard charts ---
    const weeklyData = React.useMemo(() => {
        if (children.length === 0) return { enrollment: [], visits: [] };

        // Helper: get ISO week string (YYYY-WXX)
        const getWeekKey = (dateStr) => {
            if (!dateStr) return null;
            const d = new Date(dateStr);
            if (isNaN(d.getTime())) return null;
            // Get ISO week number
            const jan1 = new Date(d.getFullYear(), 0, 1);
            const weekNum = Math.ceil(((d - jan1) / 86400000 + jan1.getDay() + 1) / 7);
            return d.getFullYear() + '-W' + String(weekNum).padStart(2, '0');
        };

        // Get the Monday date for a week key
        const weekKeyToDate = (weekKey) => {
            const [year, wStr] = weekKey.split('-W');
            const jan1 = new Date(parseInt(year), 0, 1);
            const dayOffset = (jan1.getDay() + 6) % 7; // days since last Monday
            const firstMonday = new Date(jan1);
            firstMonday.setDate(jan1.getDate() - dayOffset);
            firstMonday.setDate(firstMonday.getDate() + (parseInt(wStr) - 1) * 7);
            return firstMonday.toISOString().split('T')[0];
        };

        // Enrollment: count children by week of their first visit
        const enrollmentByWeek = {};
        children.forEach(c => {
            const firstDate = c.visits[0] && c.visits[0].visit_date;
            const week = getWeekKey(firstDate);
            if (week) {
                enrollmentByWeek[week] = (enrollmentByWeek[week] || 0) + 1;
            }
        });

        // Visits: count all visits by week
        const visitsByWeek = {};
        children.forEach(c => {
            c.visits.forEach(v => {
                const week = getWeekKey(v.visit_date);
                if (week) {
                    visitsByWeek[week] = (visitsByWeek[week] || 0) + 1;
                }
            });
        });

        // Get all weeks, sorted
        const allWeeks = [...new Set([...Object.keys(enrollmentByWeek), ...Object.keys(visitsByWeek)])].sort();

        // Build cumulative enrollment
        let cumulative = 0;
        const enrollment = allWeeks.map(week => {
            cumulative += (enrollmentByWeek[week] || 0);
            return { week, date: weekKeyToDate(week), count: cumulative };
        });

        const visits = allWeeks.map(week => ({
            week,
            date: weekKeyToDate(week),
            count: visitsByWeek[week] || 0,
        }));

        return { enrollment, visits };
    }, [children]);

    // --- Enrollment chart ---
    React.useEffect(() => {
        if (currentView !== 'dashboard') return;
        if (!enrollmentChartRef.current || !window.Chart || weeklyData.enrollment.length === 0) return;

        if (enrollmentChartInstance.current) enrollmentChartInstance.current.destroy();

        const ctx = enrollmentChartRef.current.getContext('2d');
        enrollmentChartInstance.current = new window.Chart(ctx, {
            type: 'line',
            data: {
                labels: weeklyData.enrollment.map(d => d.date),
                datasets: [{
                    label: 'Children Enrolled',
                    data: weeklyData.enrollment.map(d => d.count),
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 3,
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
                        ticks: { font: { size: 10 } },
                    },
                },
            },
        });

        return () => {
            if (enrollmentChartInstance.current) {
                enrollmentChartInstance.current.destroy();
                enrollmentChartInstance.current = null;
            }
        };
    }, [currentView, weeklyData]);

    // --- Visits per week chart ---
    React.useEffect(() => {
        if (currentView !== 'dashboard') return;
        if (!visitsChartRef.current || !window.Chart || weeklyData.visits.length === 0) return;

        if (visitsChartInstance.current) visitsChartInstance.current.destroy();

        const ctx = visitsChartRef.current.getContext('2d');
        visitsChartInstance.current = new window.Chart(ctx, {
            type: 'bar',
            data: {
                labels: weeklyData.visits.map(d => d.date),
                datasets: [{
                    label: 'Visits',
                    data: weeklyData.visits.map(d => d.count),
                    backgroundColor: 'rgba(16, 185, 129, 0.6)',
                    borderColor: '#10b981',
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

        return () => {
            if (visitsChartInstance.current) {
                visitsChartInstance.current.destroy();
                visitsChartInstance.current = null;
            }
        };
    }, [currentView, weeklyData]);

    // --- Loading state ---
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

    // --- Empty data state ---
    if (visitRows.length === 0) {
        return (
            <div className="text-center py-16">
                <div className="inline-block p-4 rounded-full bg-gray-100 mb-4">
                    <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
                    </svg>
                </div>
                <p className="text-gray-500 text-lg">No KMC visit data found</p>
                <p className="text-gray-400 text-sm mt-1">Pipeline data may still be loading, or no visits have been recorded for this opportunity.</p>
            </div>
        );
    }

    // --- Card click handler ---
    const handleCardClick = (filter) => {
        setChildListFilter(filter);
        setCurrentView('childList');
    };

    // --- Back to dashboard handler ---
    const handleBackToDashboard = () => {
        setCurrentView('dashboard');
        setSelectedChildId(null);
        setChildListFilter('all');
    };

    // --- Child Timeline ---
    const ChildTimeline = () => {
        const child = children.find(c => c.beneficiary_case_id === selectedChildId);
        if (!child) return <div className="p-8 text-center text-gray-500">Child not found</div>;

        const sortedVisits = [...child.visits].reverse();
        const selectedVisit = sortedVisits[selectedVisitIdx] || {};

        // --- Collapsible detail sections ---
        const [expandedSections, setExpandedSections] = React.useState({
            anthropometric: true,
            kmc_practice: true,
            feeding: true,
            vitals: true,
            visit_info: true,
        });
        const toggleSection = (key) => {
            setExpandedSections(prev => ({...prev, [key]: !prev[key]}));
        };

        const formatValue = (val, suffix, isDanger) => {
            if (val == null || val === '') return '\u2014';
            const str = typeof val === 'number' ? val.toLocaleString() : String(val);
            const display = suffix ? str + suffix : str;
            if (isDanger && val && val !== 'none' && val !== 'no') {
                return React.createElement('span', {className: 'text-red-600 font-medium'}, display);
            }
            return display;
        };

        const detailSections = [
            {
                key: 'anthropometric',
                title: 'Anthropometric',
                fields: [
                    { label: 'Weight', value: selectedVisit.weight, suffix: 'g' },
                    { label: 'Height', value: selectedVisit.height, suffix: 'cm' },
                    { label: 'Birth Weight', value: child.birth_weight, suffix: 'g' },
                ],
            },
            {
                key: 'kmc_practice',
                title: 'KMC Practice',
                fields: [
                    { label: 'KMC Hours', value: selectedVisit.kmc_hours },
                    { label: 'KMC Providers', value: selectedVisit.kmc_providers },
                    { label: 'Baby Position', value: selectedVisit.baby_position },
                ],
            },
            {
                key: 'feeding',
                title: 'Feeding',
                fields: [
                    { label: 'Feeding Provided', value: selectedVisit.feeding_provided },
                    { label: 'Successful Feeds', value: selectedVisit.successful_feeds },
                ],
            },
            {
                key: 'vitals',
                title: 'Vital Signs',
                fields: [
                    { label: 'Temperature', value: selectedVisit.temperature, suffix: '\u00B0C' },
                    { label: 'Breath Count', value: selectedVisit.breath_count },
                    { label: 'Danger Signs', value: selectedVisit.danger_signs, isDanger: true },
                ],
            },
            {
                key: 'visit_info',
                title: 'Visit Info',
                fields: [
                    { label: 'Location', value: selectedVisit.visit_location },
                    { label: 'Timeliness', value: selectedVisit.visit_timeliness },
                    { label: 'Status', value: selectedVisit.kmc_status },
                ],
            },
        ];

        // --- Chart refs and data ---
        const chartRef = React.useRef(null);
        const chartInstanceRef = React.useRef(null);

        const chartVisits = child.visits.filter(v => v.weight != null && v.weight !== '');
        const chartLabels = chartVisits.map(v => v.visit_date || v.time_end);
        const chartWeights = chartVisits.map(v => parseFloat(v.weight));

        React.useEffect(() => {
            if (!chartRef.current || !window.Chart || chartVisits.length === 0) return;

            if (chartInstanceRef.current) {
                chartInstanceRef.current.destroy();
            }

            // Map selectedVisitIdx (index in sortedVisits) to index in chartVisits
            const selectedVisit = sortedVisits[selectedVisitIdx];
            const selectedChartIdx = selectedVisit ? chartVisits.findIndex(v => v === selectedVisit) : -1;

            // Point colors: green for >= 2500g, amber for below, blue highlight for selected
            const pointBackgroundColors = chartWeights.map((w, i) => {
                if (i === selectedChartIdx) return '#3b82f6'; // blue-500
                return w >= 2500 ? '#10b981' : '#f59e0b'; // emerald-500 : amber-500
            });
            const pointRadii = chartWeights.map((_, i) => i === selectedChartIdx ? 8 : 4);

            const ctx = chartRef.current.getContext('2d');
            chartInstanceRef.current = new window.Chart(ctx, {
                type: 'line',
                data: {
                    labels: chartLabels,
                    datasets: [
                        {
                            label: 'Weight (g)',
                            data: chartWeights,
                            borderColor: '#6b7280',
                            backgroundColor: 'rgba(107, 114, 128, 0.1)',
                            fill: true,
                            tension: 0.3,
                            pointBackgroundColor: pointBackgroundColors,
                            pointBorderColor: pointBackgroundColors,
                            pointRadius: pointRadii,
                            pointHoverRadius: 8,
                        },
                        // 2.5kg threshold line
                        {
                            label: '2.5kg Threshold',
                            data: chartLabels.map(() => 2500),
                            borderColor: '#ef4444',
                            borderDash: [6, 4],
                            borderWidth: 1,
                            pointRadius: 0,
                            fill: false,
                        },
                        // Birth weight line (if available)
                        ...(child.birth_weight != null ? [{
                            label: 'Birth Weight',
                            data: chartLabels.map(() => child.birth_weight),
                            borderColor: '#94a3b8',
                            borderDash: [3, 3],
                            borderWidth: 1,
                            pointRadius: 0,
                            fill: false,
                        }] : []),
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    onClick: (e, elements) => {
                        if (elements.length > 0) {
                            const chartIdx = elements[0].index;
                            const clickedVisit = chartVisits[chartIdx];
                            // Find the corresponding index in sortedVisits
                            const sortedIdx = sortedVisits.findIndex(v => v === clickedVisit);
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
                                label: (ctx) => {
                                    if (ctx.datasetIndex === 0) {
                                        return ctx.parsed.y.toLocaleString() + 'g';
                                    }
                                    return ctx.dataset.label + ': ' + ctx.parsed.y.toLocaleString() + 'g';
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
                            title: { display: true, text: 'Weight (grams)', font: { size: 11 } },
                            beginAtZero: false,
                        },
                    },
                },
            });

            return () => {
                if (chartInstanceRef.current) {
                    chartInstanceRef.current.destroy();
                    chartInstanceRef.current = null;
                }
            };
        }, [child.visits, selectedVisitIdx]);

        // --- Map: GPS parser, data, refs, effects ---
        const parseGPS = (gpsStr) => {
            if (!gpsStr) return null;
            const parts = String(gpsStr).trim().split(/\\s+/);
            if (parts.length >= 2) {
                const lat = parseFloat(parts[0]);
                const lng = parseFloat(parts[1]);
                if (!isNaN(lat) && !isNaN(lng) && lat !== 0 && lng !== 0) {
                    return [lat, lng];
                }
            }
            return null;
        };

        const visitsWithGPS = child.visits.map((v, idx) => ({
            visit: v,
            originalIdx: idx,
            coords: parseGPS(v.gps),
        })).filter(item => item.coords !== null);

        const mapRef = React.useRef(null);
        const mapInstanceRef = React.useRef(null);
        const markersRef = React.useRef([]);

        React.useEffect(() => {
            if (!mapRef.current || !window.L || mapInstanceRef.current) return;

            mapInstanceRef.current = window.L.map(mapRef.current, {
                scrollWheelZoom: false,
            }).setView([0, 0], 2);

            window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '&copy; OpenStreetMap',
                maxZoom: 18,
            }).addTo(mapInstanceRef.current);

            return () => {
                if (mapInstanceRef.current) {
                    mapInstanceRef.current.remove();
                    mapInstanceRef.current = null;
                }
            };
        }, []);

        React.useEffect(() => {
            if (!mapInstanceRef.current || !window.L) return;

            // Clear existing markers
            markersRef.current.forEach(m => m.remove());
            markersRef.current = [];

            if (visitsWithGPS.length === 0) return;

            // Map selectedVisitIdx (in sortedVisits) to original visit index
            const selectedVisit = sortedVisits[selectedVisitIdx];
            const selectedOriginalIdx = selectedVisit ? child.visits.indexOf(selectedVisit) : -1;

            visitsWithGPS.forEach(({ visit, originalIdx, coords }) => {
                const isSelected = originalIdx === selectedOriginalIdx;
                const isFirst = originalIdx === 0;

                const color = isSelected ? '#3b82f6' : isFirst ? '#6366f1' : '#10b981';
                const radius = isSelected ? 10 : 6;

                const marker = window.L.circleMarker(coords, {
                    radius: radius,
                    fillColor: color,
                    color: '#fff',
                    weight: 2,
                    opacity: 1,
                    fillOpacity: 0.9,
                }).addTo(mapInstanceRef.current);

                const label = visit.visit_number ? 'Visit ' + visit.visit_number : (visit.form_name || 'Visit');
                marker.bindPopup(label + '<br>' + (visit.visit_date || ''));

                marker.on('click', () => {
                    const sortedIdx = sortedVisits.indexOf(visit);
                    if (sortedIdx >= 0) {
                        setSelectedVisitIdx(sortedIdx);
                    }
                });

                markersRef.current.push(marker);
            });

            // Fit bounds
            const bounds = window.L.latLngBounds(visitsWithGPS.map(v => v.coords));
            mapInstanceRef.current.fitBounds(bounds, { padding: [20, 20], maxZoom: 15 });

        }, [child.visits, selectedVisitIdx]);

        const handleBackToList = () => {
            setCurrentView('childList');
            setSelectedChildId(null);
            setSelectedVisitIdx(0);
        };

        // Status badge
        const getStatusBadge = () => {
            if (child.kmc_status === 'discharged') {
                return { label: 'Discharged', bg: 'bg-blue-100', text: 'text-blue-800' };
            }
            if (child.kmc_status === 'lost_to_followup') {
                return { label: 'Lost to Follow-up', bg: 'bg-red-100', text: 'text-red-800' };
            }
            if (child.isOverdue) {
                return { label: 'Overdue', bg: 'bg-yellow-100', text: 'text-yellow-800' };
            }
            return { label: 'Active', bg: 'bg-green-100', text: 'text-green-800' };
        };
        const status = getStatusBadge();

        // Computed values for header
        const birthWeightNum = child.birth_weight != null && !isNaN(child.birth_weight) ? child.birth_weight : null;
        const currentWeightNum = child.currentWeight != null && !isNaN(child.currentWeight) ? child.currentWeight : null;
        const weightGainPct = (child.weightGain != null && birthWeightNum != null && birthWeightNum > 0)
            ? ((child.weightGain / birthWeightNum) * 100).toFixed(0)
            : null;
        const weeksInProgram = child.reg_date ? Math.round(daysSince(child.reg_date) / 7) : null;
        const avgGainPerWeek = child.avgWeightGainPerWeek != null ? Math.round(child.avgWeightGainPerWeek) : null;

        return (
            <div className="space-y-4">
                {/* Header Card */}
                <div className="bg-white rounded-lg shadow-sm p-5">
                    {/* Top row: back button, name, status */}
                    <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-3">
                            <button
                                onClick={handleBackToList}
                                className="inline-flex items-center text-sm text-blue-600 hover:text-blue-800 font-medium"
                            >
                                &larr; Back to list
                            </button>
                            <h2 className="text-lg font-semibold text-gray-900">
                                {child.child_name || 'Unknown Child'}
                            </h2>
                        </div>
                        <span className={"inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium " + status.bg + " " + status.text}>
                            {status.label}
                        </span>
                    </div>

                    {/* 3-column info grid */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        {/* Column 1: Child Info */}
                        <div className="space-y-2">
                            <div>
                                <span className="text-xs text-gray-500">DOB</span>
                                <div className="text-sm text-gray-900">{child.child_dob || '-'}</div>
                            </div>
                            <div>
                                <span className="text-xs text-gray-500">Gender</span>
                                <div className="text-sm text-gray-900">{child.child_gender || '-'}</div>
                            </div>
                            <div>
                                <span className="text-xs text-gray-500">Visits</span>
                                <div className="text-sm text-gray-900">{child.visitCount}</div>
                            </div>
                            <div>
                                <span className="text-xs text-gray-500">In program</span>
                                <div className="text-sm text-gray-900">{weeksInProgram != null ? weeksInProgram + ' wk' : '-'}</div>
                            </div>
                        </div>

                        {/* Column 2: Weight */}
                        <div className="space-y-2">
                            <div>
                                <span className="text-xs text-gray-500">Birth weight</span>
                                <div className="text-sm text-gray-900">{birthWeightNum != null ? birthWeightNum.toLocaleString() + 'g' : '-'}</div>
                            </div>
                            <div>
                                <span className="text-xs text-gray-500">Current weight</span>
                                <div className="text-sm text-gray-900">{currentWeightNum != null ? currentWeightNum.toLocaleString() + 'g' : '-'}</div>
                            </div>
                            <div>
                                <span className="text-xs text-gray-500">Weight gain</span>
                                <div className="text-sm text-gray-900">
                                    {child.weightGain != null
                                        ? '+' + Math.round(child.weightGain).toLocaleString() + 'g' + (weightGainPct != null ? ' (+' + weightGainPct + '%)' : '')
                                        : '-'}
                                </div>
                            </div>
                            <div>
                                <span className="text-xs text-gray-500">Gain/week</span>
                                <div className="text-sm text-gray-900">{avgGainPerWeek != null ? avgGainPerWeek + 'g' : '-'}</div>
                            </div>
                        </div>

                        {/* Column 3: Contact */}
                        <div className="space-y-2">
                            <div>
                                <span className="text-xs text-gray-500">Mother</span>
                                <div className="text-sm text-gray-900">{child.mother_name || '-'}</div>
                            </div>
                            <div>
                                <span className="text-xs text-gray-500">Phone</span>
                                <div className="text-sm text-gray-900">{child.mother_phone || '-'}</div>
                            </div>
                            <div>
                                <span className="text-xs text-gray-500">Village</span>
                                <div className="text-sm text-gray-900">{child.village || '-'}</div>
                            </div>
                            <div>
                                <span className="text-xs text-gray-500">Subcounty</span>
                                <div className="text-sm text-gray-900">{child.subcounty || '-'}</div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* 3-column body layout */}
                <div style={{display: 'grid', gridTemplateColumns: '220px 1fr 300px', gap: '16px'}}>
                    {/* Left: Visit History Sidebar */}
                    <div className="bg-white rounded-lg shadow-sm overflow-hidden">
                        <div className="px-3 py-2 bg-gray-50 border-b text-xs font-medium text-gray-500 uppercase">
                            Visits ({child.visits.length})
                        </div>
                        <div style={{maxHeight: '500px', overflowY: 'auto'}}>
                            {sortedVisits.map((visit, idx) => (
                                <div
                                    key={idx}
                                    onClick={() => setSelectedVisitIdx(idx)}
                                    className={
                                        "px-3 py-2 cursor-pointer border-b border-gray-50 " +
                                        (selectedVisitIdx === idx ? "bg-blue-50 border-l-2 border-l-blue-500" : "hover:bg-gray-50")
                                    }
                                >
                                    <div className="text-sm font-medium text-gray-900">
                                        {visit.visit_number ? 'Visit ' + visit.visit_number : visit.form_name || 'Visit'}
                                    </div>
                                    <div className="text-xs text-gray-500">
                                        {visit.visit_date || 'No date'}
                                    </div>
                                    {visit.weight != null && visit.weight !== '' && (
                                        <div className="text-xs text-gray-600 mt-0.5">
                                            {parseFloat(visit.weight).toLocaleString()}g
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Center: Chart + Map */}
                    <div className="space-y-4">
                        <div className="bg-white rounded-lg shadow-sm p-4">
                            <h3 className="text-sm font-medium text-gray-700 mb-2">Weight Progression</h3>
                            {chartVisits.length > 0 ? (
                                <div style={{height: '250px'}}>
                                    <canvas ref={chartRef}></canvas>
                                </div>
                            ) : (
                                <p className="text-gray-400 text-sm text-center py-8">No weight data available</p>
                            )}
                        </div>
                        <div className="bg-white rounded-lg shadow-sm p-4">
                            <h3 className="text-sm font-medium text-gray-700 mb-2">Visit Locations</h3>
                            {visitsWithGPS.length > 0 ? (
                                <div ref={mapRef} style={{height: '200px', borderRadius: '6px'}}></div>
                            ) : (
                                <p className="text-gray-400 text-sm text-center py-8">No GPS data available</p>
                            )}
                        </div>
                    </div>

                    {/* Right: Clinical Detail Panel */}
                    <div className="bg-white rounded-lg shadow-sm overflow-hidden">
                        <div className="px-4 py-3 bg-gray-50 border-b">
                            <h3 className="text-sm font-medium text-gray-700">
                                {selectedVisit.visit_number ? 'Visit ' + selectedVisit.visit_number : selectedVisit.form_name || 'Visit Details'}
                            </h3>
                            <p className="text-xs text-gray-500">{selectedVisit.visit_date || ''}</p>
                        </div>
                        <div style={{maxHeight: '460px', overflowY: 'auto'}}>
                            {detailSections.map(section => (
                                <div key={section.key} className="border-b border-gray-100 last:border-b-0">
                                    <button
                                        onClick={() => toggleSection(section.key)}
                                        className="w-full px-4 py-2 flex justify-between items-center text-left hover:bg-gray-50"
                                    >
                                        <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                                            {section.title}
                                        </span>
                                        <span className="text-gray-400 text-xs">
                                            {expandedSections[section.key] ? '\u25B2' : '\u25BC'}
                                        </span>
                                    </button>
                                    {expandedSections[section.key] && (
                                        <div className="px-4 pb-3">
                                            {section.fields.map(field => (
                                                <div key={field.label} className="flex justify-between py-1">
                                                    <span className="text-xs text-gray-500">{field.label}</span>
                                                    <span className="text-sm text-gray-900 text-right">
                                                        {formatValue(field.value, field.suffix, field.isDanger)}
                                                    </span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        );
    };

    // --- Child List ---
    const ChildList = () => {
        const filterOptions = [
            { value: 'all', label: 'All' },
            { value: 'active', label: 'Active' },
            { value: 'overdue', label: 'Overdue' },
            { value: 'low_gain', label: 'Below Avg Gain' },
            { value: 'threshold_met', label: 'Reached 2.5kg' },
            { value: 'discharged', label: 'Discharged' },
        ];

        // Apply status filter
        const statusFiltered = children.filter((child) => {
            if (childListFilter === 'all') return true;
            if (childListFilter === 'active') return !child.isOverdue && child.kmc_status !== 'discharged';
            if (childListFilter === 'overdue') return child.isOverdue;
            if (childListFilter === 'low_gain') return child.avgWeightGainPerWeek != null && child.avgWeightGainPerWeek < 100;
            if (childListFilter === 'threshold_met') return child.reachedThreshold;
            if (childListFilter === 'discharged') return child.kmc_status === 'discharged';
            return true;
        });

        // Apply search filter
        const filteredChildren = statusFiltered.filter((child) => {
            if (!searchText) return true;
            const q = searchText.toLowerCase();
            const cn = (child.child_name || '').toLowerCase();
            const mn = (child.mother_name || '').toLowerCase();
            return cn.includes(q) || mn.includes(q);
        });

        // Sort
        const handleSort = (col) => {
            if (sortBy === col) {
                setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
            } else {
                setSortBy(col);
                setSortDir('asc');
            }
        };

        const sortedChildren = [...filteredChildren].sort((a, b) => {
            let cmp = 0;
            if (sortBy === 'name') cmp = (a.child_name || '').localeCompare(b.child_name || '');
            else if (sortBy === 'flw') cmp = (a.flw_username || '').localeCompare(b.flw_username || '');
            else if (sortBy === 'visits') cmp = a.visitCount - b.visitCount;
            else if (sortBy === 'weight') cmp = (a.currentWeight || 0) - (b.currentWeight || 0);
            else if (sortBy === 'gain') cmp = (a.weightGain || 0) - (b.weightGain || 0);
            else if (sortBy === 'lastVisit') cmp = (daysSince(a.lastVisitDate) || 9999) - (daysSince(b.lastVisitDate) || 9999);
            return sortDir === 'asc' ? cmp : -cmp;
        });

        const sortArrow = (col) => {
            if (sortBy !== col) return '';
            return sortDir === 'asc' ? ' \\u2191' : ' \\u2193';
        };

        const columns = [
            { key: 'name', label: 'Child Name' },
            { key: 'flw', label: 'FLW' },
            { key: 'visits', label: 'Visits' },
            { key: 'weight', label: 'Current Weight' },
            { key: 'gain', label: 'Weight Gain' },
            { key: 'lastVisit', label: 'Last Visit' },
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
                        onChange={(e) => setChildListFilter(e.target.value)}
                        className="border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                        {filterOptions.map((opt) => (
                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                        ))}
                    </select>
                    <input
                        type="text"
                        placeholder="Search by child or mother name..."
                        value={searchText}
                        onChange={(e) => setSearchText(e.target.value)}
                        className="border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 flex-1 min-w-[200px]"
                    />
                    <span className="text-sm text-gray-500">
                        Showing {sortedChildren.length} of {children.length} children
                    </span>
                </div>

                {/* Table */}
                <div className="bg-white rounded-lg shadow-sm overflow-hidden">
                    <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200">
                            <thead className="bg-gray-50">
                                <tr>
                                    {columns.map((col) => (
                                        <th
                                            key={col.key}
                                            onClick={() => handleSort(col.key)}
                                            className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none"
                                        >
                                            {col.label}{sortArrow(col.key)}
                                        </th>
                                    ))}
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
                                    sortedChildren.map((child) => {
                                        const daysAgo = daysSince(child.lastVisitDate);
                                        const lastVisitText = daysAgo != null ? (daysAgo === 0 ? 'Today' : daysAgo + ' days ago') : '-';
                                        const lastVisitClass = daysAgo != null && daysAgo > 14 ? 'text-red-600 font-medium' : 'text-gray-700';
                                        const weightText = child.currentWeight != null ? child.currentWeight + 'g' : '-';
                                        const weightClass = child.currentWeight != null
                                            ? (child.currentWeight >= 2500 ? 'text-green-600 font-medium' : 'text-amber-600 font-medium')
                                            : 'text-gray-400';
                                        const gainText = child.weightGain != null ? '+' + Math.round(child.weightGain) + 'g' : '-';
                                        const gainPerWeek = child.avgWeightGainPerWeek != null ? Math.round(child.avgWeightGainPerWeek) + 'g/wk' : '';
                                        return (
                                            <tr
                                                key={child.beneficiary_case_id}
                                                onClick={() => { setSelectedChildId(child.beneficiary_case_id); setCurrentView('timeline'); }}
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
                                                <td className="px-4 py-3 text-sm text-gray-700">{child.flw_username || '-'}</td>
                                                <td className="px-4 py-3 text-sm text-gray-700">{child.visitCount}</td>
                                                <td className={"px-4 py-3 text-sm " + weightClass}>{weightText}</td>
                                                <td className="px-4 py-3 text-sm text-gray-700">
                                                    <div>{gainText}</div>
                                                    {gainPerWeek && <div className="text-xs text-gray-400">{gainPerWeek}</div>}
                                                </td>
                                                <td className={"px-4 py-3 text-sm " + lastVisitClass}>{lastVisitText}</td>
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
    };

    // --- Navigation Bar ---
    const NavigationBar = () => {
        const selectedChild = selectedChildId ? children.find(c => c.beneficiary_case_id === selectedChildId) : null;

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
                    onClick={() => setCurrentView('childList')}
                    className={"px-4 py-2 text-sm font-medium border-b-2 -mb-px " +
                        (currentView === 'childList'
                            ? "border-blue-500 text-blue-600"
                            : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300")}
                >
                    All Children ({children.length})
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
    };

    // --- View Router ---
    if (currentView === 'timeline' && selectedChildId) {
        return (
            <div>
                <NavigationBar />
                <ChildTimeline />
            </div>
        );
    }
    if (currentView === 'childList') {
        return (
            <div>
                <NavigationBar />
                <ChildList />
            </div>
        );
    }

    // --- Dashboard View ---
    const kpiCards = [
        {
            label: 'Total Children',
            value: kpis.totalChildren,
            borderColor: 'border-blue-500',
            filter: 'all',
        },
        {
            label: 'Active',
            value: kpis.activeChildren,
            borderColor: 'border-green-500',
            filter: 'active',
        },
        {
            label: 'Overdue >14 days',
            value: kpis.overdueChildren,
            borderColor: 'border-red-500',
            filter: 'overdue',
        },
        {
            label: 'Below Avg Gain',
            value: kpis.belowAvgGain,
            borderColor: 'border-amber-500',
            filter: 'low_gain',
        },
        {
            label: 'Reached 2.5kg',
            value: kpis.reachedThreshold,
            borderColor: 'border-emerald-500',
            filter: 'threshold_met',
        },
        {
            label: 'Discharged',
            value: kpis.discharged,
            borderColor: 'border-gray-500',
            filter: 'discharged',
        },
    ];

    return (
        <div>
            <NavigationBar />
            <div className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {kpiCards.map((card) => (
                        <div
                            key={card.filter}
                            onClick={() => handleCardClick(card.filter)}
                            className={"bg-white rounded-lg shadow-sm p-5 cursor-pointer hover:shadow-md transition-shadow border-l-4 " + card.borderColor}
                        >
                            <div className="text-3xl font-bold text-gray-900">{card.value}</div>
                            <div className="text-sm text-gray-600 mt-1">{card.label}</div>
                        </div>
                    ))}
                </div>
                <p className="text-sm text-gray-500 mt-4">
                    {kpis.totalVisits} total visits across {kpis.totalChildren} children
                    ({kpis.avgVisitsPerChild.toFixed(1)} visits/child avg)
                </p>
                {weeklyData.enrollment.length > 0 && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                        <div className="bg-white rounded-lg shadow-sm p-4">
                            <h3 className="text-sm font-medium text-gray-700 mb-2">Enrollment Over Time</h3>
                            <div style={{height: '200px'}}>
                                <canvas ref={enrollmentChartRef}></canvas>
                            </div>
                        </div>
                        <div className="bg-white rounded-lg shadow-sm p-4">
                            <h3 className="text-sm font-medium text-gray-700 mb-2">Visits Per Week</h3>
                            <div style={{height: '200px'}}>
                                <canvas ref={visitsChartRef}></canvas>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}"""

TEMPLATE = {
    "key": "kmc_longitudinal",
    "name": "KMC Longitudinal Tracking",
    "description": "Track KMC children across visits with outcomes dashboard, child list, and timeline",
    "icon": "fa-baby",
    "color": "teal",
    "definition": DEFINITION,
    "render_code": RENDER_CODE,
    "pipeline_schemas": PIPELINE_SCHEMAS,
}
