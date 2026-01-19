"""
Seed command for creating example pipeline templates.

Usage:
    python manage.py seed_pipeline_templates --template visit_list
    python manage.py seed_pipeline_templates --template flw_summary
    python manage.py seed_pipeline_templates --template weight_tracker
    python manage.py seed_pipeline_templates --list
"""

import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


# =============================================================================
# Pipeline Templates - Schema Definitions
# =============================================================================

VISIT_LIST_SCHEMA = {
    "name": "Visit Data Explorer",
    "description": "Explore visit-level data with custom field extraction",
    "version": 1,
    "grouping_key": "username",
    "terminal_stage": "visit_level",
    "linking_field": "entity_id",
    "fields": [
        {
            "name": "form_name",
            "path": "form.@name",
            "aggregation": "first",
            "description": "Name of the form submitted",
        },
        {
            "name": "entity_name",
            "paths": ["form.case.update.name", "form.entity_name"],
            "aggregation": "first",
            "description": "Name of the beneficiary/entity",
        },
    ],
    "histograms": [],
    "filters": {},
}

FLW_SUMMARY_SCHEMA = {
    "name": "FLW Performance Summary",
    "description": "Aggregated statistics per frontline worker",
    "version": 1,
    "grouping_key": "username",
    "terminal_stage": "aggregated",
    "linking_field": "entity_id",
    "fields": [
        {
            "name": "unique_entities",
            "path": "entity_id",
            "aggregation": "count_unique",
            "description": "Number of unique beneficiaries visited",
        },
    ],
    "histograms": [],
    "filters": {},
}

WEIGHT_TRACKER_SCHEMA = {
    "name": "Weight Tracker",
    "description": "Track weight measurements across visits",
    "version": 1,
    "grouping_key": "username",
    "terminal_stage": "visit_level",
    "linking_field": "beneficiary_case_id",
    "fields": [
        {
            "name": "beneficiary_case_id",
            "paths": ["form.case.@case_id", "form.beneficiary_case_id"],
            "aggregation": "first",
            "description": "Unique beneficiary identifier",
        },
        {
            "name": "weight",
            "paths": [
                "form.anthropometric.child_weight",
                "form.weight",
                "form.case.update.weight",
            ],
            "aggregation": "first",
            "transform": "kg_to_g",
            "description": "Weight in grams",
        },
        {
            "name": "visit_date",
            "paths": ["form.visit_date", "form.date"],
            "aggregation": "first",
            "transform": "date",
            "description": "Date of the visit",
        },
        {
            "name": "child_name",
            "paths": ["form.child_name", "form.case.update.name", "form.beneficiary_name"],
            "aggregation": "first",
            "description": "Name of the child/beneficiary",
        },
    ],
    "histograms": [
        {
            "name": "weight_distribution",
            "path": "form.anthropometric.child_weight",
            "paths": [
                "form.anthropometric.child_weight",
                "form.weight",
                "form.case.update.weight",
            ],
            "lower_bound": 1000,
            "upper_bound": 5000,
            "num_bins": 8,
            "bin_name_prefix": "weight",
            "transform": "kg_to_g",
            "description": "Weight distribution in grams",
        },
    ],
    "filters": {},
}


# =============================================================================
# Render Code Templates
# =============================================================================

