"""
KMC Project Metrics Dashboard Workflow Template.

Program-level M&E dashboard for KMC (Kangaroo Mother Care) projects.
Aggregates visit data across all FLWs and SVNs to show overall project
performance against M&E indicator targets.

Three views:
1. Overview — Top-line KPI cards + enrollment/visit charts
2. Outcomes & Outputs — Detailed metrics with charts by M&E category
3. Indicators Table — All computable indicators with status and trend

Uses the same visit-level pipeline as kmc_longitudinal, with client-side
aggregation in React for project-wide metrics.
"""

DEFINITION = {
    "name": "KMC Project Metrics",
    "description": "Program-level M&E dashboard showing enrollment, health outcomes, KMC practice, and visit quality indicators",
    "version": 1,
    "templateType": "kmc_project_metrics",
    "statuses": [
        {"id": "active", "label": "Active", "color": "green"},
        {"id": "review", "label": "Under Review", "color": "yellow"},
        {"id": "closed", "label": "Closed", "color": "gray"},
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
        "name": "KMC Project Metrics Data",
        "description": "Visit-level data for computing program-wide M&E indicators",
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
                    "paths": [
                        "form.grp_kmc_beneficiary.child_name",
                        "form.grp_beneficiary_details.child_name",
                        "form.svn_name",
                        "form.mothers_details.child_name",
                    ],
                    "aggregation": "first",
                },
                {
                    "name": "flw_username",
                    "path": "form.meta.username",
                    "aggregation": "first",
                },
                # --- Visit Metadata ---
                {
                    "name": "visit_number",
                    "path": "form.grp_kmc_visit.visit_number",
                    "aggregation": "first",
                    "transform": "int",
                },
                {
                    "name": "visit_date",
                    "paths": ["form.grp_kmc_visit.visit_date", "form.reg_date"],
                    "aggregation": "first",
                    "transform": "date",
                },
                {
                    "name": "visit_timeliness",
                    "path": "form.grp_kmc_visit.visit_timeliness",
                    "aggregation": "first",
                },
                {
                    "name": "visit_type",
                    "path": "form.grp_kmc_visit.visit_type",
                    "aggregation": "first",
                },
                {
                    "name": "first_visit_date",
                    "path": "form.grp_kmc_visit.first_visit_date",
                    "aggregation": "first",
                    "transform": "date",
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
                # --- Clinical ---
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
                # --- KMC Practice ---
                {
                    "name": "kmc_hours",
                    "path": "form.kmc_24-hour_recall.kmc_hours",
                    "aggregation": "first",
                    "transform": "float",
                },
                {
                    "name": "kmc_hours_secondary",
                    "path": "form.kmc_24-hour_recall.kmc_hours_secondary",
                    "aggregation": "first",
                    "transform": "float",
                },
                {
                    "name": "total_kmc_hours",
                    "path": "form.kmc_24-hour_recall.total_kmc_hours",
                    "aggregation": "first",
                    "transform": "float",
                },
                {
                    "name": "baby_position",
                    "path": "form.kmc_positioning_checklist.baby_position",
                    "aggregation": "first",
                },
                # --- Feeding ---
                {
                    "name": "feeding_provided",
                    "path": "form.kmc_24-hour_recall.feeding_provided",
                    "aggregation": "first",
                },
                {
                    "name": "successful_feeds",
                    "path": "form.danger_signs_checklist.successful_feeds_in_last_24_hours",
                    "aggregation": "first",
                    "transform": "int",
                },
                # --- Danger Signs & Referrals ---
                {
                    "name": "danger_sign_positive",
                    "path": "form.danger_signs_checklist.danger_sign_positive",
                    "aggregation": "first",
                },
                {
                    "name": "danger_sign_list",
                    "path": "form.danger_signs_checklist.danger_sign_list",
                    "aggregation": "first",
                },
                {
                    "name": "child_referred",
                    "path": "form.danger_signs_checklist.child_referred",
                    "aggregation": "first",
                },
                {
                    "name": "child_taken_to_hospital",
                    "path": "form.referral_check.child_taken_to_the_hospital",
                    "aggregation": "first",
                },
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
                    "transform": "int",
                },
                # --- Status & Discharge ---
                {
                    "name": "child_alive",
                    "path": "form.child_alive",
                    "aggregation": "first",
                },
                {
                    "name": "kmc_status",
                    "paths": ["form.grp_kmc_beneficiary.kmc_status", "form.kmc_status"],
                    "aggregation": "first",
                },
                {
                    "name": "kmc_status_discharged",
                    "path": "form.kmc_discontinuation.kmc_status_discharged",
                    "aggregation": "first",
                },
                # --- Registration & Timeline ---
                {
                    "name": "reg_date",
                    "paths": [
                        "form.grp_kmc_beneficiary.reg_date",
                        "form.reg_date",
                    ],
                    "aggregation": "first",
                    "transform": "date",
                },
                {
                    "name": "days_since_reg",
                    "path": "form.days_since_reg",
                    "aggregation": "first",
                    "transform": "int",
                },
                {
                    "name": "child_dob",
                    "paths": [
                        "form.mothers_details.child_DOB",
                        "form.child_DOB",
                    ],
                    "aggregation": "first",
                    "transform": "date",
                },
                # --- Location ---
                {
                    "name": "gps",
                    "paths": ["form.visit_gps_manual", "form.reg_gps", "metadata.location"],
                    "aggregation": "first",
                },
                {
                    "name": "village",
                    "paths": [
                        "form.grp_kmc_beneficiary.village",
                        "form.address_change_grp.location.village",
                        "form.village",
                    ],
                    "aggregation": "first",
                },
                {
                    "name": "subcounty",
                    "paths": ["form.sub_country", "form.subcounty"],
                    "aggregation": "first",
                },
                # --- Payment ---
                {
                    "name": "visit_pay",
                    "path": "form.grp_kmc_visit.visit_pay_yes_no",
                    "aggregation": "first",
                },
            ],
        },
    },
]

