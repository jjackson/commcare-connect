/**
 * TypeScript types for Workflow components.
 *
 * These types define the contract between Django and React for workflow rendering.
 * The workflow render code receives WorkflowProps and can render any React UI.
 */

// =============================================================================
// Core Props - What every workflow component receives
// =============================================================================

/**
 * Props passed to every workflow component.
 * This is the main contract between the system and workflow render code.
 */
export interface WorkflowProps {
  /** The workflow definition (structure defined by workflow creator) */
  definition: WorkflowDefinition;

  /** The current workflow instance with state */
  instance: WorkflowInstance;

  /** Workers in this opportunity */
  workers: WorkerData[];

  /** Helper functions for generating URLs to other Labs features */
  links: LinkHelpers;

  /** Callback to update workflow instance state */
  onUpdateState: (newState: Record<string, unknown>) => Promise<void>;
}

// =============================================================================
// Workflow Definition - Schema defined by creator (flexible)
// =============================================================================

/**
 * Workflow definition stored in LabsRecord.
 * The structure is flexible - creators define what fields they need.
 */
export interface WorkflowDefinition {
  /** Unique identifier */
  id?: number;

  /** Display name */
  name: string;

  /** Description of what this workflow does */
  description: string;

  /** Version number for tracking changes */
  version?: number;

  /** Status options for workers (optional, workflow-defined) */
  statuses?: StatusConfig[];

  /** Additional fields defined by the workflow creator */
  [key: string]: unknown;
}

/**
 * Status configuration for worker states.
 */
export interface StatusConfig {
  /** Unique identifier for the status */
  id: string;

  /** Display label */
  label: string;

  /** Color for UI rendering (gray, green, yellow, blue, red, etc.) */
  color: string;
}

// =============================================================================
// Workflow Instance - Running workflow with state
// =============================================================================

/**
 * Workflow instance stored in LabsRecord.
 * Represents a specific execution of a workflow for an opportunity.
 */
export interface WorkflowInstance {
  /** Unique identifier */
  id: number;

  /** Reference to the workflow definition */
  definition_id: number;

  /** Opportunity this instance is for */
  opportunity_id: number;

  /** Current status: in_progress or completed */
  status: 'in_progress' | 'completed';

  /** Flexible state object - structure defined by the workflow */
  state: WorkflowState;
}

/**
 * Flexible state object for workflow instance.
 * Structure is defined by the workflow creator.
 */
export interface WorkflowState {
  /** Period start date (ISO format) */
  period_start?: string;

  /** Period end date (ISO format) */
  period_end?: string;

  /** Per-worker state (keyed by username) */
  worker_states?: Record<string, WorkerState>;

  /** Additional state fields defined by the workflow */
  [key: string]: unknown;
}

/**
 * State for a single worker within a workflow.
 * Structure is flexible based on workflow needs.
 */
export interface WorkerState {
  /** Current status (from definition.statuses) */
  status?: string;

  /** Notes about this worker */
  notes?: string;

  /** Reference to audit created from this workflow */
  audit_id?: number;

  /** Reference to task created from this workflow */
  task_id?: number;

  /** Additional fields defined by the workflow */
  [key: string]: unknown;
}

// =============================================================================
// Worker Data - From Connect API
// =============================================================================

/**
 * Worker data fetched from Connect API.
 */
export interface WorkerData {
  /** Unique username (primary identifier) */
  username: string;

  /** Display name */
  name: string;

  /** Total visit count */
  visit_count: number;

  /** Last active date (ISO format) or null */
  last_active: string | null;

  /** Phone number (if available) */
  phone_number?: string;

  /** Email (if available) */
  email?: string;

  /** Approved visits count */
  approved_visits?: number;

  /** Flagged visits count */
  flagged_visits?: number;

  /** Rejected visits count */
  rejected_visits?: number;

  /** Additional fields from API */
  [key: string]: unknown;
}

// =============================================================================
// Link Helpers - Generate URLs to other Labs features
// =============================================================================

/**
 * Helper functions for generating URLs to other Labs features.
 * These allow workflow components to link to audits, tasks, etc.
 */
export interface LinkHelpers {
  /**
   * Generate URL to create an audit.
   *
   * @param params - Audit creation parameters
   * @returns URL string for audit creation page
   */
  auditUrl(params: AuditUrlParams): string;

  /**
   * Generate URL to create a task.
   *
   * @param params - Task creation parameters
   * @returns URL string for task creation page
   */
  taskUrl(params: TaskUrlParams): string;
}

/**
 * Parameters for audit URL generation.
 */
export interface AuditUrlParams {
  /** FLW username to audit */
  username?: string;

  /** Multiple FLW usernames (comma-separated) */
  usernames?: string;

  /** Number of visits for last_n types */
  count?: number;

  /** Audit type: date_range, last_n_per_flw, last_n_per_opp, last_n_across_all */
  audit_type?: string;

  /** Granularity: combined, per_opp, per_flw */
  granularity?: string;

  /** Start date for date_range (YYYY-MM-DD) */
  start_date?: string;

  /** End date for date_range (YYYY-MM-DD) */
  end_date?: string;

  /** Audit title */
  title?: string;

  /** Audit tag */
  tag?: string;

  /** Auto-submit the form */
  auto_create?: boolean;

  /** Additional parameters */
  [key: string]: unknown;
}

/**
 * Parameters for task URL generation.
 */
export interface TaskUrlParams {
  /** FLW username */
  username?: string;

  /** Task title */
  title?: string;

  /** Task description */
  description?: string;

  /** Link to audit that triggered this task */
  audit_session_id?: number;

  /** Link to workflow instance that triggered this task */
  workflow_instance_id?: number;

  /** Task priority: low, medium, high */
  priority?: string;

  /** Additional parameters */
  [key: string]: unknown;
}

// =============================================================================
// API Response Types
// =============================================================================

/**
 * Response from update state API.
 */
export interface UpdateStateResponse {
  success: boolean;
  instance?: {
    id: number;
    state: WorkflowState;
  };
  error?: string;
}

/**
 * Response from get workers API.
 */
export interface GetWorkersResponse {
  workers: WorkerData[];
  error?: string;
}

// =============================================================================
// Utility Types
// =============================================================================

/**
 * Type for workflow component function.
 */
export type WorkflowComponent = React.FC<WorkflowProps>;

/**
 * Data passed from Django template to React.
 */
export interface WorkflowDataFromDjango {
  definition: WorkflowDefinition;
  definition_id: number;
  instance: {
    id: number;
    definition_id: number;
    opportunity_id: number;
    status: string;
    state: WorkflowState;
  };
  workers: WorkerData[];
  links: {
    auditUrlBase: string;
    taskUrlBase: string;
  };
  apiEndpoints: {
    updateState: string;
    getWorkers: string;
  };
}
