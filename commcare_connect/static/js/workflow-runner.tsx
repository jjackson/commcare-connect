/**
 * Workflow Runner - Webpack entry point for rendering workflows.
 *
 * This script:
 * 1. Loads workflow data from the DOM
 * 2. Mounts the PerformanceReview component (or other workflow components)
 * 3. Handles state updates via API
 */

import React from 'react';
import { createRoot } from 'react-dom/client';
import { PerformanceReviewWorkflow } from '@/components/workflow/examples/PerformanceReview';
import type {
  WorkflowProps,
  WorkflowDataFromDjango,
  LinkHelpers,
  AuditUrlParams,
  TaskUrlParams,
} from '@/components/workflow/types';

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
      urlParams.set('audit_type', params.audit_type || 'last_n_per_flw');
      urlParams.set('granularity', params.granularity || 'per_flw');
      if (params.start_date) urlParams.set('start_date', params.start_date);
      if (params.end_date) urlParams.set('end_date', params.end_date);
      if (params.title) urlParams.set('title', params.title);
      if (params.tag) urlParams.set('tag', params.tag);
      if (params.auto_create) urlParams.set('auto_create', 'true');

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
 * Main workflow runner component with state management.
 */
function WorkflowRunner({
  workflowData,
  csrfToken,
}: {
  workflowData: WorkflowDataFromDjango;
  csrfToken: string;
}) {
  const [instanceState, setInstanceState] = React.useState(
    workflowData.instance.state,
  );
  const [error, setError] = React.useState<string | null>(null);

  // Handle state updates
  const handleUpdateState = React.useCallback(
    async (newState: Record<string, unknown>) => {
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
        } else if (result.error) {
          throw new Error(result.error);
        }
      } catch (e) {
        console.error('Failed to update workflow state:', e);
        setError(String(e));
        throw e;
      }
    },
    [workflowData.apiEndpoints.updateState, csrfToken],
  );

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

  // Show error if any
  if (error) {
    return (
      <div className="bg-red-50 border-l-4 border-red-400 p-4 mb-4">
        <div className="flex">
          <div className="flex-shrink-0">
            <i className="fa-solid fa-circle-exclamation text-red-400"></i>
          </div>
          <div className="ml-3">
            <p className="text-sm text-red-700">{error}</p>
            <button
              onClick={() => setError(null)}
              className="text-sm text-red-600 underline mt-1"
            >
              Dismiss
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Render the Performance Review workflow
  // In Phase 2, this would dynamically load the component based on workflow type
  return <PerformanceReviewWorkflow {...workflowProps} />;
}

// Wait for DOM to be ready
document.addEventListener('DOMContentLoaded', () => {
  const container = document.getElementById('workflow-root');
  const dataScript = document.getElementById('workflow-data');

  if (container) {
    try {
      // Parse workflow data from json_script tag (Django's safe way to pass JSON)
      if (!dataScript) {
        console.error('No workflow data script found');
        return;
      }

      const workflowData = JSON.parse(
        dataScript.textContent || '{}',
      ) as WorkflowDataFromDjango;
      const csrfToken = container.dataset.csrfToken || '';

      console.log('Workflow data loaded:', workflowData);

      // Create React root and render
      const root = createRoot(container);
      root.render(
        <React.StrictMode>
          <WorkflowRunner workflowData={workflowData} csrfToken={csrfToken} />
        </React.StrictMode>,
      );

      console.log('Workflow mounted successfully');
    } catch (e) {
      console.error('Failed to initialize workflow:', e);
      container.innerHTML = `
        <div class="bg-red-50 border-l-4 border-red-400 p-4">
          <div class="flex">
            <div class="flex-shrink-0">
              <i class="fa-solid fa-circle-exclamation text-red-400"></i>
            </div>
            <div class="ml-3">
              <p class="text-sm text-red-700">Failed to initialize workflow: ${e}</p>
            </div>
          </div>
        </div>
      `;
    }
  }
});