VISIT_LIST_RENDER_CODE = """function PipelineUI({ data, definition, onRefresh }) {
    const rows = data?.rows || [];
    const schema = definition?.schema || {};
    const fields = schema.fields || [];

    const [sortField, setSortField] = React.useState('visit_date');
    const [sortDir, setSortDir] = React.useState('desc');
    const [filterText, setFilterText] = React.useState('');

    // Sort and filter rows
    const processedRows = React.useMemo(() => {
        let result = [...rows];

        // Filter
        if (filterText) {
            const lower = filterText.toLowerCase();
            result = result.filter(row =>
                row.username?.toLowerCase().includes(lower) ||
                row.entity_name?.toLowerCase().includes(lower) ||
                row.entity_id?.toLowerCase().includes(lower)
            );
        }

        // Sort
        result.sort((a, b) => {
            let aVal = a[sortField] || a.computed?.[sortField] || '';
            let bVal = b[sortField] || b.computed?.[sortField] || '';
            if (typeof aVal === 'string') aVal = aVal.toLowerCase();
            if (typeof bVal === 'string') bVal = bVal.toLowerCase();
            if (aVal < bVal) return sortDir === 'asc' ? -1 : 1;
            if (aVal > bVal) return sortDir === 'asc' ? 1 : -1;
            return 0;
        });

        return result;
    }, [rows, sortField, sortDir, filterText]);

    const handleSort = (field) => {
        if (sortField === field) {
            setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
        } else {
            setSortField(field);
            setSortDir('asc');
        }
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="bg-white rounded-lg shadow-sm p-6">
                <div className="flex justify-between items-start">
                    <div>
                        <h1 className="text-2xl font-bold text-gray-900">
                            {definition?.name || 'Visit Data'}
                        </h1>
                        <p className="text-gray-600 mt-1">
                            {definition?.description}
                        </p>
                    </div>
                    <div className="flex items-center gap-2">
                        {data?.from_cache && (
                            <span className="px-3 py-1 bg-green-100 text-green-800 rounded text-sm">
                                Cached
                            </span>
                        )}
                        <button
                            onClick={onRefresh}
                            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                        >
                            <i className="fa-solid fa-arrows-rotate mr-2"></i>
                            Refresh
                        </button>
                    </div>
                </div>
            </div>

            {/* Controls */}
            <div className="bg-white rounded-lg shadow-sm p-4">
                <div className="flex items-center gap-4">
                    <div className="flex-1">
                        <input
                            type="text"
                            placeholder="Filter by username or entity..."
                            value={filterText}
                            onChange={(e) => setFilterText(e.target.value)}
                            className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                        />
                    </div>
                    <div className="text-sm text-gray-500">
                        {processedRows.length} of {rows.length} visits
                    </div>
                </div>
            </div>

            {/* Data Table */}
            <div className="bg-white rounded-lg shadow-sm overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th
                                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100"
                                    onClick={() => handleSort('username')}
                                >
                                    User {sortField === 'username' && (sortDir === 'asc' ? '↑' : '↓')}
                                </th>
                                <th
                                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100"
                                    onClick={() => handleSort('visit_date')}
                                >
                                    Date {sortField === 'visit_date' && (sortDir === 'asc' ? '↑' : '↓')}
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                    Entity
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                    Status
                                </th>
                                {fields.map(field => (
                                    <th key={field.name} className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                        {field.description || field.name}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {processedRows.slice(0, 200).map((row, idx) => (
                                <tr key={idx} className="hover:bg-gray-50">
                                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                                        {row.username}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                        {row.visit_date || '-'}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                        <div>{row.entity_name || row.computed?.entity_name || '-'}</div>
                                        <div className="text-xs text-gray-500">{row.entity_id}</div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <span className={
                                            row.status === 'approved' ? 'px-2 py-1 text-xs rounded bg-green-100 text-green-800' :
                                            row.status === 'rejected' ? 'px-2 py-1 text-xs rounded bg-red-100 text-red-800' :
                                            'px-2 py-1 text-xs rounded bg-yellow-100 text-yellow-800'
                                        }>
                                            {row.status}
                                        </span>
                                        {row.flagged && (
                                            <span className="ml-2 text-red-500">
                                                <i className="fa-solid fa-flag"></i>
                                            </span>
                                        )}
                                    </td>
                                    {fields.map(field => (
                                        <td key={field.name} className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                            {formatValue(row.computed?.[field.name])}
                                        </td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
                {processedRows.length > 200 && (
                    <div className="px-6 py-3 bg-gray-50 text-sm text-gray-500">
                        Showing first 200 of {processedRows.length} rows
                    </div>
                )}
            </div>
        </div>
    );
}

function formatValue(val) {
    if (val === null || val === undefined) return '-';
    if (typeof val === 'number') return val.toLocaleString();
    if (Array.isArray(val)) return val.length + ' items';
    return String(val);
}
"""

