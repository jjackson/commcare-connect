"""
Management command to seed example workflow definition and render code.

This creates the "Weekly Performance Review" workflow as a LabsRecord
that can be used to test the workflow system.

Usage:
    python manage.py seed_example_workflow --settings=config.settings.labs
"""

import json
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

# Example workflow definition
EXAMPLE_DEFINITION = {
    "name": "Weekly Performance Review",
    "description": "Review each worker's performance and mark as confirmed, needs audit, or create a task",
    "version": 1,
    "statuses": [
        {"id": "pending", "label": "Pending Review", "color": "gray"},
        {"id": "confirmed", "label": "Confirmed Good", "color": "green"},
        {"id": "needs_audit", "label": "Needs Audit", "color": "yellow"},
        {"id": "task_created", "label": "Task Created", "color": "blue"},
    ],
    "worker_fields": ["notes", "audit_id", "task_id"],
}

# Example render code (React component as a string)
# This would be dynamically loaded and executed in the browser
EXAMPLE_RENDER_CODE = """
// Weekly Performance Review Workflow Component
// This component renders the workflow UI with full React flexibility

import React, { useState, useMemo } from 'react';

export function WorkflowUI({ definition, instance, workers, links, onUpdateState }) {
    const [sortBy, setSortBy] = useState('name');
    const [filterStatus, setFilterStatus] = useState('all');

    // Get statuses from definition
    const statuses = definition.statuses || [];

    // Get worker states from instance
    const workerStates = instance.state?.worker_states || {};

    // Calculate summary stats
    const stats = useMemo(() => {
        const counts = {};
        statuses.forEach(s => counts[s.id] = 0);

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

    // Filter and sort workers
    const displayWorkers = useMemo(() => {
        let filtered = workers;
        if (filterStatus !== 'all') {
            filtered = workers.filter(w =>
                (workerStates[w.username]?.status || 'pending') === filterStatus
            );
        }
        return [...filtered].sort((a, b) => {
            if (sortBy === 'name') return a.name.localeCompare(b.name);
            if (sortBy === 'visits') return b.visit_count - a.visit_count;
            return 0;
        });
    }, [workers, workerStates, filterStatus, sortBy]);

    // Handle status change
    const handleStatusChange = async (username, newStatus) => {
        const newWorkerStates = {
            ...workerStates,
            [username]: { ...workerStates[username], status: newStatus }
        };
        await onUpdateState({ worker_states: newWorkerStates });
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold">{definition.name}</h1>
                    <p className="text-gray-600">{definition.description}</p>
                </div>
                <div className="text-sm text-gray-500">
                    {instance.state?.period_start} - {instance.state?.period_end}
                </div>
            </div>

            {/* Summary Cards */}
            <div className="grid grid-cols-4 gap-4">
                <div className="bg-white p-4 rounded-lg shadow">
                    <div className="text-3xl font-bold">{stats.total}</div>
                    <div className="text-gray-600">Total Workers</div>
                </div>
                <div className="bg-green-50 p-4 rounded-lg shadow">
                    <div className="text-3xl font-bold text-green-700">{stats.reviewed}</div>
                    <div className="text-gray-600">Reviewed</div>
                </div>
                {statuses.map(status => (
                    <div key={status.id} className="bg-white p-4 rounded-lg shadow">
                        <div className="text-2xl font-bold">{stats.counts[status.id] || 0}</div>
                        <div className="text-gray-600">{status.label}</div>
                    </div>
                ))}
            </div>

            {/* Filters */}
            <div className="flex gap-4">
                <select
                    value={filterStatus}
                    onChange={e => setFilterStatus(e.target.value)}
                    className="border rounded px-3 py-2"
                >
                    <option value="all">All Statuses</option>
                    {statuses.map(s => (
                        <option key={s.id} value={s.id}>{s.label}</option>
                    ))}
                </select>
                <select
                    value={sortBy}
                    onChange={e => setSortBy(e.target.value)}
                    className="border rounded px-3 py-2"
                >
                    <option value="name">Sort by Name</option>
                    <option value="visits">Sort by Visits</option>
                </select>
            </div>

            {/* Worker Table */}
            <div className="bg-white rounded-lg shadow overflow-hidden">
                <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                        <tr>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                Worker
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                Visits
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                Last Active
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                Status
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                                Actions
                            </th>
                        </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                        {displayWorkers.map(worker => {
                            const state = workerStates[worker.username] || {};
                            const currentStatus = state.status || 'pending';

                            return (
                                <tr key={worker.username} className="hover:bg-gray-50">
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <div className="font-medium">{worker.name}</div>
                                        <div className="text-sm text-gray-500">{worker.username}</div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        {worker.visit_count}
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
                                                Create Task
                                            </a>
                                        </div>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
"""


class Command(BaseCommand):
    help = "Seed example workflow definition and render code to LabsRecord"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without actually creating it",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        self.stdout.write("Seeding example workflow...\n")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no changes will be made\n"))

        # Show what will be created
        self.stdout.write("\nWorkflow Definition:")
        self.stdout.write(f"  Name: {EXAMPLE_DEFINITION['name']}")
        self.stdout.write(f"  Description: {EXAMPLE_DEFINITION['description']}")
        self.stdout.write(f"  Statuses: {[s['id'] for s in EXAMPLE_DEFINITION['statuses']]}")

        self.stdout.write("\nRender Code:")
        self.stdout.write("  Type: React Component")
        self.stdout.write(f"  Lines: {len(EXAMPLE_RENDER_CODE.splitlines())}")

        if dry_run:
            self.stdout.write(self.style.SUCCESS("\nDry run complete. Use without --dry-run to create."))
            return

        # Note: This command is meant to be run in a labs environment with OAuth
        # For now, we'll just print instructions
        self.stdout.write(
            self.style.WARNING(
                "\nNote: This command requires OAuth authentication to create LabsRecords.\n"
                "To seed the workflow:\n"
                "1. Log into the labs environment\n"
                "2. Use the workflow data access layer with a valid OAuth token\n"
                "3. Or create the records manually via the API\n"
            )
        )

        # Print the JSON for manual creation
        self.stdout.write("\nDefinition JSON for manual creation:")
        self.stdout.write(json.dumps(EXAMPLE_DEFINITION, indent=2))

        self.stdout.write(self.style.SUCCESS("\nExample workflow definition ready."))