RENDER_CODE = """
function groupVisitsByChild(visitRows) {
    var grouped = {};
    visitRows.forEach(function(row) {
        var caseId = row.beneficiary_case_id;
        if (!caseId) return;
        if (!grouped[caseId]) grouped[caseId] = [];
        grouped[caseId].push(row);
    });

    return Object.keys(grouped).map(function(caseId) {
        var rows = grouped[caseId].slice().sort(function(a, b) {
            var da = a.visit_date ? new Date(a.visit_date) : new Date(0);
            var db = b.visit_date ? new Date(b.visit_date) : new Date(0);
            return da - db;
        });

        var first = rows[0] || {};
        var findFirst = function(field) {
            for (var i = 0; i < rows.length; i++) {
                if (rows[i][field] != null && rows[i][field] !== '') return rows[i][field];
            }
            return null;
        };

        var childName = findFirst('child_name');
        var regDate = findFirst('reg_date');
        var childDob = findFirst('child_dob');
        var kmcStatus = null;
        var childAlive = null;
        for (var i = rows.length - 1; i >= 0; i--) {
            if (kmcStatus == null && rows[i].kmc_status != null && rows[i].kmc_status !== '') {
                kmcStatus = rows[i].kmc_status;
            }
            if (childAlive == null && rows[i].child_alive != null && rows[i].child_alive !== '') {
                childAlive = rows[i].child_alive;
            }
        }

        var birthWeightRaw = findFirst('birth_weight');
        var birthWeight = birthWeightRaw != null ? parseFloat(birthWeightRaw) : null;
        if (birthWeight != null && isNaN(birthWeight)) birthWeight = null;

        var currentWeight = null;
        for (var j = rows.length - 1; j >= 0; j--) {
            if (rows[j].weight != null && rows[j].weight !== '') {
                currentWeight = parseFloat(rows[j].weight);
                if (isNaN(currentWeight)) currentWeight = null;
                else break;
            }
        }

        var weightGain = (currentWeight != null && birthWeight != null) ? currentWeight - birthWeight : null;

        var visitCount = rows.length;
        var firstVisitDate = rows[0] ? rows[0].visit_date : null;
        var lastVisitDate = rows[rows.length - 1] ? rows[rows.length - 1].visit_date : null;

        var isActive = (String(childAlive || '').toLowerCase().indexOf('no') === -1) &&
                       (String(kmcStatus || '').toLowerCase() !== 'discharged');

        var daysInProgram = 0;
        if (regDate && lastVisitDate) {
            var regD = new Date(regDate);
            var lastD = new Date(lastVisitDate);
            if (!isNaN(regD.getTime()) && !isNaN(lastD.getTime())) {
                daysInProgram = Math.floor((lastD - regD) / 86400000);
            }
        }

        return {
            beneficiary_case_id: caseId,
            child_name: childName,
            reg_date: regDate,
            child_dob: childDob,
            visits: rows,
            visitCount: visitCount,
            firstVisitDate: firstVisitDate,
            lastVisitDate: lastVisitDate,
            currentWeight: currentWeight,
            birthWeight: birthWeight,
            weightGain: weightGain,
            kmc_status: kmcStatus,
            child_alive: childAlive,
            isActive: isActive,
            daysInProgram: daysInProgram
        };
    });
}

function computeProjectMetrics(children, visitRows) {
    var totalEnrolled = children.length;
    var activeChildren = children.filter(function(c) { return c.isActive; }).length;
    var totalVisits = visitRows.length;
    var avgVisitsPerChild = totalEnrolled > 0 ? totalVisits / totalEnrolled : 0;

    // 28-day retention: among children enrolled >=28 days ago, % with visits spanning >=28 days
    var now = Date.now();
    var childrenEnrolled28d = children.filter(function(c) {
        if (!c.reg_date) return false;
        var regD = new Date(c.reg_date);
        if (isNaN(regD.getTime())) return false;
        return (now - regD.getTime()) / 86400000 >= 28;
    });
    var retainedCount = childrenEnrolled28d.filter(function(c) {
        return c.daysInProgram >= 28;
    }).length;
    var retentionRate28d = childrenEnrolled28d.length > 0 ? (retainedCount / childrenEnrolled28d.length) * 100 : 0;

    // Mortality rate: among children enrolled >=28 days, % where child_alive includes 'no'
    var deceasedCount = childrenEnrolled28d.filter(function(c) {
        return c.child_alive != null && String(c.child_alive).toLowerCase().indexOf('no') !== -1;
    }).length;
    var mortalityRate = childrenEnrolled28d.length > 0 ? (deceasedCount / childrenEnrolled28d.length) * 100 : 0;

    // KMC hours averages
    var kmcTotalArr = [];
    var kmcPrimaryArr = [];
    var kmcSecondaryArr = [];
    visitRows.forEach(function(row) {
        var total = parseFloat(row.total_kmc_hours);
        if (!isNaN(total)) kmcTotalArr.push(total);
        var primary = parseFloat(row.kmc_hours);
        if (!isNaN(primary)) kmcPrimaryArr.push(primary);
        var secondary = parseFloat(row.kmc_hours_secondary);
        if (!isNaN(secondary)) kmcSecondaryArr.push(secondary);
    });
    var avgKmcHours = kmcTotalArr.length > 0 ? kmcTotalArr.reduce(function(a, b) { return a + b; }, 0) / kmcTotalArr.length : 0;
    var avgKmcHoursPrimary = kmcPrimaryArr.length > 0 ? kmcPrimaryArr.reduce(function(a, b) { return a + b; }, 0) / kmcPrimaryArr.length : 0;
    var avgKmcHoursSecondary = kmcSecondaryArr.length > 0 ? kmcSecondaryArr.reduce(function(a, b) { return a + b; }, 0) / kmcSecondaryArr.length : 0;

    // Referrals
    var referralsMade = visitRows.filter(function(row) {
        return row.child_referred != null && String(row.child_referred).toLowerCase() === 'yes';
    }).length;
    var referralsCompleted = visitRows.filter(function(row) {
        return row.child_referred != null && String(row.child_referred).toLowerCase() === 'yes' &&
               row.child_taken_to_hospital != null && String(row.child_taken_to_hospital).toLowerCase() === 'yes';
    }).length;
    var referralCompletionRate = referralsMade > 0 ? (referralsCompleted / referralsMade) * 100 : 0;

    // Avg days to first visit
    var daysToFirstArr = [];
    children.forEach(function(c) {
        if (c.reg_date && c.firstVisitDate) {
            var regD = new Date(c.reg_date);
            var firstD = new Date(c.firstVisitDate);
            if (!isNaN(regD.getTime()) && !isNaN(firstD.getTime())) {
                var diff = Math.floor((firstD - regD) / 86400000);
                daysToFirstArr.push(diff);
            }
        }
    });
    var avgDaysToFirstVisit = daysToFirstArr.length > 0 ? daysToFirstArr.reduce(function(a, b) { return a + b; }, 0) / daysToFirstArr.length : 0;

    // Visit timeliness
    var timelyVisits = visitRows.filter(function(row) {
        return row.visit_timeliness != null && row.visit_timeliness !== '' &&
               String(row.visit_timeliness).toLowerCase().indexOf('on_time') !== -1;
    }).length;
    var visitsOnSchedule = visitRows.length > 0 ? (timelyVisits / visitRows.length) * 100 : 0;

    // Danger signs assessed
    var dangerAssessed = visitRows.filter(function(row) {
        return row.danger_sign_positive != null && row.danger_sign_positive !== '';
    }).length;
    var dangerSignsAssessed = visitRows.length > 0 ? (dangerAssessed / visitRows.length) * 100 : 0;

    // Danger sign incidence
    var dangerPositive = visitRows.filter(function(row) {
        if (row.danger_sign_positive == null || row.danger_sign_positive === '') return false;
        var val = String(row.danger_sign_positive).toLowerCase();
        return val === 'yes' || val === 'true' || val === '1';
    }).length;
    var dangerSignIncidence = visitRows.length > 0 ? (dangerPositive / visitRows.length) * 100 : 0;

    // Avg weight by visit number
    var weightByVisitNum = {};
    var weightCountByVisitNum = {};
    visitRows.forEach(function(row) {
        var vn = parseInt(row.visit_number);
        var w = parseFloat(row.weight);
        if (!isNaN(vn) && !isNaN(w)) {
            if (!weightByVisitNum[vn]) { weightByVisitNum[vn] = 0; weightCountByVisitNum[vn] = 0; }
            weightByVisitNum[vn] += w;
            weightCountByVisitNum[vn] += 1;
        }
    });
    var avgWeightByVisitNumber = {};
    Object.keys(weightByVisitNum).forEach(function(vn) {
        avgWeightByVisitNumber[vn] = weightByVisitNum[vn] / weightCountByVisitNum[vn];
    });

    // Feeding breakdown
    var feedingBreakdown = {};
    visitRows.forEach(function(row) {
        if (row.feeding_provided != null && row.feeding_provided !== '') {
            var key = String(row.feeding_provided);
            feedingBreakdown[key] = (feedingBreakdown[key] || 0) + 1;
        }
    });

    // EBF rate: % of children whose latest visit has exclusive breastfeeding
    var ebfCount = 0;
    var feedingAssessedCount = 0;
    children.forEach(function(c) {
        for (var i = c.visits.length - 1; i >= 0; i--) {
            if (c.visits[i].feeding_provided != null && c.visits[i].feeding_provided !== '') {
                feedingAssessedCount++;
                var val = String(c.visits[i].feeding_provided).toLowerCase();
                if (val.indexOf('exclusive') !== -1 || val.indexOf('ebf') !== -1 || val === 'breast_milk_only') {
                    ebfCount++;
                }
                break;
            }
        }
    });
    var ebfRate = feedingAssessedCount > 0 ? (ebfCount / feedingAssessedCount) * 100 : 0;

    // % visits with >= 8hrs total KMC
    var kmcOver8 = kmcTotalArr.filter(function(h) { return h >= 8; }).length;
    var pctKmc8Plus = kmcTotalArr.length > 0 ? (kmcOver8 / kmcTotalArr.length) * 100 : 0;

    return {
        totalEnrolled: totalEnrolled,
        activeChildren: activeChildren,
        totalVisits: totalVisits,
        avgVisitsPerChild: avgVisitsPerChild,
        retentionRate28d: retentionRate28d,
        mortalityRate: mortalityRate,
        avgKmcHours: avgKmcHours,
        avgKmcHoursPrimary: avgKmcHoursPrimary,
        avgKmcHoursSecondary: avgKmcHoursSecondary,
        referralsMade: referralsMade,
        referralCompletionRate: referralCompletionRate,
        avgDaysToFirstVisit: avgDaysToFirstVisit,
        visitsOnSchedule: visitsOnSchedule,
        dangerSignsAssessed: dangerSignsAssessed,
        dangerSignIncidence: dangerSignIncidence,
        avgWeightByVisitNumber: avgWeightByVisitNumber,
        feedingBreakdown: feedingBreakdown,
        ebfRate: ebfRate,
        pctKmc8Plus: pctKmc8Plus
    };
}

function computeWeeklyData(visitRows, children) {
    if (children.length === 0) return { weeklyVisits: [], cumulativeEnrollment: [], weeklyKmcHours: [] };

    var getWeekKey = function(dateStr) {
        if (!dateStr) return null;
        var d = new Date(dateStr);
        if (isNaN(d.getTime())) return null;
        var jan1 = new Date(d.getFullYear(), 0, 1);
        var weekNum = Math.ceil(((d - jan1) / 86400000 + jan1.getDay() + 1) / 7);
        return d.getFullYear() + '-W' + String(weekNum).padStart(2, '0');
    };

    var weekKeyToDate = function(weekKey) {
        var parts = weekKey.split('-W');
        var year = parseInt(parts[0]);
        var wStr = parseInt(parts[1]);
        var jan1 = new Date(year, 0, 1);
        var dayOffset = (jan1.getDay() + 6) % 7;
        var firstMonday = new Date(jan1);
        firstMonday.setDate(jan1.getDate() - dayOffset);
        firstMonday.setDate(firstMonday.getDate() + (wStr - 1) * 7);
        return firstMonday.toISOString().split('T')[0];
    };

    // Enrollment by week
    var enrollmentByWeek = {};
    children.forEach(function(c) {
        var firstDate = c.visits[0] && c.visits[0].visit_date;
        var week = getWeekKey(firstDate);
        if (week) enrollmentByWeek[week] = (enrollmentByWeek[week] || 0) + 1;
    });

    // Visits by week
    var visitsByWeek = {};
    visitRows.forEach(function(v) {
        var week = getWeekKey(v.visit_date);
        if (week) visitsByWeek[week] = (visitsByWeek[week] || 0) + 1;
    });

    // KMC hours by week
    var kmcHoursByWeek = {};
    var kmcCountByWeek = {};
    var kmcSecByWeek = {};
    var kmcSecCountByWeek = {};
    visitRows.forEach(function(v) {
        var week = getWeekKey(v.visit_date);
        if (!week) return;
        var primary = parseFloat(v.kmc_hours);
        if (!isNaN(primary)) {
            kmcHoursByWeek[week] = (kmcHoursByWeek[week] || 0) + primary;
            kmcCountByWeek[week] = (kmcCountByWeek[week] || 0) + 1;
        }
        var secondary = parseFloat(v.kmc_hours_secondary);
        if (!isNaN(secondary)) {
            kmcSecByWeek[week] = (kmcSecByWeek[week] || 0) + secondary;
            kmcSecCountByWeek[week] = (kmcSecCountByWeek[week] || 0) + 1;
        }
    });

    var allWeeks = Object.keys(enrollmentByWeek).concat(Object.keys(visitsByWeek)).concat(Object.keys(kmcHoursByWeek));
    var uniqueWeeks = [];
    var seen = {};
    allWeeks.forEach(function(w) { if (!seen[w]) { seen[w] = true; uniqueWeeks.push(w); } });
    uniqueWeeks.sort();

    var cumulative = 0;
    var cumulativeEnrollment = uniqueWeeks.map(function(week) {
        cumulative += (enrollmentByWeek[week] || 0);
        return { week: week, date: weekKeyToDate(week), count: cumulative };
    });

    var weeklyVisits = uniqueWeeks.map(function(week) {
        return { week: week, date: weekKeyToDate(week), count: visitsByWeek[week] || 0 };
    });

    var weeklyKmcHours = uniqueWeeks.map(function(week) {
        var avgPrimary = kmcCountByWeek[week] ? kmcHoursByWeek[week] / kmcCountByWeek[week] : null;
        var avgSecondary = kmcSecCountByWeek[week] ? kmcSecByWeek[week] / kmcSecCountByWeek[week] : null;
        return { week: week, date: weekKeyToDate(week), primary: avgPrimary, secondary: avgSecondary };
    });

    return { weeklyVisits: weeklyVisits, cumulativeEnrollment: cumulativeEnrollment, weeklyKmcHours: weeklyKmcHours };
}

function WorkflowUI({ definition, instance, workers, pipelines, links, actions, onUpdateState }) {

    // --- State ---
    var [currentView, setCurrentView] = React.useState('overview');
    var [sortColumn, setSortColumn] = React.useState('level');
    var [sortDirection, setSortDirection] = React.useState('asc');

    // --- Chart refs ---
    var enrollmentChartRef = React.useRef(null);
    var enrollmentChartInstance = React.useRef(null);
    var visitsChartRef = React.useRef(null);
    var visitsChartInstance = React.useRef(null);
    var kmcHoursChartRef = React.useRef(null);
    var kmcHoursChartInstance = React.useRef(null);
    var feedingChartRef = React.useRef(null);
    var feedingChartInstance = React.useRef(null);
    var weightChartRef = React.useRef(null);
    var weightChartInstance = React.useRef(null);

    // --- Computed data ---
    var visitRows = pipelines && pipelines.visits && pipelines.visits.rows ? pipelines.visits.rows : [];
    var children = React.useMemo(function() { return groupVisitsByChild(visitRows); }, [visitRows]);
    var metrics = React.useMemo(function() { return computeProjectMetrics(children, visitRows); }, [children, visitRows]);
    var weeklyData = React.useMemo(function() { return computeWeeklyData(visitRows, children); }, [visitRows, children]);

    // --- Format helpers ---
    var fmtPct = function(val) {
        if (val == null || isNaN(val)) return '0%';
        return val.toFixed(1) + '%';
    };
    var fmtDecimal1 = function(val) {
        if (val == null || isNaN(val)) return '0.0';
        return val.toFixed(1);
    };
    var fmtInt = function(val) {
        if (val == null || isNaN(val)) return '0';
        return Math.round(val).toLocaleString();
    };
    var formatValue = function(val, format) {
        if (format === 'pct') return fmtPct(val);
        if (format === 'decimal1') return fmtDecimal1(val);
        if (format === 'int') return fmtInt(val);
        return String(val != null ? val : '-');
    };

    // --- Enrollment chart ---
    React.useEffect(function() {
        if (currentView !== 'overview') return;
        if (!enrollmentChartRef.current || !window.Chart) return;
        if (weeklyData.cumulativeEnrollment.length === 0) return;

        if (enrollmentChartInstance.current) enrollmentChartInstance.current.destroy();

        var ctx = enrollmentChartRef.current.getContext('2d');
        enrollmentChartInstance.current = new window.Chart(ctx, {
            type: 'line',
            data: {
                labels: weeklyData.cumulativeEnrollment.map(function(d) { return d.date; }),
                datasets: [{
                    label: 'Cumulative Enrollment',
                    data: weeklyData.cumulativeEnrollment.map(function(d) { return d.count; }),
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 3
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { type: 'time', time: { unit: 'week', tooltipFormat: 'MMM d, yyyy' }, ticks: { font: { size: 10 } } },
                    y: { beginAtZero: true, ticks: { font: { size: 10 } } }
                }
            }
        });

        return function() {
            if (enrollmentChartInstance.current) { enrollmentChartInstance.current.destroy(); enrollmentChartInstance.current = null; }
        };
    }, [currentView, weeklyData]);

    // --- Visits per week chart ---
    React.useEffect(function() {
        if (currentView !== 'overview') return;
        if (!visitsChartRef.current || !window.Chart) return;
        if (weeklyData.weeklyVisits.length === 0) return;

        if (visitsChartInstance.current) visitsChartInstance.current.destroy();

        var ctx = visitsChartRef.current.getContext('2d');
        visitsChartInstance.current = new window.Chart(ctx, {
            type: 'bar',
            data: {
                labels: weeklyData.weeklyVisits.map(function(d) { return d.date; }),
                datasets: [{
                    label: 'Visits',
                    data: weeklyData.weeklyVisits.map(function(d) { return d.count; }),
                    backgroundColor: 'rgba(16, 185, 129, 0.6)',
                    borderColor: '#10b981',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { type: 'time', time: { unit: 'week', tooltipFormat: 'MMM d, yyyy' }, ticks: { font: { size: 10 } } },
                    y: { beginAtZero: true, ticks: { font: { size: 10 }, stepSize: 1 } }
                }
            }
        });

        return function() {
            if (visitsChartInstance.current) { visitsChartInstance.current.destroy(); visitsChartInstance.current = null; }
        };
    }, [currentView, weeklyData]);

    // --- KMC Hours chart (Outcomes view) ---
    React.useEffect(function() {
        if (currentView !== 'outcomes') return;
        if (!kmcHoursChartRef.current || !window.Chart) return;
        if (weeklyData.weeklyKmcHours.length === 0) return;

        if (kmcHoursChartInstance.current) kmcHoursChartInstance.current.destroy();

        var ctx = kmcHoursChartRef.current.getContext('2d');
        var labels = weeklyData.weeklyKmcHours.map(function(d) { return d.date; });
        var primaryData = weeklyData.weeklyKmcHours.map(function(d) { return d.primary; });
        var secondaryData = weeklyData.weeklyKmcHours.map(function(d) { return d.secondary; });
        var targetData = weeklyData.weeklyKmcHours.map(function() { return 8; });

        kmcHoursChartInstance.current = new window.Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Primary Caregiver',
                        data: primaryData,
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59, 130, 246, 0.05)',
                        tension: 0.3,
                        pointRadius: 3,
                        fill: false
                    },
                    {
                        label: 'Secondary Caregiver',
                        data: secondaryData,
                        borderColor: '#14b8a6',
                        backgroundColor: 'rgba(20, 184, 166, 0.05)',
                        borderDash: [5, 5],
                        tension: 0.3,
                        pointRadius: 3,
                        fill: false
                    },
                    {
                        label: '8hr Target',
                        data: targetData,
                        borderColor: '#ef4444',
                        borderDash: [2, 4],
                        borderWidth: 1,
                        pointRadius: 0,
                        fill: false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: true, position: 'bottom', labels: { font: { size: 11 } } } },
                scales: {
                    x: { type: 'time', time: { unit: 'week', tooltipFormat: 'MMM d, yyyy' }, ticks: { font: { size: 10 } } },
                    y: { beginAtZero: true, title: { display: true, text: 'Hours', font: { size: 11 } }, ticks: { font: { size: 10 } } }
                }
            }
        });

        return function() {
            if (kmcHoursChartInstance.current) { kmcHoursChartInstance.current.destroy(); kmcHoursChartInstance.current = null; }
        };
    }, [currentView, weeklyData]);

    // --- Feeding donut chart (Outcomes view) ---
    React.useEffect(function() {
        if (currentView !== 'outcomes') return;
        if (!feedingChartRef.current || !window.Chart) return;

        var keys = Object.keys(metrics.feedingBreakdown);
        if (keys.length === 0) return;

        if (feedingChartInstance.current) feedingChartInstance.current.destroy();

        var colors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];
        var ctx = feedingChartRef.current.getContext('2d');
        feedingChartInstance.current = new window.Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: keys.map(function(k) { return k.replace(/_/g, ' '); }),
                datasets: [{
                    data: keys.map(function(k) { return metrics.feedingBreakdown[k]; }),
                    backgroundColor: keys.map(function(k, i) { return colors[i % colors.length]; }),
                    borderWidth: 2,
                    borderColor: '#fff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: true, position: 'right', labels: { font: { size: 10 }, padding: 8 } }
                }
            }
        });

        return function() {
            if (feedingChartInstance.current) { feedingChartInstance.current.destroy(); feedingChartInstance.current = null; }
        };
    }, [currentView, metrics]);

    // --- Weight by visit number chart (Outcomes view) ---
    React.useEffect(function() {
        if (currentView !== 'outcomes') return;
        if (!weightChartRef.current || !window.Chart) return;

        var visitNums = Object.keys(metrics.avgWeightByVisitNumber).map(function(k) { return parseInt(k); }).sort(function(a, b) { return a - b; });
        if (visitNums.length === 0) return;

        if (weightChartInstance.current) weightChartInstance.current.destroy();

        var ctx = weightChartRef.current.getContext('2d');
        var thresholdData = visitNums.map(function() { return 2500; });
        weightChartInstance.current = new window.Chart(ctx, {
            type: 'line',
            data: {
                labels: visitNums.map(function(vn) { return 'Visit ' + vn; }),
                datasets: [
                    {
                        label: 'Avg Weight (g)',
                        data: visitNums.map(function(vn) { return Math.round(metrics.avgWeightByVisitNumber[vn]); }),
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 4
                    },
                    {
                        label: '2500g Threshold',
                        data: thresholdData,
                        borderColor: '#ef4444',
                        borderDash: [4, 4],
                        borderWidth: 1,
                        pointRadius: 0,
                        fill: false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: true, position: 'bottom', labels: { font: { size: 11 } } } },
                scales: {
                    x: { ticks: { font: { size: 10 } } },
                    y: { beginAtZero: false, title: { display: true, text: 'Grams', font: { size: 11 } }, ticks: { font: { size: 10 } } }
                }
            }
        });

        return function() {
            if (weightChartInstance.current) { weightChartInstance.current.destroy(); weightChartInstance.current = null; }
        };
    }, [currentView, metrics]);

    // --- Loading state ---
    if (!pipelines || !pipelines.visits || !pipelines.visits.rows) {
        return (
            <div className="flex items-center justify-center py-20">
                <div className="text-center">
                    <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-gray-200 border-t-blue-600 mb-4"></div>
                    <p className="text-gray-500 text-sm">Loading project metrics data...</p>
                </div>
            </div>
        );
    }

    // --- Empty state ---
    if (visitRows.length === 0) {
        return (
            <div className="text-center py-16">
                <div className="inline-block p-4 rounded-full bg-gray-100 mb-4">
                    <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                    </svg>
                </div>
                <p className="text-gray-500 text-lg">No KMC visit data found</p>
                <p className="text-gray-400 text-sm mt-1">Pipeline data may still be loading, or no visits have been recorded.</p>
            </div>
        );
    }

    // --- Tab bar ---
    var tabs = [
        { id: 'overview', label: 'Overview' },
        { id: 'outcomes', label: 'Outcomes & Outputs' },
        { id: 'indicators', label: 'Indicators Table' }
    ];

    var TabBar = function() {
        return (
            <div className="flex border-b border-gray-200 mb-6">
                {tabs.map(function(tab) {
                    var isActive = currentView === tab.id;
                    return (
                        <button
                            key={tab.id}
                            onClick={function() { setCurrentView(tab.id); }}
                            className={'px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ' +
                                (isActive ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300')}
                        >
                            {tab.label}
                        </button>
                    );
                })}
            </div>
        );
    };

    // --- KPI Card component ---
    var KpiCard = function(props) {
        return (
            <div className="bg-white rounded-lg shadow-sm p-4">
                <div className="text-sm text-gray-500">{props.title}</div>
                <div className={'text-2xl font-bold mt-1 ' + (props.colorClass || 'text-gray-900')}>{props.value}</div>
                {props.subtitle && <div className="text-xs text-gray-400 mt-1">{props.subtitle}</div>}
            </div>
        );
    };

    // --- Overview View ---
    var OverviewView = function() {
        return (
            <div>
                <div className="grid grid-cols-4 gap-4 mb-6">
                    <KpiCard
                        title="SVNs Enrolled"
                        value={fmtInt(metrics.totalEnrolled)}
                        colorClass="text-blue-600"
                        subtitle="Total unique children"
                    />
                    <KpiCard
                        title="Active SVNs"
                        value={fmtInt(metrics.activeChildren)}
                        colorClass="text-green-600"
                        subtitle={fmtPct(metrics.totalEnrolled > 0 ? (metrics.activeChildren / metrics.totalEnrolled) * 100 : 0) + ' of enrolled'}
                    />
                    <KpiCard
                        title="28-Day Retention"
                        value={fmtPct(metrics.retentionRate28d)}
                        colorClass={metrics.retentionRate28d >= 80 ? 'text-green-600' : metrics.retentionRate28d >= 60 ? 'text-amber-600' : 'text-red-600'}
                        subtitle="Among children enrolled 28+ days"
                    />
                    <KpiCard
                        title="Mortality Rate"
                        value={fmtPct(metrics.mortalityRate)}
                        colorClass={metrics.mortalityRate <= 2 ? 'text-green-600' : metrics.mortalityRate <= 5 ? 'text-amber-600' : 'text-red-600'}
                        subtitle="28-day mortality"
                    />
                </div>
                <div className="grid grid-cols-4 gap-4 mb-6">
                    <KpiCard
                        title="Avg KMC Hours"
                        value={fmtDecimal1(metrics.avgKmcHours)}
                        colorClass={metrics.avgKmcHours >= 8 ? 'text-green-600' : metrics.avgKmcHours >= 5 ? 'text-amber-600' : 'text-red-600'}
                        subtitle="Total (primary + secondary)"
                    />
                    <KpiCard
                        title="Referrals Made"
                        value={fmtInt(metrics.referralsMade)}
                        colorClass="text-amber-600"
                        subtitle={fmtPct(metrics.referralCompletionRate) + ' completion rate'}
                    />
                    <KpiCard
                        title="Total Visits"
                        value={fmtInt(metrics.totalVisits)}
                        colorClass="text-blue-600"
                        subtitle={fmtDecimal1(metrics.avgVisitsPerChild) + ' avg per child'}
                    />
                    <KpiCard
                        title="Avg Days to 1st Visit"
                        value={fmtDecimal1(metrics.avgDaysToFirstVisit)}
                        colorClass={metrics.avgDaysToFirstVisit <= 3 ? 'text-green-600' : metrics.avgDaysToFirstVisit <= 7 ? 'text-amber-600' : 'text-red-600'}
                        subtitle="From registration"
                    />
                </div>

                <div className="grid grid-cols-2 gap-4 mb-6">
                    <div className="bg-white rounded-lg shadow-sm p-4">
                        <h3 className="text-sm font-medium text-gray-700 mb-2">Enrollment Trend</h3>
                        <div style={{height: '220px'}}>
                            <canvas ref={enrollmentChartRef}></canvas>
                        </div>
                    </div>
                    <div className="bg-white rounded-lg shadow-sm p-4">
                        <h3 className="text-sm font-medium text-gray-700 mb-2">Visits Per Week</h3>
                        <div style={{height: '220px'}}>
                            <canvas ref={visitsChartRef}></canvas>
                        </div>
                    </div>
                </div>

                <div className="text-center">
                    <button
                        onClick={function() { setCurrentView('outcomes'); }}
                        className="text-blue-600 hover:text-blue-800 text-sm font-medium"
                    >
                        View Detailed Outcomes &rarr;
                    </button>
                </div>
            </div>
        );
    };

    // --- Outcomes & Outputs View ---
    var OutcomesView = function() {
        return (
            <div>
                {/* KMC Practice */}
                <div className="bg-white rounded-lg shadow-sm p-5 mb-6">
                    <h3 className="text-base font-semibold text-gray-800 mb-4">KMC Practice</h3>
                    <div style={{height: '240px'}} className="mb-4">
                        <canvas ref={kmcHoursChartRef}></canvas>
                    </div>
                    <div className="grid grid-cols-3 gap-4 mt-3">
                        <div className="text-center p-3 bg-blue-50 rounded-lg">
                            <div className="text-xs text-gray-500 mb-1">Mean Primary Hours</div>
                            <div className="text-lg font-bold text-blue-600">{fmtDecimal1(metrics.avgKmcHoursPrimary)}</div>
                        </div>
                        <div className="text-center p-3 bg-teal-50 rounded-lg">
                            <div className="text-xs text-gray-500 mb-1">Mean Secondary Hours</div>
                            <div className="text-lg font-bold text-teal-600">{fmtDecimal1(metrics.avgKmcHoursSecondary)}</div>
                        </div>
                        <div className="text-center p-3 bg-green-50 rounded-lg">
                            <div className="text-xs text-gray-500 mb-1">Visits with 8+ hrs</div>
                            <div className="text-lg font-bold text-green-600">{fmtPct(metrics.pctKmc8Plus)}</div>
                        </div>
                    </div>
                </div>

                {/* Nutrition & Feeding */}
                <div className="bg-white rounded-lg shadow-sm p-5 mb-6">
                    <h3 className="text-base font-semibold text-gray-800 mb-4">Nutrition & Feeding</h3>
                    <div className="grid grid-cols-2 gap-6">
                        <div className="flex flex-col items-center justify-center">
                            <div className="text-xs text-gray-500 mb-2">Exclusive Breastfeeding Rate</div>
                            <div className={'text-4xl font-bold ' + (metrics.ebfRate >= 60 ? 'text-green-600' : metrics.ebfRate >= 40 ? 'text-amber-600' : 'text-red-600')}>
                                {fmtPct(metrics.ebfRate)}
                            </div>
                            <div className="text-xs text-gray-400 mt-1">Based on most recent visit per child</div>
                        </div>
                        <div style={{height: '200px'}}>
                            <canvas ref={feedingChartRef}></canvas>
                        </div>
                    </div>
                </div>

                {/* Health Outcomes */}
                <div className="bg-white rounded-lg shadow-sm p-5 mb-6">
                    <h3 className="text-base font-semibold text-gray-800 mb-4">Health Outcomes</h3>
                    <div style={{height: '240px'}} className="mb-4">
                        <canvas ref={weightChartRef}></canvas>
                    </div>
                    <div className="grid grid-cols-2 gap-4 mt-3">
                        <div className="text-center p-3 bg-red-50 rounded-lg">
                            <div className="text-xs text-gray-500 mb-1">Danger Sign Incidence</div>
                            <div className={'text-lg font-bold ' + (metrics.dangerSignIncidence <= 10 ? 'text-green-600' : metrics.dangerSignIncidence <= 25 ? 'text-amber-600' : 'text-red-600')}>
                                {fmtPct(metrics.dangerSignIncidence)}
                            </div>
                        </div>
                        <div className="text-center p-3 bg-blue-50 rounded-lg">
                            <div className="text-xs text-gray-500 mb-1">Referral Completion Rate</div>
                            <div className={'text-lg font-bold ' + (metrics.referralCompletionRate >= 80 ? 'text-green-600' : metrics.referralCompletionRate >= 60 ? 'text-amber-600' : 'text-red-600')}>
                                {fmtPct(metrics.referralCompletionRate)}
                            </div>
                        </div>
                    </div>
                </div>

                {/* Visit Quality */}
                <div className="bg-white rounded-lg shadow-sm p-5 mb-6">
                    <h3 className="text-base font-semibold text-gray-800 mb-4">Visit Quality</h3>
                    <div className="grid grid-cols-3 gap-4">
                        <div className="text-center p-4 bg-white border border-gray-200 rounded-lg">
                            <div className="text-xs text-gray-500 mb-2">Visits on Schedule</div>
                            <div className={'text-2xl font-bold ' + (metrics.visitsOnSchedule >= 80 ? 'text-green-600' : metrics.visitsOnSchedule >= 60 ? 'text-amber-600' : 'text-red-600')}>
                                {fmtPct(metrics.visitsOnSchedule)}
                            </div>
                        </div>
                        <div className="text-center p-4 bg-white border border-gray-200 rounded-lg">
                            <div className="text-xs text-gray-500 mb-2">Danger Signs Assessed</div>
                            <div className={'text-2xl font-bold ' + (metrics.dangerSignsAssessed >= 90 ? 'text-green-600' : metrics.dangerSignsAssessed >= 70 ? 'text-amber-600' : 'text-red-600')}>
                                {fmtPct(metrics.dangerSignsAssessed)}
                            </div>
                        </div>
                        <div className="text-center p-4 bg-white border border-gray-200 rounded-lg">
                            <div className="text-xs text-gray-500 mb-2">Avg Visits per Child</div>
                            <div className="text-2xl font-bold text-blue-600">
                                {fmtDecimal1(metrics.avgVisitsPerChild)}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        );
    };

    // --- Indicators Table View ---
    var IndicatorsView = function() {
        var indicators = [
            {level: 'Impact', name: '28-Day Mortality Rate', value: metrics.mortalityRate, format: 'pct', target: null, lowerIsBetter: true},
            {level: 'Outcome', name: 'Avg KMC Hours (Primary)', value: metrics.avgKmcHoursPrimary, format: 'decimal1', target: 8, lowerIsBetter: false},
            {level: 'Outcome', name: 'Avg KMC Hours (Secondary)', value: metrics.avgKmcHoursSecondary, format: 'decimal1', target: null, lowerIsBetter: false},
            {level: 'Outcome', name: 'Exclusive Breastfeeding Rate', value: metrics.ebfRate, format: 'pct', target: null, lowerIsBetter: false},
            {level: 'Outcome', name: 'Referral Completion Rate', value: metrics.referralCompletionRate, format: 'pct', target: 80, lowerIsBetter: false},
            {level: 'Output', name: 'SVNs Enrolled', value: metrics.totalEnrolled, format: 'int', target: null, lowerIsBetter: false},
            {level: 'Output', name: 'Avg Days to First Visit', value: metrics.avgDaysToFirstVisit, format: 'decimal1', target: 3, lowerIsBetter: true},
            {level: 'Output', name: '28-Day Retention Rate', value: metrics.retentionRate28d, format: 'pct', target: 80, lowerIsBetter: false},
            {level: 'Output', name: 'Referrals Made', value: metrics.referralsMade, format: 'int', target: null, lowerIsBetter: false},
            {level: 'Output', name: 'Visits on Schedule', value: metrics.visitsOnSchedule, format: 'pct', target: 80, lowerIsBetter: false},
            {level: 'Output', name: 'Danger Signs Assessed', value: metrics.dangerSignsAssessed, format: 'pct', target: 90, lowerIsBetter: false},
            {level: 'Output', name: 'Avg Visits per Child', value: metrics.avgVisitsPerChild, format: 'decimal1', target: 5, lowerIsBetter: false}
        ];

        var getStatus = function(ind) {
            if (ind.target == null) return { label: 'N/A', color: 'bg-gray-100 text-gray-600' };
            var val = ind.value || 0;
            var target = ind.target;
            var met = false;
            var close = false;
            if (ind.lowerIsBetter) {
                met = val <= target;
                close = val <= target * 1.2;
            } else {
                met = val >= target;
                close = val >= target * 0.8;
            }
            if (met) return { label: 'On Track', color: 'bg-green-100 text-green-800' };
            if (close) return { label: 'Watch', color: 'bg-amber-100 text-amber-800' };
            return { label: 'Action Needed', color: 'bg-red-100 text-red-800' };
        };

        var levelOrder = { 'Impact': 0, 'Outcome': 1, 'Output': 2 };

        // Sort indicators
        var sorted = indicators.slice().sort(function(a, b) {
            var aVal, bVal;
            if (sortColumn === 'level') {
                aVal = levelOrder[a.level] || 0;
                bVal = levelOrder[b.level] || 0;
            } else if (sortColumn === 'name') {
                aVal = a.name.toLowerCase();
                bVal = b.name.toLowerCase();
            } else if (sortColumn === 'value') {
                aVal = a.value || 0;
                bVal = b.value || 0;
            } else if (sortColumn === 'target') {
                aVal = a.target || 0;
                bVal = b.target || 0;
            } else if (sortColumn === 'status') {
                var sA = getStatus(a).label;
                var sB = getStatus(b).label;
                var statusOrder = { 'Action Needed': 0, 'Watch': 1, 'On Track': 2, 'N/A': 3 };
                aVal = statusOrder[sA] != null ? statusOrder[sA] : 4;
                bVal = statusOrder[sB] != null ? statusOrder[sB] : 4;
            } else {
                aVal = 0;
                bVal = 0;
            }
            if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1;
            if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1;
            return 0;
        });

        var handleSort = function(col) {
            if (sortColumn === col) {
                setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
            } else {
                setSortColumn(col);
                setSortDirection('asc');
            }
        };

        var SortHeader = function(props) {
            var arrow = sortColumn === props.col ? (sortDirection === 'asc' ? ' \\u2191' : ' \\u2193') : '';
            return (
                <th
                    className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none"
                    onClick={function() { handleSort(props.col); }}
                >
                    {props.label}{arrow}
                </th>
            );
        };

        var levelColors = {
            'Impact': 'bg-purple-100 text-purple-800',
            'Outcome': 'bg-blue-100 text-blue-800',
            'Output': 'bg-gray-100 text-gray-700'
        };

        return (
            <div className="bg-white rounded-lg shadow-sm overflow-hidden">
                <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                        <tr>
                            <SortHeader col="level" label="Level" />
                            <SortHeader col="name" label="Indicator" />
                            <SortHeader col="value" label="Current Value" />
                            <SortHeader col="target" label="Target" />
                            <SortHeader col="status" label="Status" />
                        </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                        {sorted.map(function(ind, idx) {
                            var status = getStatus(ind);
                            return (
                                <tr key={idx} className="hover:bg-gray-50">
                                    <td className="px-4 py-3">
                                        <span className={'inline-block px-2 py-0.5 text-xs font-medium rounded-full ' + (levelColors[ind.level] || '')}>
                                            {ind.level}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3 text-sm text-gray-900">{ind.name}</td>
                                    <td className="px-4 py-3 text-sm font-medium text-gray-900">{formatValue(ind.value, ind.format)}</td>
                                    <td className="px-4 py-3 text-sm text-gray-500">{ind.target != null ? formatValue(ind.target, ind.format) : '\u2014'}</td>
                                    <td className="px-4 py-3">
                                        <span className={'inline-block px-2 py-0.5 text-xs font-medium rounded-full ' + status.color}>
                                            {status.label}
                                        </span>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        );
    };

    // --- Main render ---
    return (
        <div className="space-y-4">
            <TabBar />
            {currentView === 'overview' && <OverviewView />}
            {currentView === 'outcomes' && <OutcomesView />}
            {currentView === 'indicators' && <IndicatorsView />}
        </div>
    );
}"""

TEMPLATE = {
    "key": "kmc_project_metrics",
    "name": "KMC Project Metrics",
    "description": "Program-level M&E dashboard showing enrollment, health outcomes, KMC practice, and visit quality indicators",
    "icon": "fa-chart-bar",
    "color": "indigo",
    "definition": DEFINITION,
    "render_code": RENDER_CODE,
    "pipeline_schemas": PIPELINE_SCHEMAS,
}
