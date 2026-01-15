'use client';

/**
 * Weekly Performance Review Workflow Component
 *
 * This is an example workflow component that demonstrates full React flexibility.
 * It shows a list of workers that can be reviewed and marked with different statuses.
 *
 * Features:
 * - Summary statistics cards
 * - Filterable and sortable worker table
 * - Status dropdown per worker
 * - Links to create audits or tasks
 */

import React, { useState, useMemo, useCallback } from 'react';
import type { WorkflowProps, StatusConfig, WorkerState } from '../types';

/**
 * Performance Review Workflow Component
 */
export function PerformanceReviewWorkflow({
  definition,
  instance,
  workers,
  links,
  onUpdateState,
}: WorkflowProps) {
  const [sortBy, setSortBy] = useState<'name' | 'visits' | 'status'>('name');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [updating, setUpdating] = useState<string | null>(null);

  // Get statuses from definition (with fallback)
  const statuses: StatusConfig[] = useMemo(() => {
    return (
      (definition.statuses as StatusConfig[]) || [
        { id: 'pending', label: 'Pending Review', color: 'gray' },
        { id: 'confirmed', label: 'Confirmed Good', color: 'green' },
        { id: 'needs_audit', label: 'Needs Audit', color: 'yellow' },
        { id: 'task_created', label: 'Task Created', color: 'blue' },
      ]
    );
  }, [definition.statuses]);

  // Get worker states from instance
  const workerStates: Record<string, WorkerState> = useMemo(() => {
    return (instance.state?.worker_states as Record<string, WorkerState>) || {};
  }, [instance.state]);

  // Calculate summary statistics
  const stats = useMemo(() => {
    const counts: Record<string, number> = {};
    statuses.forEach((s) => {
      counts[s.id] = 0;
    });

    workers.forEach((worker) => {
      const status = workerStates[worker.username]?.status || 'pending';
      counts[status] = (counts[status] || 0) + 1;
    });

    const reviewed = workers.length - (counts['pending'] || 0);

    return {
      total: workers.length,
      reviewed,
      pending: counts['pending'] || 0,
      counts,
    };
  }, [workers, workerStates, statuses]);

  // Filter and sort workers
  const displayWorkers = useMemo(() => {
    let filtered = [...workers];

    // Apply status filter
    if (filterStatus !== 'all') {
      filtered = filtered.filter((worker) => {
        const status = workerStates[worker.username]?.status || 'pending';
        return status === filterStatus;
      });
    }

    // Apply sorting
    filtered.sort((a, b) => {
      let comparison = 0;

      switch (sortBy) {
        case 'name':
          comparison = (a.name || a.username).localeCompare(
            b.name || b.username,
          );
          break;
        case 'visits':
          comparison = (a.visit_count || 0) - (b.visit_count || 0);
          break;
        case 'status':
          const statusA = workerStates[a.username]?.status || 'pending';
          const statusB = workerStates[b.username]?.status || 'pending';
          comparison = statusA.localeCompare(statusB);
          break;
      }

      return sortOrder === 'asc' ? comparison : -comparison;
    });

    return filtered;
  }, [workers, workerStates, filterStatus, sortBy, sortOrder]);

  // Handle status change for a worker
  const handleStatusChange = useCallback(
    async (username: string, newStatus: string) => {
      setUpdating(username);

      try {
        const newWorkerStates = {
          ...workerStates,
          [username]: {
            ...workerStates[username],
            status: newStatus,
            updated_at: new Date().toISOString(),
          },
        };

        await onUpdateState({ worker_states: newWorkerStates });
      } catch (error) {
        console.error('Failed to update status:', error);
        // Could show an error toast here
      } finally {
        setUpdating(null);
      }
    },
    [workerStates, onUpdateState],
  );

  // Toggle sort order
  const handleSort = (column: 'name' | 'visits' | 'status') => {
    if (sortBy === column) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(column);
      setSortOrder('asc');
    }
  };

  // Get status color class
  const getStatusColorClass = (statusId: string): string => {
    const status = statuses.find((s) => s.id === statusId);
    const color = status?.color || 'gray';

    const colorMap: Record<string, string> = {
      gray: 'bg-gray-100 text-gray-800',
      green: 'bg-green-100 text-green-800',
      yellow: 'bg-yellow-100 text-yellow-800',
      blue: 'bg-blue-100 text-blue-800',
      red: 'bg-red-100 text-red-800',
    };

    return colorMap[color] || colorMap.gray;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white rounded-lg shadow-sm p-6">
        <div className="flex justify-between items-start">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {definition.name}
            </h1>
            <p className="text-gray-600 mt-1">{definition.description}</p>
          </div>
          <div className="text-right text-sm text-gray-500">
            <div className="font-medium">Period</div>
            <div>
              {instance.state?.period_start || 'Start'} -{' '}
              {instance.state?.period_end || 'End'}
            </div>
          </div>
        </div>
      </div>

      {/* Summary Statistics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white p-4 rounded-lg shadow-sm">
          <div className="text-3xl font-bold text-gray-900">{stats.total}</div>
          <div className="text-gray-600">Total Workers</div>
        </div>
        <div className="bg-green-50 p-4 rounded-lg shadow-sm border border-green-200">
          <div className="text-3xl font-bold text-green-700">
            {stats.reviewed}
          </div>
          <div className="text-gray-600">Reviewed</div>
        </div>
        <div className="bg-gray-50 p-4 rounded-lg shadow-sm border border-gray-200">
          <div className="text-3xl font-bold text-gray-700">
            {stats.pending}
          </div>
          <div className="text-gray-600">Pending</div>
        </div>
        <div className="bg-blue-50 p-4 rounded-lg shadow-sm border border-blue-200">
          <div className="text-3xl font-bold text-blue-700">
            {Math.round((stats.reviewed / Math.max(stats.total, 1)) * 100)}%
          </div>
          <div className="text-gray-600">Progress</div>
        </div>
      </div>

      {/* Status Breakdown */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {statuses.map((status) => (
          <div
            key={status.id}
            className={`p-3 rounded-lg shadow-sm cursor-pointer transition-all ${
              filterStatus === status.id
                ? 'ring-2 ring-offset-2 ring-blue-500'
                : 'hover:shadow-md'
            } ${getStatusColorClass(status.id)}`}
            onClick={() =>
              setFilterStatus(filterStatus === status.id ? 'all' : status.id)
            }
          >
            <div className="text-2xl font-bold">
              {stats.counts[status.id] || 0}
            </div>
            <div className="text-sm">{status.label}</div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="bg-white rounded-lg shadow-sm p-4">
        <div className="flex flex-wrap gap-4 items-center">
          <div>
            <label
              htmlFor="filter-status"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Filter by Status
            </label>
            <select
              id="filter-status"
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="all">All Statuses</option>
              {statuses.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>

          <div className="ml-auto text-sm text-gray-500">
            Showing {displayWorkers.length} of {workers.length} workers
          </div>
        </div>
      </div>

      {/* Worker Table */}
      <div className="bg-white rounded-lg shadow-sm overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th
                className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                onClick={() => handleSort('name')}
              >
                <div className="flex items-center gap-1">
                  Worker
                  {sortBy === 'name' && (
                    <i
                      className={`fa-solid fa-sort-${
                        sortOrder === 'asc' ? 'up' : 'down'
                      }`}
                    ></i>
                  )}
                </div>
              </th>
              <th
                className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                onClick={() => handleSort('visits')}
              >
                <div className="flex items-center gap-1">
                  Visits
                  {sortBy === 'visits' && (
                    <i
                      className={`fa-solid fa-sort-${
                        sortOrder === 'asc' ? 'up' : 'down'
                      }`}
                    ></i>
                  )}
                </div>
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Last Active
              </th>
              <th
                className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                onClick={() => handleSort('status')}
              >
                <div className="flex items-center gap-1">
                  Status
                  {sortBy === 'status' && (
                    <i
                      className={`fa-solid fa-sort-${
                        sortOrder === 'asc' ? 'up' : 'down'
                      }`}
                    ></i>
                  )}
                </div>
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {displayWorkers.map((worker) => {
              const state = workerStates[worker.username] || {};
              const currentStatus = state.status || 'pending';
              const isUpdating = updating === worker.username;

              return (
                <tr key={worker.username} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="font-medium text-gray-900">
                      {worker.name || worker.username}
                    </div>
                    <div className="text-sm text-gray-500">
                      {worker.username}
                    </div>
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
                      onChange={(e) =>
                        handleStatusChange(worker.username, e.target.value)
                      }
                      disabled={isUpdating}
                      className={`border rounded px-2 py-1 text-sm ${
                        isUpdating ? 'opacity-50 cursor-wait' : ''
                      }`}
                    >
                      {statuses.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.label}
                        </option>
                      ))}
                    </select>
                    {isUpdating && (
                      <i className="fa-solid fa-spinner fa-spin ml-2 text-gray-400"></i>
                    )}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    <div className="flex gap-2">
                      <a
                        href={links.auditUrl({
                          username: worker.username,
                          count: 5,
                        })}
                        className="inline-flex items-center px-2 py-1 border border-blue-300 rounded text-xs font-medium text-blue-700 bg-blue-50 hover:bg-blue-100"
                      >
                        <i className="fa-solid fa-clipboard-check mr-1"></i>
                        Audit
                      </a>
                      <a
                        href={links.taskUrl({
                          username: worker.username,
                          title: `Follow up with ${
                            worker.name || worker.username
                          }`,
                          workflow_instance_id: instance.id,
                        })}
                        className="inline-flex items-center px-2 py-1 border border-gray-300 rounded text-xs font-medium text-gray-700 bg-gray-50 hover:bg-gray-100"
                      >
                        <i className="fa-solid fa-tasks mr-1"></i>
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
            <i className="fa-solid fa-users-slash text-4xl mb-4"></i>
            <p>No workers match the current filter.</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default PerformanceReviewWorkflow;
