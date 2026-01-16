/**
 * Workflow Runner - Webpack entry point for rendering workflows.
 *
 * This script:
 * 1. Loads workflow data from the DOM
 * 2. Renders workflow using DynamicWorkflow (AI-generated code)
 * 3. Handles state updates via API
 * 4. Includes AI chat panel for editing workflows
 * 5. Provides controls for saving/discarding changes and editing code
 */

import React, { useState, useCallback, useMemo } from 'react';
import { createRoot } from 'react-dom/client';
import { DynamicWorkflow } from '@/components/workflow/DynamicWorkflow';
import { WorkflowChat } from '@/components/workflow/WorkflowChat';
import { DEFAULT_RENDER_CODE } from '@/components/workflow/defaultRenderCode';
import type {
  WorkflowProps,
  WorkflowDataFromDjango,
  LinkHelpers,
  AuditUrlParams,
  TaskUrlParams,
  ActionHandlers,
  CreateTaskParams,
  TaskResult,
  OCSStatusResult,
  OCSBotsResult,
  OCSSessionParams,
  OCSInitiateResult,
  CreateTaskWithOCSParams,
  TaskWithOCSResult,
} from '@/components/workflow/types';
import { MessageCircle, Code, Save, RotateCcw, X, Check } from 'lucide-react';

/**
 * Create action handlers for workflow operations.
 */
function createActionHandlers(csrfToken: string): ActionHandlers {
  return {
    /**
     * Create a task for a worker.
     */
    createTask: async (params: CreateTaskParams): Promise<TaskResult> => {
      try {
        const response = await fetch('/tasks/api/single-create/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken,
          },
          body: JSON.stringify({
            username: params.username,
            title: params.title,
            description: params.description || '',
            priority: params.priority || 'medium',
          }),
        });

        const data = await response.json();
        return {
          success: data.success,
          task_id: data.task_id,
          error: data.error,
        };
      } catch (e) {
        return {
          success: false,
          error: e instanceof Error ? e.message : 'Failed to create task',
        };
      }
    },

    /**
     * Check if OCS OAuth is configured and valid.
     */
    checkOCSStatus: async (): Promise<OCSStatusResult> => {
      try {
        const response = await fetch('/labs/workflow/api/ocs/status/');
        return await response.json();
      } catch (e) {
        return {
          connected: false,
          error: e instanceof Error ? e.message : 'Failed to check OCS status',
        };
      }
    },

    /**
     * List available OCS bots.
     */
    listOCSBots: async (): Promise<OCSBotsResult> => {
      try {
        const response = await fetch('/labs/workflow/api/ocs/bots/');

        // Handle 401 (not connected to OCS)
        if (response.status === 401) {
          const data = await response.json();
          return {
            success: false,
            needs_oauth: true,
            error: data.error || 'OCS authentication required',
          };
        }

        return await response.json();
      } catch (e) {
        return {
          success: false,
          error: e instanceof Error ? e.message : 'Failed to list OCS bots',
        };
      }
    },

    /**
     * Initiate an OCS session on an existing task.
     */
    initiateOCSSession: async (
      taskId: number,
      params: OCSSessionParams,
    ): Promise<OCSInitiateResult> => {
      try {
        const response = await fetch(`/tasks/${taskId}/ai/initiate/`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken,
          },
          body: JSON.stringify({
            identifier: params.identifier,
            experiment: params.experiment,
            prompt_text: params.prompt_text,
            platform: params.platform || 'commcare_connect',
            start_new_session: params.start_new_session ?? true,
          }),
        });

        const data = await response.json();
        return {
          success: data.success,
          message: data.message,
          error: data.error,
        };
      } catch (e) {
        return {
          success: false,
          error:
            e instanceof Error ? e.message : 'Failed to initiate OCS session',
        };
      }
    },

    /**
     * Create a task and optionally initiate an OCS session on it.
     */
    createTaskWithOCS: async (
      params: CreateTaskWithOCSParams,
    ): Promise<TaskWithOCSResult> => {
      // Step 1: Create task
      const taskResult = await createActionHandlers(csrfToken).createTask(
        params,
      );
      if (!taskResult.success || !taskResult.task_id) {
        return taskResult;
      }

      // Step 2: Initiate OCS if configured
      if (params.ocs && taskResult.task_id) {
        const ocsResult = await createActionHandlers(
          csrfToken,
        ).initiateOCSSession(taskResult.task_id, {
          identifier: params.username,
          ...params.ocs,
        });
        return { ...taskResult, ocs: ocsResult };
      }

      return taskResult;
    },
  };
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

// Extended data type that includes render_code, opportunity_id, and edit mode flag
interface ExtendedWorkflowData extends WorkflowDataFromDjango {
  render_code?: string;
  opportunity_id?: number;
  is_edit_mode?: boolean;
}

/**
 * Main workflow runner component with state management and AI chat.
 */
