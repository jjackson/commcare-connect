"""
Data access layer for the Audit of Audits admin report.

Unlike other DataAccess classes, this does NOT subclass BaseDataAccess because
BaseDataAccess auto-populates opportunity_id from request.labs_context, which
would scope results to a single opportunity. This class intentionally creates
an unscoped LabsRecordAPIClient so that all workflow runs across all
opportunities are returned for the admin report.
"""

import logging

from commcare_connect.audit.models import AuditSessionRecord
from commcare_connect.labs.integrations.connect.api_client import LabsAPIError, LabsRecordAPIClient
from commcare_connect.workflow.data_access import WorkflowDefinitionRecord, WorkflowRunRecord

logger = logging.getLogger(__name__)

WORKFLOW_EXPERIMENT = "workflow"
AUDIT_EXPERIMENT = "audit"


class AuditOfAuditsDataAccess:
    """
    Cross-opportunity, unscoped data access for the Audit of Audits admin report.

    Instantiates LabsRecordAPIClient with only an access_token (no opportunity_id,
    organization_id, or program_id), so that get_records() sends no scope filters
    and returns all records visible to the authenticated user.
    """

    def __init__(self, access_token: str):
        # Intentionally unscoped — no opportunity/org/program filtering
        self.labs_api = LabsRecordAPIClient(access_token=access_token)

    def close(self):
        self.labs_api.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def build_report_data(self) -> list[dict]:
        """
        Fetch all workflow definitions, runs, and linked audit sessions, then
        join them in Python and return a list of enriched row dicts sorted by
        created_at descending (most recent run first).

        Makes exactly 3 API calls regardless of the number of runs.

        Returns:
            List of dicts with keys:
                run_id, definition_id, definition_name, template_type,
                opportunity_id, created_at, period_start, period_end,
                status, selected_count, username, session_count,
                completed_session_count, avg_pct_passed
        """
        # --- 1. Fetch all workflow definitions ---
        try:
            definitions: list[WorkflowDefinitionRecord] = self.labs_api.get_records(
                experiment=WORKFLOW_EXPERIMENT,
                type="workflow_definition",
                model_class=WorkflowDefinitionRecord,
            )
        except LabsAPIError:
            logger.exception("[AuditOfAudits] Failed to fetch workflow definitions")
            definitions = []

        def_map: dict[int, WorkflowDefinitionRecord] = {d.id: d for d in definitions}

        # --- 2. Fetch all workflow runs ---
        try:
            runs: list[WorkflowRunRecord] = self.labs_api.get_records(
                experiment=WORKFLOW_EXPERIMENT,
                type="workflow_run",
                model_class=WorkflowRunRecord,
            )
        except LabsAPIError:
            logger.exception("[AuditOfAudits] Failed to fetch workflow runs")
            runs = []

        # --- 3. Fetch all audit sessions once; group by labs_record_id in Python ---
        try:
            all_sessions: list[AuditSessionRecord] = self.labs_api.get_records(
                experiment=AUDIT_EXPERIMENT,
                type="AuditSession",
                model_class=AuditSessionRecord,
            )
        except LabsAPIError:
            logger.exception("[AuditOfAudits] Failed to fetch audit sessions")
            all_sessions = []

        sessions_by_run: dict[int, list[AuditSessionRecord]] = {}
        for session in all_sessions:
            run_id = session.labs_record_id
            if run_id:
                sessions_by_run.setdefault(run_id, []).append(session)

        # --- 4. Join and build rows ---
        rows = []
        for run in runs:
            definition = def_map.get(run.definition_id)
            linked_sessions = sessions_by_run.get(run.id, [])

            # Avg % passed — check pre-computed state value first, fall back to session math
            avg_pct_passed = _extract_avg_pct_passed(run, linked_sessions)

            rows.append(
                {
                    "run_id": run.id,
                    "definition_id": run.definition_id,
                    "definition_name": definition.name if definition else f"Workflow #{run.definition_id}",
                    "template_type": definition.template_type if definition else "",
                    "opportunity_id": run.opportunity_id,
                    "created_at": run.created_at or "",
                    "period_start": run.period_start or "",
                    "period_end": run.period_end or "",
                    "status": run.status or "unknown",
                    "selected_count": run.selected_count or 0,
                    "username": run.username or "",
                    "session_count": len(linked_sessions),
                    "completed_session_count": sum(
                        1 for s in linked_sessions if s.overall_result in ("pass", "fail")
                    ),
                    "avg_pct_passed": avg_pct_passed,
                }
            )

        # Sort by created_at descending (most recent first)
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return rows


def _extract_avg_pct_passed(run: WorkflowRunRecord, sessions: list[AuditSessionRecord]) -> float | None:
    """
    Determine the average % passed for a workflow run.

    Priority:
    1. Pre-computed value stored in run.state (workflow template may store this)
    2. Calculated from linked audit session overall_result fields
    3. None if no completed sessions exist
    """
    state = run.state or {}

    # Check common pre-computed keys in run state
    for key in ("avg_pct_passed", "avg_pass_rate", "pass_rate"):
        val = state.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass

    # Check nested overall_stats dict
    overall_stats = state.get("overall_stats", {})
    if isinstance(overall_stats, dict):
        for key in ("avg_pct_passed", "avg_pass_rate", "pass_rate"):
            val = overall_stats.get(key)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    pass

    # Fallback: calculate from session results
    completed = [s for s in sessions if s.overall_result in ("pass", "fail")]
    if not completed:
        return None

    pass_count = sum(1 for s in completed if s.overall_result == "pass")
    return round(pass_count / len(completed) * 100, 1)