FLW_SUMMARY_RENDER_CODE = """function PipelineUI({ data, definition, onRefresh }) {
    const rows = data?.rows || [];
    const schema = definition?.schema || {};

    // Calculate summary stats
    const totalFLWs = rows.length;
    const totalVisits = rows.reduce((sum, r) => sum + (r.total_visits || 0), 0);
    const avgVisits = totalFLWs > 0 ? Math.round(totalVisits / totalFLWs) : 0;

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="bg-white rounded-lg shadow-sm p-6">
                <div className="flex justify-between items-start">
                    <div>
                        <h1 className="text-2xl font-bold text-gray-900">
                            {definition?.name || 'FLW Summary'}
                        </h1>
                        <p className="text-gray-600 mt-1">
                            {definition?.description}
                        </p>
                    </div>
                    <button
                        onClick={onRefresh}
                        className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                    >
                        <i className="fa-solid fa-arrows-rotate mr-2"></i>
                        Refresh
                    </button>
                </div>
            </div>

            {/* Stats Cards */}
            <div className="grid grid-cols-4 gap-4">
                <div className="bg-white rounded-lg shadow-sm p-4">
                    <div className="text-sm text-gray-500">Total FLWs</div>
                    <div className="text-2xl font-bold text-gray-900">{totalFLWs}</div>
                </div>
                <div className="bg-white rounded-lg shadow-sm p-4">
                    <div className="text-sm text-gray-500">Total Visits</div>
                    <div className="text-2xl font-bold text-gray-900">{totalVisits.toLocaleString()}</div>
                </div>
                <div className="bg-white rounded-lg shadow-sm p-4">
                    <div className="text-sm text-gray-500">Avg Visits/FLW</div>
                    <div className="text-2xl font-bold text-gray-900">{avgVisits}</div>
                </div>
                <div className="bg-white rounded-lg shadow-sm p-4">
                    <div className="text-sm text-gray-500">Data Status</div>
                    <div className="text-2xl font-bold text-green-600">
                        {data?.from_cache ? 'Cached' : 'Fresh'}
                    </div>
                </div>
            </div>

            {/* FLW Table */}
            <div className="bg-white rounded-lg shadow-sm overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                    FLW Username
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                    Total Visits
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                    Approved
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                    Pending
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                    Rejected
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                    Flagged
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                    First Visit
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                    Last Visit
                                </th>
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {rows.map((row, idx) => (
                                <tr key={idx} className="hover:bg-gray-50">
                                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                                        {row.username}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 font-semibold">
                                        {row.total_visits}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-green-600">
                                        {row.approved_visits}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-yellow-600">
                                        {row.pending_visits}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-red-600">
                                        {row.rejected_visits}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-orange-600">
                                        {row.flagged_visits}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                        {row.first_visit_date || '-'}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                        {row.last_visit_date || '-'}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
"""

