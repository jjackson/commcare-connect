"""
Data access layer for the Audit of Audits admin report.

Unlike other DataAccess classes, this does NOT subclass BaseDataAccess because
BaseDataAccess auto-populates opportunity_id from request.labs_context, which
would scope results to a single opportunity.

Two-phase query strategy
------------------------
The Connect API requires at least one scope parameter to return private records.
Workflow runs and definitions are stored with opportunity_id scope (always set),
but NOT reliably with organization_id scope (only added if labs_context had it at
creation time). Audit sessions, however, ARE stored with organization_id scope.

Phase 1 — Sessions by organization:
    Query each of the user's ~10 organizations to collect all audit sessions.
    Sessions are reliably indexed by organization_id.

Phase 2 — Runs & definitions by opportunity:
    The caller passes ALL opportunity IDs the user has access to (from their
    OAuth session). This ensures runs with zero sessions are still shown.
    get_records() has no opportunity_id param — scope is set at client init —
    so a short-lived LabsRecordAPIClient is created per opportunity.

Result: every workflow run the user can access is shown, regardless of whether
it has audit sessions yet.
"""

import logging
from datetime import datetime

from commcare_connect.audit.models import AuditSessionRecord
from commcare_connect.labs.integrations.connect.api_client import LabsAPIError, LabsRecordAPIClient
from commcare_connect.workflow.data_access import WorkflowDefinitionRecord, WorkflowRunRecord

logger = logging.getLogger(__name__)

WORKFLOW_EXPERIMENT = "workflow"
AUDIT_EXPERIMENT = "audit"

_DATE_PARSE_FORMATS = ("%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%d/%m/%Y")


def _normalize_date(value: str | None) -> str | None:
    """Normalize a date string to YYYY-MM-DD.

    Handles ISO strings (2026-01-24 or 2026-01-24T...) as well as
    human-readable formats like "Jan 24, 2026" that some workflow
    template states produce.
    """
    if not value:
        return None
    # Already ISO — just take the date portion
    if len(value) >= 10 and value[4:5] == "-":
        return value[:10]
    # Try known human-readable formats
    for fmt in _DATE_PARSE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return value  # Return as-is if unrecognised


