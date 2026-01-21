/**
 * TypeScript types for Workflow components.
 *
 * These types define the contract between Django and React for workflow rendering.
 * Workflows can reference Pipelines as data sources - pipeline data is passed
 * via the `pipelines` prop.
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

  /** Data from pipeline sources (keyed by alias) */
  pipelines: Record<string, PipelineResult>;

  /** Helper functions for generating URLs to other Labs features */
  links: LinkHelpers;

  /** Action handlers for programmatic operations (create tasks, OCS, etc.) */
  actions: ActionHandlers;

  /** Callback to update workflow instance state */
  onUpdateState: (newState: Record<string, unknown>) => Promise<void>;
}

// =============================================================================
// Pipeline Data Types
// =============================================================================

/**
 * Result from a pipeline execution.
 * Workflows reference pipelines as data sources and receive this structure.
 */
export interface PipelineResult {
  /** Array of data rows from the pipeline */
  rows: PipelineRow[];

  /** Metadata about the pipeline execution */
  metadata: PipelineMetadata;
}

/**
 * A single row from a pipeline result.
 * Structure varies based on pipeline schema and terminal_stage.
 */
export interface PipelineRow {
  /** Username (always present) */
  username: string;

  /** Visit date (for visit_level stage) */
  visit_date?: string;

  /** Visit status */
  status?: string;

  /** Entity ID (for linked visits) */
  entity_id?: string;

  /** Entity name */
  entity_name?: string;

  /** Computed fields from pipeline schema (visit_level) */
  computed?: Record<string, unknown>;

  /** Total visits (for aggregated stage) */
  total_visits?: number;

  /** Approved visits (for aggregated stage) */
  approved_visits?: number;

  /** Pending visits (for aggregated stage) */
  pending_visits?: number;

  /** Rejected visits (for aggregated stage) */
  rejected_visits?: number;

  /** Flagged visits (for aggregated stage) */
  flagged_visits?: number;

  /** First visit date (for aggregated stage) */
  first_visit_date?: string;

  /** Last visit date (for aggregated stage) */
  last_visit_date?: string;

  /** Custom aggregated fields (for aggregated stage) */
  custom_fields?: Record<string, unknown>;

  /** Additional fields */
  [key: string]: unknown;
}

/**
 * Metadata about a pipeline execution.
 */
export interface PipelineMetadata {
  /** Number of rows returned */
  row_count: number;

  /** Whether the data came from cache */
  from_cache: boolean;

  /** Name of the pipeline */
  pipeline_name: string;

  /** Terminal stage: visit_level or aggregated */
  terminal_stage: 'visit_level' | 'aggregated';

  /** Error message if execution failed */
  error?: string;
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

  /** Configuration options */
  config?: WorkflowConfig;

  /** Pipeline data sources */
  pipeline_sources?: PipelineSource[];

  /** Whether this workflow is shared with others */
  is_shared?: boolean;

  /** Sharing scope: program, organization, or global */
  shared_scope?: 'program' | 'organization' | 'global';

  /** Additional fields defined by the workflow creator */
  [key: string]: unknown;
}

/**
 * Configuration options for a workflow.
 */
export interface WorkflowConfig {
  /** Show summary cards at top */
  showSummaryCards?: boolean;

  /** Show filter controls */
  showFilters?: boolean;

  /** Additional config options */
  [key: string]: unknown;
}

/**
 * Reference to a pipeline as a data source.
 */
export interface PipelineSource {
  /** ID of the pipeline to fetch data from */
  pipeline_id: number;

  /** Alias used to access the data in render code */
  alias: string;
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
   */
  auditUrl(params: AuditUrlParams): string;

  /**
   * Generate URL to create a task.
   */
  taskUrl(params: TaskUrlParams): string;
}

/**
 * Parameters for audit URL generation.
 */
export interface AuditUrlParams {
  username?: string;
  usernames?: string;
  count?: number;
  audit_type?: string;
  granularity?: string;
  start_date?: string;
  end_date?: string;
  title?: string;
  tag?: string;
  auto_create?: boolean;
  [key: string]: unknown;
}

/**
 * Parameters for task URL generation.
 */
export interface TaskUrlParams {
  username?: string;
  title?: string;
  description?: string;
  audit_session_id?: number;
  workflow_instance_id?: number;
  priority?: string;
  [key: string]: unknown;
}

// =============================================================================
// Action Handlers - For programmatic operations
// =============================================================================

/**
 * Action handlers available to workflow components.
 */
export interface ActionHandlers {
  createTask(params: CreateTaskParams): Promise<TaskResult>;
  checkOCSStatus(): Promise<OCSStatusResult>;
  listOCSBots(): Promise<OCSBotsResult>;
  initiateOCSSession(
    taskId: number,
    params: OCSSessionParams,
  ): Promise<OCSInitiateResult>;
  createTaskWithOCS(
    params: CreateTaskWithOCSParams,
  ): Promise<TaskWithOCSResult>;
}

export interface CreateTaskParams {
  username: string;
  title: string;
  description?: string;
  priority?: 'low' | 'medium' | 'high';
}

export interface TaskResult {
  success: boolean;
  task_id?: number;
  error?: string;
}

export interface OCSStatusResult {
  connected: boolean;
  login_url?: string;
  error?: string;
}

export interface OCSBotsResult {
  success: boolean;
  bots?: OCSBot[];
  needs_oauth?: boolean;
  error?: string;
}

export interface OCSBot {
  id: string;
  name: string;
  version?: number;
}

export interface OCSSessionParams {
  identifier: string;
  experiment: string;
  prompt_text: string;
  platform?: string;
  start_new_session?: boolean;
}

export interface OCSInitiateResult {
  success: boolean;
  message?: string;
  error?: string;
}

export interface CreateTaskWithOCSParams extends CreateTaskParams {
  ocs?: Omit<OCSSessionParams, 'identifier'>;
}

export interface TaskWithOCSResult extends TaskResult {
  ocs?: OCSInitiateResult;
}

// =============================================================================
// API Response Types
// =============================================================================

export interface UpdateStateResponse {
  success: boolean;
  instance?: {
    id: number;
    state: WorkflowState;
  };
  error?: string;
}

export interface GetWorkersResponse {
  workers: WorkerData[];
  error?: string;
}

// =============================================================================
// Utility Types
// =============================================================================

export type WorkflowComponent = React.FC<WorkflowProps>;

/**
 * Data passed from Django template to React.
 */
export interface WorkflowDataFromDjango {
  definition: WorkflowDefinition;
  definition_id: number;
  opportunity_id?: number;
  instance: {
    id: number;
    definition_id: number;
    opportunity_id: number;
    status: string;
    state: WorkflowState;
  };
  workers: WorkerData[];
  pipeline_data?: Record<string, PipelineResult>;
  links: {
    auditUrlBase: string;
    taskUrlBase: string;
  };
  apiEndpoints: {
    updateState: string;
    getWorkers: string;
    getPipelineData?: string;
  };
  render_code?: string;
  is_edit_mode?: boolean;
}
