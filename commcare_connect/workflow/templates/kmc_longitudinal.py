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

    // --- Computed data ---
    const visitRows = pipelines && pipelines.visits ? (pipelines.visits.rows || []) : [];
    const children = React.useMemo(() => groupVisitsByChild(visitRows), [visitRows]);
    const kpis = React.useMemo(() => computeKPIs(children), [children]);

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

    // --- Timeline Stub ---
    const TimelineStub = () => (
        <div className="space-y-4">
            <button
                onClick={handleBackToDashboard}
                className="inline-flex items-center text-sm text-blue-600 hover:text-blue-800"
            >
                &larr; Back to Dashboard
            </button>
            <div className="bg-white rounded-lg shadow-sm p-8 text-center">
                <p className="text-gray-500 text-lg">Child Timeline</p>
                <p className="text-gray-400 text-sm mt-2">Coming soon</p>
            </div>
        </div>
    );

    // --- Child List Stub ---
    const ChildListStub = () => (
        <div className="space-y-4">
            <button
                onClick={handleBackToDashboard}
                className="inline-flex items-center text-sm text-blue-600 hover:text-blue-800"
            >
                &larr; Back to Dashboard
            </button>
            <div className="bg-white rounded-lg shadow-sm p-8 text-center">
                <p className="text-gray-500 text-lg">
                    Child List (filter: {childListFilter})
                </p>
                <p className="text-gray-400 text-sm mt-2">Coming soon</p>
            </div>
        </div>
    );

    // --- View Router ---
    if (currentView === 'timeline' && selectedChildId) {
        return <TimelineStub />;
    }
    if (currentView === 'childList') {
        return <ChildListStub />;
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
