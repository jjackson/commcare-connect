'use client';

/**
 * WorkflowHost - Container component that loads and renders workflow components.
 *
 * This component:
 * 1. Reads workflow data from the DOM (passed from Django)
 * 2. Sets up link helpers and state management
 * 3. Renders the workflow component
 *
 * In Phase 2, this will dynamically load workflow components from LabsRecord.
 * For now, it provides a placeholder/example implementation.
 */

import React, { useState, useCallback, useEffect } from 'react';
import type {
  WorkflowProps,
  WorkflowDataFromDjango,
  WorkflowState,
  LinkHelpers,
  AuditUrlParams,
  TaskUrlParams,
} from './types';

interface WorkflowHostProps {
  /** DOM element ID containing workflow data */
  containerId?: string;

  /** Optional: Direct workflow data (alternative to reading from DOM) */
  workflowData?: WorkflowDataFromDjango;

  /** Optional: Custom workflow component to render */
  WorkflowComponent?: React.FC<WorkflowProps>;
}

/**
 * Create link helpers from base URLs.
 */
function createLinkHelpers(baseUrls: {
  auditUrlBase: string;
  taskUrlBase: string;
}): LinkHelpers {
  return {
    auditUrl: (params: AuditUrlParams): string => {
      const urlParams = new URLSearchParams();

      if (params.username) urlParams.set('usernames', params.username);
      if (params.usernames) urlParams.set('usernames', params.usernames);
      if (params.count) urlParams.set('count', String(params.count));
      if (params.audit_type) urlParams.set('audit_type', params.audit_type);
      if (params.granularity) urlParams.set('granularity', params.granularity);
      if (params.start_date) urlParams.set('start_date', params.start_date);
      if (params.end_date) urlParams.set('end_date', params.end_date);
      if (params.title) urlParams.set('title', params.title);
      if (params.tag) urlParams.set('tag', params.tag);
      if (params.auto_create) urlParams.set('auto_create', 'true');

      // Default audit type if not specified
      if (!params.audit_type) urlParams.set('audit_type', 'last_n_per_flw');
      if (!params.granularity) urlParams.set('granularity', 'per_flw');

      return `${baseUrls.auditUrlBase}?${urlParams.toString()}`;
    },

    taskUrl: (params: TaskUrlParams): string => {
      const urlParams = new URLSearchParams();

      if (params.username) urlParams.set('username', params.username);
      if (params.title) urlParams.set('title', params.title);
      if (params.description) urlParams.set('description', params.description);
      if (params.audit_session_id)
        urlParams.set('audit_session_id', String(params.audit_session_id));
      if (params.workflow_instance_id)
        urlParams.set(
          'workflow_instance_id',
          String(params.workflow_instance_id),
        );
      if (params.priority) urlParams.set('priority', params.priority);

      return `${baseUrls.taskUrlBase}?${urlParams.toString()}`;
    },
  };
}

/**
 * Default placeholder workflow component.
 * Shows workflow data in a basic format until a real component is loaded.
 */
function DefaultWorkflowComponent({
  definition,
  instance,
  workers,
  links,
}: WorkflowProps) {
  return (
    <div className="space-y-6">
      <div className="bg-yellow-50 border-l-4 border-yellow-400 p-4">
        <div className="flex">
          <div className="flex-shrink-0">
            <i className="fa-solid fa-info-circle text-yellow-400"></i>
          </div>
          <div className="ml-3">
            <p className="text-sm text-yellow-700">
              No custom workflow component loaded. Showing default view.
            </p>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow-sm p-6">
        <h2 className="text-xl font-bold mb-4">{definition.name}</h2>
        <p className="text-gray-600 mb-4">{definition.description}</p>
        <p className="text-sm text-gray-500">
          {workers.length} workers | Instance ID: {instance.id}
        </p>
      </div>
    </div>
  );
}

/**
 * WorkflowHost component.
 */
export function WorkflowHost({
  containerId = 'workflow-root',
  workflowData: propWorkflowData,
  WorkflowComponent = DefaultWorkflowComponent,
}: WorkflowHostProps) {
  const [workflowData, setWorkflowData] =
    useState<WorkflowDataFromDjango | null>(propWorkflowData || null);
  const [instanceState, setInstanceState] = useState<WorkflowState>({});
  const [loading, setLoading] = useState(!propWorkflowData);
  const [error, setError] = useState<string | null>(null);
  const [csrfToken, setCsrfToken] = useState<string>('');

  // Load data from DOM on mount
  useEffect(() => {
    if (propWorkflowData) {
      setInstanceState(propWorkflowData.instance.state);
      return;
    }

    try {
      const container = document.getElementById(containerId);
      if (!container) {
        setError(`Container element #${containerId} not found`);
        setLoading(false);
        return;
      }

      const dataAttr = container.dataset.workflow;
      if (!dataAttr) {
        setError('No workflow data found in container');
        setLoading(false);
        return;
      }

      const data = JSON.parse(dataAttr) as WorkflowDataFromDjango;
      setWorkflowData(data);
      setInstanceState(data.instance.state);

      // Get CSRF token
      const tokenAttr = container.dataset.csrfToken;
      if (tokenAttr) {
        setCsrfToken(tokenAttr);
      }

      setLoading(false);
    } catch (e) {
      setError(`Failed to parse workflow data: ${e}`);
      setLoading(false);
    }
  }, [containerId, propWorkflowData]);

  // State update handler
  const handleUpdateState = useCallback(
    async (newState: Record<string, unknown>) => {
      if (!workflowData) return;

      try {
        const response = await fetch(workflowData.apiEndpoints.updateState, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken,
          },
          body: JSON.stringify({ state: newState }),
        });

        if (!response.ok) {
          throw new Error('Failed to update state');
        }

        const result = await response.json();

        if (result.success && result.instance) {
          setInstanceState(result.instance.state);
        }
      } catch (e) {
        console.error('Failed to update workflow state:', e);
        throw e;
      }
    },
    [workflowData, csrfToken],
  );

  // Loading state
  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <i className="fa-solid fa-spinner fa-spin text-3xl text-blue-600 mb-4"></i>
          <p className="text-gray-600">Loading workflow...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error || !workflowData) {
    return (
      <div className="bg-red-50 border-l-4 border-red-400 p-4">
        <div className="flex">
          <div className="flex-shrink-0">
            <i className="fa-solid fa-circle-exclamation text-red-400"></i>
          </div>
          <div className="ml-3">
            <p className="text-sm text-red-700">
              {error || 'No workflow data available'}
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Create props for workflow component
  const workflowProps: WorkflowProps = {
    definition: workflowData.definition,
    instance: {
      ...workflowData.instance,
      state: instanceState,
    },
    workers: workflowData.workers,
    links: createLinkHelpers(workflowData.links),
    onUpdateState: handleUpdateState,
  };

  return <WorkflowComponent {...workflowProps} />;
}

export default WorkflowHost;
