/**
 * Default render code template for new workflows.
 *
 * This code is used when creating a new workflow without custom render code.
 * It provides a basic worker table with status management and pipeline data display.
 */

export const DEFAULT_RENDER_CODE = `function WorkflowUI({ definition, instance, workers, pipelines, links, actions, onUpdateState }) {
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

    // Check if we have pipeline data
    const hasPipelines = pipelines && Object.keys(pipelines).length > 0;

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

            {/* Pipeline Data Summary (if available) */}
            {hasPipelines && (
                <div className="bg-blue-50 rounded-lg p-4 border border-blue-200">
                    <h3 className="font-medium text-blue-900 mb-2">Pipeline Data Sources</h3>
                    <div className="flex flex-wrap gap-4">
                        {Object.entries(pipelines).map(([alias, data]) => (
                            <div key={alias} className="bg-white px-3 py-2 rounded shadow-sm">
                                <div className="text-sm font-medium text-gray-700">{alias}</div>
                                <div className="text-xs text-gray-500">
                                    {data.metadata?.row_count || 0} rows
                                    {data.metadata?.from_cache && ' (cached)'}
                                </div>
                            </div>
                        ))}
                    </div>
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
}`;