WEIGHT_TRACKER_RENDER_CODE = """function PipelineUI({ data, definition, onRefresh }) {
    const rows = data?.rows || [];
    const schema = definition?.schema || {};

    // Group by beneficiary
    const beneficiaries = React.useMemo(() => {
        const grouped = {};
        rows.forEach(row => {
            const id = row.computed?.beneficiary_case_id || row.entity_id;
            if (!id) return;

            if (!grouped[id]) {
                grouped[id] = {
                    id,
                    name: row.computed?.child_name || row.entity_name || 'Unknown',
                    visits: []
                };
            }

            grouped[id].visits.push({
                date: row.computed?.visit_date || row.visit_date,
                weight: row.computed?.weight,
                username: row.username
            });
        });

        // Sort visits by date for each beneficiary
        Object.values(grouped).forEach(b => {
            b.visits.sort((a, b) => (a.date || '').localeCompare(b.date || ''));
            b.firstWeight = b.visits[0]?.weight;
            b.lastWeight = b.visits[b.visits.length - 1]?.weight;
            b.weightChange = b.lastWeight && b.firstWeight ? b.lastWeight - b.firstWeight : null;
        });

        return Object.values(grouped);
    }, [rows]);

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="bg-white rounded-lg shadow-sm p-6">
                <div className="flex justify-between items-start">
                    <div>
                        <h1 className="text-2xl font-bold text-gray-900">
                            {definition?.name || 'Weight Tracker'}
                        </h1>
                        <p className="text-gray-600 mt-1">
                            {definition?.description}
                        </p>
                    </div>
                    <button
                        onClick={onRefresh}
                        className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                    >
                        <i className="fa-solid fa-arrows-rotate mr-2"></i>
                        Refresh
                    </button>
                </div>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-3 gap-4">
                <div className="bg-white rounded-lg shadow-sm p-4">
                    <div className="text-sm text-gray-500">Beneficiaries</div>
                    <div className="text-2xl font-bold text-gray-900">{beneficiaries.length}</div>
                </div>
                <div className="bg-white rounded-lg shadow-sm p-4">
                    <div className="text-sm text-gray-500">Total Weight Measurements</div>
                    <div className="text-2xl font-bold text-gray-900">{rows.length}</div>
                </div>
                <div className="bg-white rounded-lg shadow-sm p-4">
                    <div className="text-sm text-gray-500">Gaining Weight</div>
                    <div className="text-2xl font-bold text-green-600">
                        {beneficiaries.filter(b => b.weightChange > 0).length}
                    </div>
                </div>
            </div>

            {/* Beneficiary Cards */}
            <div className="space-y-4">
                {beneficiaries.map(b => (
                    <div key={b.id} className="bg-white rounded-lg shadow-sm p-4">
                        <div className="flex justify-between items-start mb-3">
                            <div>
                                <h3 className="font-semibold text-gray-900">{b.name}</h3>
                                <p className="text-sm text-gray-500">{b.visits.length} measurements</p>
                            </div>
                            {b.weightChange !== null && (
                                <div className={b.weightChange >= 0 ? 'text-green-600' : 'text-red-600'}>
                                    <span className="text-lg font-bold">
                                        {b.weightChange >= 0 ? '+' : ''}{b.weightChange}g
                                    </span>
                                    <span className="text-sm ml-1">
                                        {b.weightChange >= 0 ? '↑' : '↓'}
                                    </span>
                                </div>
                            )}
                        </div>

                        {/* Weight progression */}
                        <div className="flex items-center gap-2 text-sm">
                            {b.visits.slice(0, 8).map((v, i) => (
                                <div key={i} className="flex flex-col items-center">
                                    <div className={
                                        v.weight && v.weight >= 2500 ? 'w-8 h-8 rounded-full bg-green-100 flex items-center justify-center text-xs font-medium text-green-800' :
                                        'w-8 h-8 rounded-full bg-yellow-100 flex items-center justify-center text-xs font-medium text-yellow-800'
                                    }>
                                        {v.weight ? Math.round(v.weight / 100) : '-'}
                                    </div>
                                    <span className="text-xs text-gray-400 mt-1">
                                        {v.date ? v.date.split('-').slice(1).join('/') : '?'}
                                    </span>
                                </div>
                            ))}
                            {b.visits.length > 8 && (
                                <span className="text-gray-400">+{b.visits.length - 8} more</span>
                            )}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
"""


# =============================================================================
# Blank Template
# =============================================================================

BLANK_SCHEMA = {
    "grouping_key": "username",
    "terminal_stage": "visit_level",
    "linking_field": "entity_id",
    "fields": [],
}