class AuditOfAuditsDataAccess:
    """
    Cross-opportunity admin data access for the Audit of Audits report.

    See module docstring for the two-phase query strategy.
    """

    def __init__(self, access_token: str, organization_ids: list[int], opportunity_ids: list[int]):
        self.access_token = access_token
        self.organization_ids = organization_ids
        self.opportunity_ids = opportunity_ids
        # Unscoped client used only for org-scoped session queries
        self.labs_api = LabsRecordAPIClient(access_token=access_token)

    def close(self):
        self.labs_api.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def build_report_data(self) -> list[dict]:
        """
        Fetch audit sessions (org-scoped), then fetch workflow runs and
        definitions (opportunity-scoped) for the opportunities discovered from
        those sessions. Join everything in Python and return rows sorted by
        created_at descending (most recent first).

        API call count: (org_count × 1 session call) + (opp_count × 2 calls)
        Typically ~10 org calls + 2×N opportunity calls.

        Returns:
            List of dicts with keys:
                run_id, definition_id, definition_name, template_type,
                opportunity_id, created_at, period_start, period_end,
                status, selected_count, username, session_count,
                completed_session_count, avg_pct_passed
        """
        if not self.organization_ids and not self.opportunity_ids:
            logger.warning("[AuditOfAudits] No org or opportunity IDs provided — returning empty report")
            return []

        # ── Phase 1: Fetch all audit sessions across all organizations ──────────
        all_sessions: list[AuditSessionRecord] = []
        for org_id in self.organization_ids:
            if not isinstance(org_id, int):
                logger.warning("[AuditOfAudits] Skipping non-integer org_id %r", org_id)
                continue
            try:
                org_sessions: list[AuditSessionRecord] = self.labs_api.get_records(
                    experiment=AUDIT_EXPERIMENT,
                    type="AuditSession",
                    organization_id=org_id,
                    model_class=AuditSessionRecord,
                )
                all_sessions.extend(org_sessions)
            except LabsAPIError:
                logger.exception("[AuditOfAudits] Failed to fetch sessions for org %d", org_id)

        logger.info("[AuditOfAudits] Phase 1: fetched %d sessions across %d orgs",
                    len(all_sessions), len(self.organization_ids))

        # ── Phase 2: Fetch runs & definitions for all user opportunities ─────────
        # Use the full opportunity list (not just session-derived ones) so that
        # runs with zero sessions are still shown in the report.
        opportunity_ids: set[int] = set(self.opportunity_ids)
        logger.info("[AuditOfAudits] Phase 2: querying %d opportunities",
                    len(opportunity_ids))

        def_map: dict[int, WorkflowDefinitionRecord] = {}
        runs: list[WorkflowRunRecord] = []

        for opp_id in opportunity_ids:
            # get_records() has no opportunity_id parameter — scope must be set
            # at client init time, so create a short-lived scoped client.
            try:
                with LabsRecordAPIClient(
                    access_token=self.access_token, opportunity_id=opp_id
                ) as opp_client:
                    # Definitions for this opportunity
                    try:
                        opp_defs: list[WorkflowDefinitionRecord] = opp_client.get_records(
                            experiment=WORKFLOW_EXPERIMENT,
                            type="workflow_definition",
                            model_class=WorkflowDefinitionRecord,
                        )
                        for d in opp_defs:
                            def_map[d.id] = d
                    except LabsAPIError:
                        logger.exception(
                            "[AuditOfAudits] Failed to fetch definitions for opp %d", opp_id
                        )

                    # Runs for this opportunity
                    try:
                        opp_runs: list[WorkflowRunRecord] = opp_client.get_records(
                            experiment=WORKFLOW_EXPERIMENT,
                            type="workflow_run",
                            model_class=WorkflowRunRecord,
                        )
                        logger.info("[AuditOfAudits] opp_id=%d → %d runs", opp_id, len(opp_runs))
                        runs.extend(opp_runs)
                    except LabsAPIError:
                        logger.exception(
                            "[AuditOfAudits] Failed to fetch runs for opp %d", opp_id
                        )
            except Exception:
                logger.exception("[AuditOfAudits] Unexpected error querying opp %d", opp_id)

        logger.info(
            "[AuditOfAudits] Totals — definitions: %d, runs: %d, sessions: %d",
            len(def_map), len(runs), len(all_sessions),
        )

        # ── Phase 3: Join and build rows ─────────────────────────────────────────
        # labs_record_id may be stored as a string in the JSON payload even
        # though run.id is always an int — coerce to int for reliable dict lookup.
        sessions_by_run: dict[int, list[AuditSessionRecord]] = {}
        for session in all_sessions:
            run_id = session.labs_record_id
            if run_id is not None:
                try:
                    sessions_by_run.setdefault(int(run_id), []).append(session)
                except (TypeError, ValueError):
                    logger.warning("[AuditOfAudits] Could not coerce labs_record_id %r to int", run_id)

        rows = []
        for run in runs:
            definition = def_map.get(run.definition_id)
            linked_sessions = sessions_by_run.get(run.id, [])
            avg_pct_passed = _extract_avg_pct_passed(run, linked_sessions)

            rows.append(
                {
                    "run_id": run.id,
                    "definition_id": run.definition_id,
                    "definition_name": definition.name if definition else f"Workflow #{run.definition_id}",
                    "template_type": definition.template_type if definition else "",
                    "opportunity_id": run.opportunity_id,
                    "created_at": run.created_at or "",
                    "period_start": _normalize_date(run.period_start) or "",
                    "period_end": _normalize_date(run.period_end) or "",
                    "status": run.status or "unknown",
                    "selected_count": run.selected_count or 0,
                    # username lives at the top-level API field; fall back to
                    # data["username"] for older runs stored before that field
                    # was reliably populated server-side.
                    "username": run.username or run.data.get("username", "") or "",
                    "session_count": len(linked_sessions),
                    "completed_session_count": sum(
                        1 for s in linked_sessions if s.overall_result in ("pass", "fail")
                    ),
                    "avg_pct_passed": avg_pct_passed,
                }
            )

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
