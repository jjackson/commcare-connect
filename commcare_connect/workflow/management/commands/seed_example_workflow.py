"""
Management command to seed workflow templates.

This creates workflow definitions and render code as LabsRecords
that can be used to test the workflow system.

Usage:
    python manage.py seed_example_workflow --settings=config.settings.labs
    python manage.py seed_example_workflow --template=ocs_outreach --settings=config.settings.labs
    python manage.py seed_example_workflow --list --settings=config.settings.labs
"""

import json
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

# =============================================================================
# Template: Performance Review
# =============================================================================

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
}

PERFORMANCE_REVIEW_RENDER_CODE = """function WorkflowUI({ definition, instance, workers, links, actions, onUpdateState }) {
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
}

OCS_OUTREACH_RENDER_CODE = """function WorkflowUI({ definition, instance, workers, links, actions, onUpdateState }) {
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
    // progress[username] = { status: 'pending'|'creating'|'task_created'|'ocs_initiated'|'error', task_id, error }

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

    // Toggle worker selection
    const toggleWorker = (username) => {
        setSelectedWorkers(prev => ({
            ...prev,
            [username]: !prev[username]
        }));
    };

    // Select/deselect all
    const handleSelectAll = () => {
        const newState = !selectAll;
        setSelectAll(newState);
        const newSelected = {};
        workers.forEach(w => { newSelected[w.username] = newState; });
        setSelectedWorkers(newSelected);
    };

    // Count selected workers
    const selectedCount = Object.values(selectedWorkers).filter(Boolean).length;

    // Run bulk outreach
    const handleCreateTasks = async () => {
        const workersToProcess = workers.filter(w => selectedWorkers[w.username]);
        if (workersToProcess.length === 0) return;

        setIsRunning(true);

        for (const worker of workersToProcess) {
            // Update progress: creating
            setProgress(prev => ({
                ...prev,
                [worker.username]: { status: 'creating' }
            }));

            try {
                // Build task title
                const title = (definition.taskTitleTemplate || 'Outreach: {name}')
                    .replace('{name}', worker.name || worker.username);

                // Create task with OCS if bot selected
                const result = await actions.createTaskWithOCS({
                    username: worker.username,
                    title: title,
                    description: promptText,
                    priority: 'medium',
                    ocs: selectedBot ? {
                        experiment: selectedBot,
                        prompt_text: promptText
                    } : undefined
                });

                if (result.success) {
                    const newStatus = selectedBot && result.ocs?.success ? 'ocs_initiated' : 'task_created';
                    setProgress(prev => ({
                        ...prev,
                        [worker.username]: {
                            status: newStatus,
                            task_id: result.task_id
                        }
                    }));

                    // Update workflow state
                    await onUpdateState({
                        worker_states: {
                            ...instance.state?.worker_states,
                            [worker.username]: {
                                task_id: result.task_id,
                                status: 'outreach_initiated'
                            }
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

    // Get status badge
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

    // Get existing state badge
    const getStateBadge = (username) => {
        const state = workerStates[username];
        if (!state?.task_id) return null;

        return (
            <span className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium bg-gray-100 text-gray-700">
                <i className="fa-solid fa-check"></i>
                Has Task
            </span>
        );
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="bg-white rounded-lg shadow-sm p-6">
                <h1 className="text-2xl font-bold text-gray-900">{definition.name}</h1>
                <p className="text-gray-600 mt-1">{definition.description}</p>
            </div>

            {/* OCS Status Banner */}
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
                            <span>Open Chat Studio not connected. Tasks will be created without AI sessions.</span>
                        </div>
                        <a
                            href={ocsLoginUrl + '?next=' + encodeURIComponent(window.location.pathname)}
                            className="px-4 py-2 bg-yellow-600 text-white rounded-lg hover:bg-yellow-700 text-sm font-medium"
                        >
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

            {/* Configuration */}
            <div className="bg-white rounded-lg shadow-sm p-6 space-y-4">
                <h2 className="text-lg font-semibold text-gray-900">Configuration</h2>

                {/* Bot Selector */}
                {ocsConnected && bots.length > 0 && (
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                            <i className="fa-solid fa-robot mr-2"></i>
                            Select AI Bot
                        </label>
                        <select
                            value={selectedBot}
                            onChange={e => setSelectedBot(e.target.value)}
                            className="w-full border border-gray-300 rounded-lg px-3 py-2"
                            disabled={isRunning}
                        >
                            <option value="">No AI Bot (create tasks only)</option>
                            {bots.map(bot => (
                                <option key={bot.id} value={bot.id}>{bot.name}</option>
                            ))}
                        </select>
                    </div>
                )}

                {/* Prompt */}
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                        <i className="fa-solid fa-message mr-2"></i>
                        {selectedBot ? 'AI Prompt / Task Description' : 'Task Description'}
                    </label>
                    <textarea
                        value={promptText}
                        onChange={e => setPromptText(e.target.value)}
                        rows={4}
                        className="w-full border border-gray-300 rounded-lg px-3 py-2 resize-none"
                        placeholder="Enter instructions for the AI bot or task description..."
                        disabled={isRunning}
                    />
                </div>
            </div>

            {/* Worker Selection */}
            <div className="bg-white rounded-lg shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <h2 className="text-lg font-semibold text-gray-900">Select Workers</h2>
                        <span className="text-sm text-gray-500">
                            {selectedCount} of {workers.length} selected
                        </span>
                    </div>
                    <div className="flex items-center gap-3">
                        <button
                            onClick={handleSelectAll}
                            className="text-sm text-blue-600 hover:text-blue-800"
                            disabled={isRunning}
                        >
                            {selectAll ? 'Deselect All' : 'Select All'}
                        </button>
                        <button
                            onClick={handleCreateTasks}
                            disabled={selectedCount === 0 || isRunning || !promptText.trim()}
                            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-sm font-medium flex items-center gap-2"
                        >
                            {isRunning ? (
                                <>
                                    <i className="fa-solid fa-spinner fa-spin"></i>
                                    Processing...
                                </>
                            ) : (
                                <>
                                    <i className="fa-solid fa-paper-plane"></i>
                                    Create Tasks ({selectedCount})
                                </>
                            )}
                        </button>
                    </div>
                </div>

                <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                        <tr>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase w-12">
                                <input
                                    type="checkbox"
                                    checked={selectAll}
                                    onChange={handleSelectAll}
                                    disabled={isRunning}
                                    className="rounded border-gray-300"
                                />
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Worker</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Visits</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Last Active</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Task</th>
                        </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                        {workers.map(worker => {
                            const isSelected = selectedWorkers[worker.username] || false;
                            const progressItem = progress[worker.username];
                            const existingState = workerStates[worker.username];

                            return (
                                <tr key={worker.username} className={isSelected ? 'bg-blue-50' : 'hover:bg-gray-50'}>
                                    <td className="px-6 py-4">
                                        <input
                                            type="checkbox"
                                            checked={isSelected}
                                            onChange={() => toggleWorker(worker.username)}
                                            disabled={isRunning}
                                            className="rounded border-gray-300"
                                        />
                                    </td>
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
                                        {getProgressBadge(worker.username) || getStateBadge(worker.username) || (
                                            <span className="text-sm text-gray-400">-</span>
                                        )}
                                        {progressItem?.status === 'error' && (
                                            <div className="text-xs text-red-600 mt-1">{progressItem.error}</div>
                                        )}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                                        {(progressItem?.task_id || existingState?.task_id) ? (
                                            <a
                                                href={"/tasks/" + (progressItem?.task_id || existingState?.task_id) + "/edit/"}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="text-blue-600 hover:text-blue-800 flex items-center gap-1"
                                            >
                                                <i className="fa-solid fa-external-link"></i>
                                                View Task
                                            </a>
                                        ) : (
                                            <span className="text-gray-400">-</span>
                                        )}
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>

                {workers.length === 0 && (
                    <div className="px-6 py-12 text-center text-gray-500">
                        No workers available in this opportunity.
                    </div>
                )}
            </div>
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
        "definition": PERFORMANCE_REVIEW_DEFINITION,
        "render_code": PERFORMANCE_REVIEW_RENDER_CODE,
    },
    "ocs_outreach": {
        "name": "OCS Bulk Outreach",
        "description": "Create tasks and initiate AI chatbot conversations for multiple workers",
        "definition": OCS_OUTREACH_DEFINITION,
        "render_code": OCS_OUTREACH_RENDER_CODE,
    },
}


class Command(BaseCommand):
    help = "Seed workflow templates to LabsRecord"

    def add_arguments(self, parser):
        parser.add_argument(
            "--template",
            type=str,
            default="performance_review",
            choices=list(TEMPLATES.keys()),
            help="Which template to create (default: performance_review)",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="List available templates",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without actually creating it",
        )

    def handle(self, *args, **options):
        # List templates
        if options["list"]:
            self.stdout.write("\nAvailable workflow templates:\n")
            for key, template in TEMPLATES.items():
                self.stdout.write(f"  {key}:")
                self.stdout.write(f"    Name: {template['name']}")
                self.stdout.write(f"    Description: {template['description']}\n")
            return

        template_key = options["template"]
        dry_run = options["dry_run"]

        template = TEMPLATES[template_key]

        self.stdout.write(f"Seeding workflow template: {template_key}\n")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no changes will be made\n"))

        # Show what will be created
        self.stdout.write("\nWorkflow Definition:")
        self.stdout.write(f"  Name: {template['definition']['name']}")
        self.stdout.write(f"  Description: {template['definition']['description']}")
        self.stdout.write(f"  Statuses: {[s['id'] for s in template['definition']['statuses']]}")

        self.stdout.write("\nRender Code:")
        self.stdout.write("  Type: React Component")
        self.stdout.write(f"  Lines: {len(template['render_code'].splitlines())}")

        if dry_run:
            self.stdout.write(self.style.SUCCESS("\nDry run complete. Use without --dry-run to create."))
            return

        # Print instructions
        self.stdout.write(
            self.style.WARNING(
                "\nNote: This command requires OAuth authentication to create LabsRecords.\n"
                "To seed the workflow:\n"
                "1. Log into the labs environment\n"
                "2. Use the workflow data access layer with a valid OAuth token\n"
                "3. Or use the 'Create Workflow' button in the UI\n"
            )
        )

        # Print the JSON for manual creation
        self.stdout.write("\nDefinition JSON for manual creation:")
        self.stdout.write(json.dumps(template["definition"], indent=2))

        self.stdout.write(self.style.SUCCESS(f"\n{template['name']} template ready."))