BLANK_RENDER_CODE = """function PipelineUI({ data, definition, onRefresh }) {
    const rows = data?.rows || [];

    return (
        <div className="p-4">
            <div className="bg-white rounded-lg shadow">
                <div className="px-4 py-5 sm:p-6">
                    <h3 className="text-lg font-medium text-gray-900 mb-4">
                        Pipeline Data
                    </h3>

                    {rows.length === 0 ? (
                        <p className="text-gray-500">
                            No data available. Configure your pipeline schema to extract fields.
                        </p>
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="min-w-full divide-y divide-gray-200">
                                <thead className="bg-gray-50">
                                    <tr>
                                        {Object.keys(rows[0] || {}).map(key => (
                                            <th key={key}
                                                className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                                {key}
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody className="bg-white divide-y divide-gray-200">
                                    {rows.slice(0, 50).map((row, i) => (
                                        <tr key={i}>
                                            {Object.values(row).map((val, j) => (
                                                <td key={j} className="px-4 py-2 text-sm text-gray-900">
                                                    {formatValue(val)}
                                                </td>
                                            ))}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                            {rows.length > 50 && (
                                <p className="text-sm text-gray-500 p-4">
                                    Showing 50 of {rows.length} rows
                                </p>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

function formatValue(val) {
    if (val === null || val === undefined) return '-';
    if (typeof val === 'object') return JSON.stringify(val);
    return String(val);
}
"""


# =============================================================================
# Template Registry
# =============================================================================

TEMPLATES = {
    "visit_list": {
        "name": "Visit Data Explorer",
        "description": "Explore visit-level data with custom field extraction",
        "schema": VISIT_LIST_SCHEMA,
        "render_code": VISIT_LIST_RENDER_CODE,
    },
    "flw_summary": {
        "name": "FLW Performance Summary",
        "description": "Aggregated statistics per frontline worker",
        "schema": FLW_SUMMARY_SCHEMA,
        "render_code": FLW_SUMMARY_RENDER_CODE,
    },
    "weight_tracker": {
        "name": "Weight Tracker",
        "description": "Track weight measurements across visits",
        "schema": WEIGHT_TRACKER_SCHEMA,
        "render_code": WEIGHT_TRACKER_RENDER_CODE,
    },
    "blank": {
        "name": "New Pipeline",
        "description": "Start from scratch with a blank pipeline",
        "schema": BLANK_SCHEMA,
        "render_code": BLANK_RENDER_CODE,
    },
}


class Command(BaseCommand):
    help = "Create example pipeline templates"

    def add_arguments(self, parser):
        parser.add_argument(
            "--template",
            type=str,
            help=f"Template to create: {', '.join(TEMPLATES.keys())}",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="List available templates",
        )
        parser.add_argument(
            "--access-token",
            type=str,
            help="OAuth access token for Connect API",
        )
        parser.add_argument(
            "--opportunity-id",
            type=int,
            help="Opportunity ID to scope the pipeline",
        )

    def handle(self, *args, **options):
        if options["list"]:
            self.stdout.write("\nAvailable pipeline templates:\n")
            for key, template in TEMPLATES.items():
                self.stdout.write(f"  {key}:")
                self.stdout.write(f"    Name: {template['name']}")
                self.stdout.write(f"    Description: {template['description']}")
                self.stdout.write(f"    Type: {template['schema']['terminal_stage']}")
                self.stdout.write("")
            return

        template_key = options.get("template")
        if not template_key:
            self.stderr.write("Error: --template is required. Use --list to see available templates.")
            return

        if template_key not in TEMPLATES:
            self.stderr.write(f"Error: Unknown template '{template_key}'. Use --list to see available templates.")
            return

        access_token = options.get("access_token")
        opportunity_id = options.get("opportunity_id")

        if not access_token:
            self.stderr.write("Error: --access-token is required")
            return

        if not opportunity_id:
            self.stderr.write("Error: --opportunity-id is required")
            return

        template = TEMPLATES[template_key]

        # Create the pipeline
        from commcare_connect.labs.custom_pipelines.data_access import PipelineDataAccess

        try:
            data_access = PipelineDataAccess(
                access_token=access_token,
                opportunity_id=opportunity_id,
            )

            definition = data_access.create_definition(
                name=template["name"],
                description=template["description"],
                schema=template["schema"],
                render_code=template["render_code"],
            )

            data_access.close()

            self.stdout.write(self.style.SUCCESS(f"Created pipeline '{template['name']}' with ID {definition.id}"))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Failed to create pipeline: {e}"))