function WorkflowRunner({
  workflowData: initialData,
  csrfToken,
}: {
  workflowData: ExtendedWorkflowData;
  csrfToken: string;
}) {
  // Original values (for detecting changes)
  const originalRenderCode = initialData.render_code || DEFAULT_RENDER_CODE;
  const originalDefinition = initialData.definition;

  // State for workflow definition and render code (can be updated by AI or manual edit)
  const [definition, setDefinition] = useState(initialData.definition);
  const [renderCode, setRenderCode] = useState(originalRenderCode);
  const [instanceState, setInstanceState] = useState(
    initialData.instance.state,
  );
  const [error, setError] = useState<string | null>(null);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [isCodeEditorOpen, setIsCodeEditorOpen] = useState(false);
  const [editingCode, setEditingCode] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Check if there are unsaved changes
  const hasChanges = useMemo(() => {
    const codeChanged = renderCode !== originalRenderCode;
    const defChanged =
      JSON.stringify(definition) !== JSON.stringify(originalDefinition);
    return codeChanged || defChanged;
  }, [renderCode, definition, originalRenderCode, originalDefinition]);

  // Check if we're in edit mode (temporary run, no persistence)
  const isEditMode = initialData.is_edit_mode === true;

  // Handle state updates
  const handleUpdateState = useCallback(
    async (newState: Record<string, unknown>) => {
      // In edit mode, only update local state (no API call)
      if (isEditMode || !initialData.apiEndpoints.updateState) {
        setInstanceState((prev) => ({ ...prev, ...newState }));
        return;
      }

      try {
        const response = await fetch(initialData.apiEndpoints.updateState, {
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

        if (result.success && result.run) {
          setInstanceState(result.run.state);
        } else if (result.error) {
          throw new Error(result.error);
        }
      } catch (e) {
        console.error('Failed to update workflow state:', e);
        setError(String(e));
        throw e;
      }
    },
    [initialData.apiEndpoints.updateState, csrfToken, isEditMode],
  );

  // Handle workflow definition update from AI
  const handleWorkflowUpdate = useCallback(
    (newDefinition: Record<string, unknown>) => {
      console.log('Workflow definition updated by AI:', newDefinition);
      setDefinition(newDefinition);
    },
    [],
  );

  // Handle render code update from AI
  const handleRenderCodeUpdate = useCallback((newRenderCode: string) => {
    console.log('Render code updated by AI');
    setRenderCode(newRenderCode);
    setRenderError(null);
  }, []);

  // Handle render errors
  const handleRenderError = useCallback((errorMsg: string) => {
    setRenderError(errorMsg);
  }, []);

  // Save changes to backend
  const handleSave = useCallback(async () => {
    setIsSaving(true);
    setError(null);

    try {
      // Save render code
      const response = await fetch(
        `/labs/workflow/api/${initialData.definition_id}/render-code/`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken,
          },
          body: JSON.stringify({
            component_code: renderCode,
            definition: definition,
          }),
        },
      );

      if (!response.ok) {
        throw new Error('Failed to save changes');
      }

      const result = await response.json();
      if (result.success) {
        setSaveSuccess(true);
        setTimeout(() => setSaveSuccess(false), 2000);
        // Reload the page to get fresh data
        // window.location.reload();
      } else {
        throw new Error(result.error || 'Failed to save');
      }
    } catch (e) {
      console.error('Failed to save changes:', e);
      setError(String(e));
    } finally {
      setIsSaving(false);
    }
  }, [renderCode, definition, initialData.definition_id, csrfToken]);

  // Discard changes
  const handleDiscard = useCallback(() => {
    setRenderCode(originalRenderCode);
    setDefinition(originalDefinition);
    setRenderError(null);
  }, [originalRenderCode, originalDefinition]);

  // Open code editor
  const handleOpenCodeEditor = useCallback(() => {
    setEditingCode(renderCode);
    setIsCodeEditorOpen(true);
  }, [renderCode]);

  // Apply code from editor
  const handleApplyCode = useCallback(() => {
    setRenderCode(editingCode);
    setIsCodeEditorOpen(false);
    setRenderError(null);
  }, [editingCode]);

  // Create action handlers (memoized to avoid recreating on every render)
  const actions = useMemo(() => createActionHandlers(csrfToken), [csrfToken]);

  // Create props for workflow component
  const workflowProps: WorkflowProps = {
    definition: definition,
    instance: {
      ...initialData.instance,
      state: instanceState,
    },
    workers: initialData.workers,
    links: createLinkHelpers(initialData.links),
    actions: actions,
    onUpdateState: handleUpdateState,
  };

  return (
    <div className="flex h-full">
      {/* Main Content */}
      <div
        className={`flex-1 transition-all duration-300 ${
          isChatOpen ? 'mr-96' : ''
        }`}
      >
        {/* Control Bar */}
        <div className="bg-white border-b border-gray-200 px-4 py-2 mb-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            {/* Edit Code Button */}
            <button
              onClick={handleOpenCodeEditor}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-md transition-colors"
              title="Edit render code"
            >
              <Code size={16} />
              Edit Code
            </button>

            {/* Save/Discard buttons - only show when there are changes */}
            {hasChanges && (
              <>
                <div className="h-4 w-px bg-gray-300" />
                <span className="text-sm text-amber-600 font-medium">
                  Unsaved changes
                </span>
                <button
                  onClick={handleSave}
                  disabled={isSaving}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-white bg-green-600 hover:bg-green-700 disabled:bg-green-400 rounded-md transition-colors"
                >
                  {isSaving ? (
                    <i className="fa-solid fa-spinner fa-spin" />
                  ) : saveSuccess ? (
                    <Check size={16} />
                  ) : (
                    <Save size={16} />
                  )}
                  {saveSuccess ? 'Saved!' : 'Save'}
                </button>
                <button
                  onClick={handleDiscard}
                  disabled={isSaving}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 disabled:bg-gray-50 rounded-md transition-colors"
                >
                  <RotateCcw size={16} />
                  Discard
                </button>
              </>
            )}
          </div>

          {/* Right side - status */}
          <div className="text-xs text-gray-500">
            {renderError ? (
              <span className="text-red-600">Render error</span>
            ) : (
              <span className="text-green-600">Ready</span>
            )}
          </div>
        </div>

        {/* Show error if any */}
        {error && (
          <div className="bg-red-50 border-l-4 border-red-400 p-4 mb-4 mx-4">
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
        )}

        {/* Render error */}
        {renderError && (
          <div className="bg-yellow-50 border-l-4 border-yellow-400 p-4 mb-4 mx-4">
            <div className="flex">
              <div className="flex-shrink-0">
                <i className="fa-solid fa-exclamation-triangle text-yellow-400"></i>
              </div>
              <div className="ml-3">
                <p className="text-sm text-yellow-700">
                  Render error: {renderError}
                </p>
                <p className="text-xs text-yellow-600 mt-1">
                  Open the code editor to fix the issue.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Render the workflow */}
        <div className="px-4">
          <DynamicWorkflow
            {...workflowProps}
            renderCode={renderCode}
            onError={handleRenderError}
          />
        </div>
      </div>

      {/* Chat Toggle Button */}
      {!isChatOpen && (
        <button
          onClick={() => setIsChatOpen(true)}
          className="fixed bottom-6 right-6 z-50 flex items-center justify-center w-14 h-14 rounded-full shadow-lg transition-all duration-300 bg-blue-600 hover:bg-blue-700 text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          title="Edit workflow with AI"
        >
          <MessageCircle size={24} />
        </button>
      )}

      {/* Chat Panel */}
      <div
        className={`fixed top-0 right-0 h-full w-96 bg-white shadow-2xl z-40 transform transition-transform duration-300 ease-in-out ${
          isChatOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        {isChatOpen && (
          <WorkflowChat
            definition={definition}
            definitionId={initialData.definition_id}
            opportunityId={initialData.opportunity_id}
            renderCode={renderCode}
            onWorkflowUpdate={handleWorkflowUpdate}
            onRenderCodeUpdate={handleRenderCodeUpdate}
            onClose={() => setIsChatOpen(false)}
          />
        )}
      </div>

      {/* Code Editor Modal */}
      {isCodeEditorOpen && (
        <div className="fixed inset-0 z-50 overflow-hidden">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black bg-opacity-50"
            onClick={() => setIsCodeEditorOpen(false)}
          />

          {/* Modal */}
          <div className="absolute inset-4 md:inset-8 lg:inset-16 bg-white rounded-lg shadow-xl flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">
                Edit Render Code
              </h2>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleApplyCode}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md transition-colors"
                >
                  <Check size={16} />
                  Apply Changes
                </button>
                <button
                  onClick={() => setIsCodeEditorOpen(false)}
                  className="p-1.5 text-gray-500 hover:text-gray-700 rounded-md hover:bg-gray-100"
                >
                  <X size={20} />
                </button>
              </div>
            </div>

            {/* Code Editor */}
            <div className="flex-1 overflow-hidden p-4">
              <textarea
                value={editingCode}
                onChange={(e) => setEditingCode(e.target.value)}
                className="w-full h-full font-mono text-sm p-4 border border-gray-300 rounded-md resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-gray-50"
                spellCheck={false}
                placeholder="Enter your React component code here..."
              />
            </div>

            {/* Footer with hints */}
            <div className="px-4 py-2 border-t border-gray-200 bg-gray-50 text-xs text-gray-500">
              <p>
                The code should define a function named{' '}
                <code className="bg-gray-200 px-1 rounded">WorkflowUI</code>{' '}
                that receives props:{' '}
                <code className="bg-gray-200 px-1 rounded">definition</code>,
                <code className="bg-gray-200 px-1 rounded">instance</code>,
                <code className="bg-gray-200 px-1 rounded">workers</code>,
                <code className="bg-gray-200 px-1 rounded">links</code>,
                <code className="bg-gray-200 px-1 rounded">onUpdateState</code>
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
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
      ) as ExtendedWorkflowData;
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
