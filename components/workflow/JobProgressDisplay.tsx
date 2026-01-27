/**
 * JobProgressDisplay Component
 *
 * Displays real-time progress for multi-stage workflow jobs.
 * Shows stage info, progress bar, and provides cancel/delete buttons.
 *
 * Usage in workflow components:
 *   <JobProgressDisplay
 *     progress={jobProgress}
 *     onCancel={handleCancel}
 *     onDelete={handleDelete}
 *   />
 */

import React from 'react';
import type { JobProgressData, ActiveJobState } from './types';

export interface JobProgressDisplayProps {
  /** Current progress data from SSE stream or state */
  progress: JobProgressData | ActiveJobState | null;

  /** Whether a job is currently running (for showing cancel button) */
  isRunning?: boolean;

  /** Callback when user clicks cancel */
  onCancel?: () => void;

  /** Whether cancel is in progress */
  isCancelling?: boolean;

  /** Callback when user clicks delete run */
  onDelete?: () => void;

  /** Whether delete is in progress */
  isDeleting?: boolean;

  /** Show delete button */
  showDeleteButton?: boolean;

  /** Custom class name */
  className?: string;
}

/**
 * Progress bar component for job stages.
 */
const ProgressBar: React.FC<{
  processed: number;
  total: number;
  className?: string;
}> = ({ processed, total, className = '' }) => {
  const percent = total > 0 ? Math.round((processed / total) * 100) : 0;

  return (
    <div className={`w-full bg-gray-200 rounded-full h-2 ${className}`}>
      <div
        className="bg-blue-600 h-2 rounded-full transition-all duration-300"
        style={{ width: `${percent}%` }}
      />
    </div>
  );
};

/**
 * Stage indicator pill.
 */
const StageIndicator: React.FC<{
  currentStage: number;
  totalStages: number;
  stageName: string;
}> = ({ currentStage, totalStages, stageName }) => (
  <div className="flex items-center gap-2 text-sm">
    <span className="px-2 py-0.5 bg-blue-100 text-blue-800 rounded-full text-xs font-medium">
      Stage {currentStage}/{totalStages}
    </span>
    <span className="text-gray-600">{stageName}</span>
  </div>
);

/**
 * Main JobProgressDisplay component.
 */
export const JobProgressDisplay: React.FC<JobProgressDisplayProps> = ({
  progress,
  isRunning = false,
  onCancel,
  isCancelling = false,
  onDelete,
  isDeleting = false,
  showDeleteButton = false,
  className = '',
}) => {
  if (!progress) return null;

  const status = progress.status || 'unknown';
  const currentStage = progress.current_stage || 1;
  const totalStages = progress.total_stages || 1;
  const stageName = progress.stage_name || 'Processing';
  const processed = progress.processed || 0;
  const total = progress.total || 0;
  const message = ('message' in progress ? progress.message : null) || '';

  // Determine if job is active
  const isActive = status === 'running' || status === 'pending';

  // Status-based styling
  const getStatusBadge = () => {
    switch (status) {
      case 'running':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800">
            <svg
              className="animate-spin -ml-0.5 mr-1.5 h-3 w-3"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
                fill="none"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
            Running
          </span>
        );
      case 'completed':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
            <svg
              className="-ml-0.5 mr-1.5 h-3 w-3"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path
                fillRule="evenodd"
                d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                clipRule="evenodd"
              />
            </svg>
            Completed
          </span>
        );
      case 'failed':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">
            <svg
              className="-ml-0.5 mr-1.5 h-3 w-3"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path
                fillRule="evenodd"
                d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                clipRule="evenodd"
              />
            </svg>
            Failed
          </span>
        );
      case 'cancelled':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
            <svg
              className="-ml-0.5 mr-1.5 h-3 w-3"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path
                fillRule="evenodd"
                d="M13.477 14.89A6 6 0 015.11 6.524l8.367 8.368zm1.414-1.414L6.524 5.11a6 6 0 008.367 8.367zM18 10a8 8 0 11-16 0 8 8 0 0116 0z"
                clipRule="evenodd"
              />
            </svg>
            Cancelled
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
            {status}
          </span>
        );
    }
  };

  return (
    <div
      className={`bg-white border border-gray-200 rounded-lg p-4 ${className}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          {getStatusBadge()}
          {totalStages > 1 && isActive && (
            <StageIndicator
              currentStage={currentStage}
              totalStages={totalStages}
              stageName={stageName}
            />
          )}
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2">
          {isActive && onCancel && (
            <button
              onClick={onCancel}
              disabled={isCancelling}
              className="inline-flex items-center px-3 py-1.5 text-sm font-medium text-red-700 bg-red-50 hover:bg-red-100 border border-red-200 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isCancelling ? (
                <>
                  <svg
                    className="animate-spin -ml-0.5 mr-1.5 h-4 w-4"
                    viewBox="0 0 24 24"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                      fill="none"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                    />
                  </svg>
                  Cancelling...
                </>
              ) : (
                <>
                  <svg
                    className="-ml-0.5 mr-1.5 h-4 w-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                  Cancel Job
                </>
              )}
            </button>
          )}

          {showDeleteButton && !isActive && onDelete && (
            <button
              onClick={onDelete}
              disabled={isDeleting}
              className="inline-flex items-center px-3 py-1.5 text-sm font-medium text-red-700 bg-red-50 hover:bg-red-100 border border-red-200 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isDeleting ? (
                <>
                  <svg
                    className="animate-spin -ml-0.5 mr-1.5 h-4 w-4"
                    viewBox="0 0 24 24"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                      fill="none"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                    />
                  </svg>
                  Deleting...
                </>
              ) : (
                <>
                  <svg
                    className="-ml-0.5 mr-1.5 h-4 w-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                    />
                  </svg>
                  Delete Run
                </>
              )}
            </button>
          )}
        </div>
      </div>

      {/* Progress display (only when active) */}
      {isActive && total > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-600">{message || `Processing...`}</span>
            <span className="text-gray-500 font-medium">
              {processed}/{total}
            </span>
          </div>
          <ProgressBar processed={processed} total={total} />
        </div>
      )}

      {/* Error message */}
      {'error' in progress && progress.error && (
        <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-md">
          <p className="text-sm text-red-700">{progress.error}</p>
        </div>
      )}

      {/* Summary (when completed) */}
      {'summary' in progress && progress.summary && status === 'completed' && (
        <div className="mt-3 flex items-center gap-4 text-sm">
          {progress.summary.successful !== undefined && (
            <span className="text-green-600">
              {progress.summary.successful} successful
            </span>
          )}
          {progress.summary.failed !== undefined &&
            progress.summary.failed > 0 && (
              <span className="text-red-600">
                {progress.summary.failed} failed
              </span>
            )}
        </div>
      )}
    </div>
  );
};

export default JobProgressDisplay;
