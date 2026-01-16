/**
 * Workflow Components
 *
 * This module exports types and components for the workflow system.
 */

// Export all types
export * from './types';

// Export components
export { WorkflowHost } from './WorkflowHost';
export { WorkflowChat } from './WorkflowChat';
export { DynamicWorkflow } from './DynamicWorkflow';
export { PerformanceReviewWorkflow } from './examples/PerformanceReview';

// Export default render code
export { DEFAULT_RENDER_CODE } from './defaultRenderCode';
