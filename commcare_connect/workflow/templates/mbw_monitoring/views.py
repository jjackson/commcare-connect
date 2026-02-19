"""
Views for MBW Monitoring Dashboard.

Three-tab dashboard (Overview, GPS Analysis, Follow-Up Rate) with SSE data loading,
client-side filtering, and interactive features.
"""

import json
import logging
from collections import Counter
from collections.abc import Generator
from datetime import date, timedelta

import sentry_sdk
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.views import View
from django.views.generic import TemplateView

from commcare_connect.workflow.templates.mbw_monitoring.gps_analysis import (
    analyze_gps_metrics,
    build_result_from_analyzed_visits,
    compute_median_meters_per_visit,
    compute_median_minutes_per_visit,
)
from commcare_connect.workflow.templates.mbw_monitoring.pipeline_config import MBW_GPS_PIPELINE_CONFIG
from commcare_connect.workflow.templates.mbw_monitoring.serializers import (
    filter_visits_by_date,
    serialize_flw_summary,
    serialize_visit,
)
from commcare_connect.workflow.templates.mbw_monitoring.data_fetchers import (
    _get_cache_config,
    fetch_gs_forms,
    fetch_opportunity_metadata,
    fetch_registration_forms,
)
from commcare_connect.workflow.templates.mbw_monitoring.followup_analysis import (
    aggregate_flw_followup,
    aggregate_mother_metrics,
    aggregate_visit_status_distribution,
    build_followup_from_pipeline,
    compute_overview_quality_metrics,
    count_mothers_from_pipeline,
    extract_mother_metadata_from_forms,
)
from commcare_connect.workflow.templates.mbw_monitoring.session_adapter import (
    VALID_FLW_RESULTS,
    WorkflowMonitoringSession,
    complete_monitoring_run,
    load_monitoring_run,
    save_dashboard_snapshot,
    save_flw_result as save_flw_result_helper,
)
from commcare_connect.labs.analysis.data_access import fetch_flw_names
from commcare_connect.labs.analysis.pipeline import AnalysisPipeline
from commcare_connect.labs.analysis.sse_streaming import AnalysisPipelineSSEMixin, BaseSSEStreamView, send_sse_event

logger = logging.getLogger(__name__)


def _check_app_version(version, op: str, val: int) -> bool:
    """Check if a visit's app_build_version satisfies the operator comparison."""
    if version is None:
        return False
    try:
        version = int(version)
    except (ValueError, TypeError):
        return False
    if op == "gte":
        return version >= val
    if op == "eq":
        return version == val
    if op == "lte":
        return version <= val
    return True


def _parse_int_param(value: str | None) -> int | None:
    """Safely parse a query parameter to int, returning None if invalid."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def get_default_date_range() -> tuple[date, date]:
    """Get default date range (last 30 days)."""
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    return start_date, end_date


def parse_date_param(date_str: str | None, default: date) -> date:
    """Parse date from query param or return default."""
    if not date_str:
        return default
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        return default


class MBWMonitoringDashboardView(LoginRequiredMixin, TemplateView):
    """
    Main dashboard view rendering the three-tab interface.

    Supports direct URL access to specific tabs via URL path or query param.
    When ?session_id=X is provided, scopes the dashboard to a monitoring session.
    """

    template_name = "custom_analysis/mbw_monitoring/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        labs_context = getattr(self.request, "labs_context", {})
        opportunity_id = labs_context.get("opportunity_id")

        # Check for monitoring session (accept both run_id and session_id for backward compat)
        run_id = _parse_int_param(self.request.GET.get("run_id") or self.request.GET.get("session_id"))
        monitoring_session = None
        if run_id:
            monitoring_session = load_monitoring_run(self.request, run_id)
            if monitoring_session:
                session_opp_id = monitoring_session.opportunity_id
                if session_opp_id:
                    opportunity_id = session_opp_id

        context["opportunity_id"] = opportunity_id
        context["opportunity_name"] = labs_context.get("opportunity_name", "")
        context["has_context"] = bool(opportunity_id)
        context["session_id"] = run_id or ""  # template uses session_id for display
        context["monitoring_session_json"] = json.dumps(
            monitoring_session.to_summary_dict() if monitoring_session else None
        )

        if not opportunity_id:
            context["error"] = "No opportunity selected. Please select an opportunity from the labs context."
            return context

        # Date range defaults
        default_start, default_end = get_default_date_range()
        start_date = parse_date_param(self.request.GET.get("start_date"), default_start)
        end_date = parse_date_param(self.request.GET.get("end_date"), default_end)

        context["start_date"] = start_date.isoformat()
        context["end_date"] = end_date.isoformat()

        # Active tab (from URL kwargs or query param)
        default_tab = kwargs.get("default_tab") or self.request.GET.get("tab", "overview")
        context["active_tab"] = default_tab

        # API URLs
        context["stream_api_url"] = reverse("mbw:stream")
        context["gps_detail_api_url"] = reverse("mbw:gps_detail", kwargs={"username": "__USERNAME__"})
        context["suspend_api_url"] = reverse("mbw:suspend_user")
        context["task_create_api_url"] = reverse("tasks:single_create")

        # OAuth status — check token presence AND expiry
        labs_oauth = self.request.session.get("labs_oauth", {})
        context["has_oauth"] = bool(labs_oauth.get("access_token"))

        commcare_oauth = self.request.session.get("commcare_oauth", {})
        commcare_expires_at = commcare_oauth.get("expires_at", 0)
        commcare_oauth_active = bool(
            commcare_oauth.get("access_token") and timezone.now().timestamp() < commcare_expires_at
        )
        context["commcare_oauth_active"] = commcare_oauth_active

        # Build CommCare authorize URL with ?next= pointing back here
        current_path = self.request.get_full_path()
        commcare_initiate_url = reverse("labs:commcare_initiate") + "?" + urlencode({"next": current_path})
        context["commcare_authorize_url"] = commcare_initiate_url

        # OCS OAuth status
        ocs_oauth = self.request.session.get("ocs_oauth", {})
        ocs_expires_at = ocs_oauth.get("expires_at", 0)
        context["ocs_oauth_active"] = bool(
            ocs_oauth.get("access_token") and timezone.now().timestamp() < ocs_expires_at
        )
        context["ocs_authorize_url"] = reverse("labs:ocs_initiate") + "?" + urlencode({"next": current_path})

        # API URLs for AI task flow
        context["ocs_bots_api_url"] = reverse("tasks:ocs_bots")
        context["ai_initiate_url_template"] = "/tasks/__TASK_ID__/ai/initiate/"

        # Session API URLs (for save/complete)
        context["save_flw_result_url"] = reverse("mbw:save_flw_result")
        context["complete_session_url"] = reverse("mbw:complete_session")

        # Dev fixture mode: show bust cache button
        context["dev_fixture"] = getattr(settings, "MBW_DEV_FIXTURE", False)

        # Cache tolerance defaults (passed to template for SSE URL construction)
        cache_config = _get_cache_config()
        context["default_cache_tolerance_pct"] = cache_config["cache_tolerance_pct"]
        context["default_cache_tolerance"] = cache_config["cache_tolerance_minutes"]

        return context


class MBWMonitoringStreamView(AnalysisPipelineSSEMixin, BaseSSEStreamView):
    """
    SSE streaming endpoint that loads ALL dashboard data in one connection.

    Fetches GPS data, visit cases, mother cases, and computes all metrics.
    Frontend receives one combined payload for all three tabs.
    """

    def stream_data(self, request) -> Generator[str, None, None]:
        """Stream all dashboard data via SSE."""
        try:
            labs_context = getattr(request, "labs_context", {})
            opportunity_id = labs_context.get("opportunity_id")

            if not opportunity_id:
                yield send_sse_event("Error", error="No opportunity selected")
                return

            labs_oauth = request.session.get("labs_oauth", {})
            access_token = labs_oauth.get("access_token")
            if not access_token:
                yield send_sse_event("Error", error="No OAuth token found. Please log in to Connect.")
                return

            # Parse date range (for GPS filtering only)
            default_start, default_end = get_default_date_range()
            start_date = parse_date_param(request.GET.get("start_date"), default_start)
            end_date = parse_date_param(request.GET.get("end_date"), default_end)

            # App version filter (for GPS data only)
            app_version_op = request.GET.get("app_version_op", "")
            app_version_val = _parse_int_param(request.GET.get("app_version_val"))

            # Bust cache: when MBW_DEV_FIXTURE is on and ?bust_cache=1 is passed
            bust_cache = request.GET.get("bust_cache") == "1"
            if bust_cache:
                yield send_sse_event("Cache busted — re-fetching all data...")

            # Load monitoring session early so we know which FLWs to filter to
            session_id = _parse_int_param(request.GET.get("run_id") or request.GET.get("session_id"))
            monitoring_session = None
            session_flw_filter = None
            if session_id:
                monitoring_session = load_monitoring_run(request, session_id)
                if monitoring_session:
                    session_flw_filter = {u.lower() for u in monitoring_session.selected_flw_usernames}
                    logger.info(
                        f"[MBW Dashboard] Monitoring session {session_id}: "
                        f"filtering to {len(session_flw_filter)} FLWs"
                    )

            # Determine which opportunities to load data from.
            # Workflow-based monitoring is single-opportunity.
            if monitoring_session:
                opportunity_ids = [monitoring_session.opportunity_id or opportunity_id]
            else:
                opportunity_ids = [opportunity_id]

            # Step 1: Fetch GPS visit forms via pipeline (per opportunity, merge rows)
            all_pipeline_rows = []
            from_cache = False
            for i, opp_id in enumerate(opportunity_ids):
                if len(opportunity_ids) > 1:
                    yield send_sse_event(
                        f"Loading visits from opportunity {i + 1}/{len(opportunity_ids)}..."
                    )
                else:
                    yield send_sse_event("Loading visit forms from Connect...")

                pipeline = AnalysisPipeline(request)
                pipeline_stream = pipeline.stream_analysis(
                    MBW_GPS_PIPELINE_CONFIG, opportunity_id=opp_id
                )
                yield from self.stream_pipeline_events(pipeline_stream)

                if self._pipeline_result:
                    all_pipeline_rows.extend(self._pipeline_result.rows)
                    from_cache = from_cache or self._pipeline_from_cache

            # Use last pipeline result as a container, replace rows with merged set
            pipeline_result = self._pipeline_result
            if pipeline_result:
                pipeline_result.rows = all_pipeline_rows

            if not pipeline_result or not all_pipeline_rows:
                yield send_sse_event("Error", error="No data returned from Connect API")
                return

            total_rows = len(pipeline_result.rows)
            logger.info(f"[MBW Dashboard] Pipeline returned {total_rows} visits across {len(opportunity_ids)} opportunities")

            # Step 2: Get active Connect users and FLW names (per opportunity, merge)
            yield send_sse_event("Loading FLW data...")
            active_usernames = set()
            flw_names = {}
            for opp_id in opportunity_ids:
                try:
                    opp_flw_names = fetch_flw_names(access_token, opp_id)
                    flw_names.update(opp_flw_names)
                    active_usernames.update(opp_flw_names.keys())
                except Exception as e:
                    logger.warning(f"[MBW Dashboard] Failed to fetch FLW names for opp {opp_id}: {e}")
            logger.info(
                f"[MBW Dashboard] Fetched {len(active_usernames)} FLW usernames "
                f"across {len(opportunity_ids)} opportunities"
            )

            # Normalize usernames to lowercase for case-insensitive comparison.
            # CCHQ lowercases usernames while Connect may preserve original casing.
            active_usernames = {u.lower() for u in active_usernames}
            flw_names = {k.lower(): v for k, v in flw_names.items()}

            # Scope to monitoring session FLWs if applicable
            if session_flw_filter:
                intersection = active_usernames & session_flw_filter
                logger.info(
                    f"[MBW Dashboard] Monitoring session {session_id}: "
                    f"active_usernames={len(active_usernames)}, "
                    f"session_flw_filter={len(session_flw_filter)}, "
                    f"intersection={len(intersection)}"
                )
                if not intersection and session_flw_filter:
                    # Fallback: if the intersection is empty (e.g., FLW names fetch failed
                    # or returned a different set), use the session's FLWs directly.
                    logger.warning(
                        f"[MBW Dashboard] Empty intersection — falling back to session FLWs. "
                        f"session_flw_filter sample: {list(session_flw_filter)[:3]}, "
                        f"active_usernames sample: {list(active_usernames)[:3]}"
                    )
                    active_usernames = session_flw_filter
                else:
                    active_usernames = intersection

            # Step 3: GPS analysis (on ALL visits, then filter by date)
            yield send_sse_event("Analyzing GPS data...")

            visits_for_gps = []
            for row in pipeline_result.rows:
                row_username = (row.username or "").lower()
                if row_username not in active_usernames:
                    continue
                gps_location = None
                if row.latitude is not None and row.longitude is not None:
                    gps_location = f"{row.latitude} {row.longitude}"

                visits_for_gps.append({
                    "id": row.id,
                    "username": row_username,
                    "visit_date": row.visit_date.isoformat() if row.visit_date else None,
                    "entity_name": row.entity_name,
                    "computed": row.computed,
                    "metadata": {"location": gps_location},
                })

            # Apply app version filter to GPS visits if configured
            if app_version_op and app_version_val is not None:
                pre_filter_count = len(visits_for_gps)
                visits_for_gps = [
                    v for v in visits_for_gps
                    if _check_app_version(v["computed"].get("app_build_version"), app_version_op, app_version_val)
                ]
                logger.info(
                    "[MBW Dashboard] App version filter (%s %d): %d -> %d GPS visits",
                    app_version_op, app_version_val, pre_filter_count, len(visits_for_gps),
                )

            gps_result = analyze_gps_metrics(visits_for_gps, flw_names)

            # Filter GPS by date range
            filtered_gps_visits = filter_visits_by_date(gps_result.visits, start_date, end_date)
            gps_result = build_result_from_analyzed_visits(filtered_gps_visits, flw_names)

            gps_data = {
                "total_visits": gps_result.total_visits,
                "total_flagged": gps_result.total_flagged,
                "date_range_start": start_date.isoformat(),
                "date_range_end": end_date.isoformat(),
                "flw_summaries": [serialize_flw_summary(flw) for flw in gps_result.flw_summaries],
            }

            # Step 4: Fetch registration forms from CCHQ
            yield send_sse_event("Fetching registration data...")
            followup_data = None
            overview_data = None
            visit_status_distribution = None
            registration_forms = []

            for opp_id in opportunity_ids:
                try:
                    metadata = fetch_opportunity_metadata(access_token, opp_id)
                    cc_domain = metadata.get("cc_domain")
                    cc_app_id = metadata.get("cc_app_id")
                    if cc_domain:
                        forms = fetch_registration_forms(
                            request, cc_domain, cc_app_id=cc_app_id, bust_cache=bust_cache
                        )
                        registration_forms.extend(forms)
                except Exception as e:
                    logger.warning(f"[MBW Dashboard] Registration form fetch failed for opp {opp_id}: {e}")
            logger.info(f"[MBW Dashboard] Fetched {len(registration_forms)} registration forms")

            # Step 4b: Fetch GS forms from CCHQ (supervisor app, not in Connect pipeline)
            gs_forms = []
            gs_app_id = monitoring_session.gs_app_id if monitoring_session else None
            for opp_id in opportunity_ids:
                try:
                    metadata = fetch_opportunity_metadata(access_token, opp_id)
                    cc_domain = metadata.get("cc_domain")
                    cc_app_id = metadata.get("cc_app_id")
                    if cc_domain:
                        forms = fetch_gs_forms(
                            request, cc_domain, cc_app_id=cc_app_id,
                            gs_app_id=gs_app_id, bust_cache=bust_cache,
                        )
                        gs_forms.extend(forms)
                except Exception as e:
                    logger.warning(f"[MBW Dashboard] GS form fetch failed for opp {opp_id}: {e}")
            logger.info(f"[MBW Dashboard] Fetched {len(gs_forms)} GS forms from CCHQ")

            # Step 5: Build follow-up data from registration forms + pipeline completions
            yield send_sse_event("Calculating follow-up metrics...")

            visit_cases_by_flw = build_followup_from_pipeline(
                all_pipeline_rows, active_usernames, registration_forms=registration_forms
            )

            current_date = date.today()

            # Extract mother metadata FIRST (needed by both flw_followup and drilldown)
            mother_metadata = extract_mother_metadata_from_forms(registration_forms, current_date=current_date)

            flw_followup = aggregate_flw_followup(
                visit_cases_by_flw, current_date, flw_names, mother_cases_map=mother_metadata
            )
            visit_status_distribution = aggregate_visit_status_distribution(
                visit_cases_by_flw, current_date
            )

            # Extract per-mother fields from pipeline rows (needed by drilldown + quality metrics)
            parity_by_mother = {}
            anc_date_by_mother = {}
            pnc_date_by_mother = {}
            baby_dob_by_mother = {}
            for row in all_pipeline_rows:
                form_name = row.computed.get("form_name", "").strip()
                mother_id = row.computed.get("mother_case_id")
                if not mother_id:
                    continue
                if form_name == "ANC Visit":
                    parity = row.computed.get("parity")
                    if parity:
                        parity_by_mother[mother_id] = parity
                    anc_date = row.computed.get("anc_completion_date")
                    if anc_date:
                        anc_date_by_mother[mother_id] = anc_date
                elif form_name == "Post delivery visit":
                    pnc_date = row.computed.get("pnc_completion_date")
                    if pnc_date:
                        pnc_date_by_mother[mother_id] = pnc_date
                    baby_dob = row.computed.get("baby_dob")
                    if baby_dob:
                        baby_dob_by_mother[mother_id] = baby_dob

            # Compute % EBF (exclusive breastfeeding) per FLW from pipeline rows
            ebf_counts_by_flw: dict[str, dict] = {}
            for row in all_pipeline_rows:
                bf_status = (row.computed.get("bf_status") or "").strip()
                if not bf_status:
                    continue
                username = (row.username or "").strip().lower()
                if not username:
                    continue
                if username not in ebf_counts_by_flw:
                    ebf_counts_by_flw[username] = {"ebf": 0, "total": 0}
                ebf_counts_by_flw[username]["total"] += 1
                if "ebf" in bf_status.split():
                    ebf_counts_by_flw[username]["ebf"] += 1

            ebf_pct_by_flw: dict[str, int] = {}
            for username, counts in ebf_counts_by_flw.items():
                if counts["total"] > 0:
                    ebf_pct_by_flw[username] = round(counts["ebf"] / counts["total"] * 100)

            logger.info(
                "[MBW Dashboard] Pipeline extraction: parity=%d, anc_date=%d, pnc_date=%d, baby_dob=%d mothers, ebf=%d FLWs",
                len(parity_by_mother), len(anc_date_by_mother),
                len(pnc_date_by_mother), len(baby_dob_by_mother),
                len(ebf_pct_by_flw),
            )

            # Log form name distribution for debugging

            form_name_counts = Counter(
                row.computed.get("form_name", "").strip()
                for row in all_pipeline_rows
            )
            logger.info("[MBW Dashboard] Form name distribution: %s", dict(form_name_counts))

            flw_drilldown = {}
            for flw_username, flw_cases in visit_cases_by_flw.items():
                flw_drilldown[flw_username] = aggregate_mother_metrics(
                    flw_cases, current_date, mother_cases_map=mother_metadata,
                    anc_date_by_mother=anc_date_by_mother,
                    pnc_date_by_mother=pnc_date_by_mother,
                    baby_dob_by_mother=baby_dob_by_mother,
                )

            followup_data = {
                "flw_summaries": flw_followup,
                "total_cases": sum(len(v) for v in visit_cases_by_flw.values()),
                "flw_drilldown": flw_drilldown,
            }

            # Extract first (oldest) GS score per FLW from CCHQ forms
            gs_scores_by_flw: dict[str, list[tuple[str, str]]] = {}
            for form_dict in gs_forms:
                form = form_dict.get("form", {})
                connect_id = (form.get("load_flw_connect_id", "") or "").lower()
                score = form.get("checklist_percentage", "")
                time_end = form.get("meta", {}).get("timeEnd", "")
                if connect_id and score:
                    gs_scores_by_flw.setdefault(connect_id, []).append((time_end, score))

            first_gs_by_flw = {}
            for connect_id, scores in gs_scores_by_flw.items():
                scores.sort(key=lambda x: x[0])  # oldest first
                first_gs_by_flw[connect_id] = scores[0][1]

            logger.info(
                "[MBW Dashboard] GS scores from CCHQ: %d forms found, %d unique FLWs. "
                "Sample connect_ids: %s, Sample usernames: %s",
                sum(len(v) for v in gs_scores_by_flw.values()),
                len(gs_scores_by_flw),
                list(gs_scores_by_flw.keys())[:3],
                list(active_usernames)[:3],
            )

            # Compute quality/fraud overview metrics
            quality_metrics = compute_overview_quality_metrics(
                visit_cases_by_flw, mother_metadata, parity_by_mother,
                anc_date_by_mother=anc_date_by_mother,
                pnc_date_by_mother=pnc_date_by_mother,
            )

            # Step 6: Build overview metrics
            yield send_sse_event("Building overview...")

            mother_counts = count_mothers_from_pipeline(
                all_pipeline_rows, active_usernames, registration_forms=registration_forms
            )

            # Build GPS median distances per FLW (revisit distance)
            gps_median_by_flw = {}
            for flw in gps_result.flw_summaries:
                if flw.avg_case_distance_km is not None:
                    gps_median_by_flw[flw.username] = round(flw.avg_case_distance_km, 2)

            # Compute median meters/visit and minutes/visit from GPS visits
            meters_per_visit_by_flw = compute_median_meters_per_visit(gps_result.visits)
            minutes_per_visit_by_flw = compute_median_minutes_per_visit(gps_result.visits)

            # Build completed visits and followup rate from follow-up data
            completed_by_flw = {}
            followup_rate_by_flw = {}
            for flw_summary in flw_followup:
                completed_by_flw[flw_summary["username"]] = flw_summary["completed_total"]
                followup_rate_by_flw[flw_summary["username"]] = flw_summary["completion_rate"]

            # Build eligible mothers count per FLW
            eligible_mothers_by_flw = {}
            for flw_username, flw_cases in visit_cases_by_flw.items():
                mother_ids = {c.get("properties", {}).get("mother_case_id", "") for c in flw_cases if c.get("properties", {}).get("mother_case_id")}
                eligible_count = sum(
                    1 for mid in mother_ids
                    if mother_metadata.get(mid, {}).get("properties", {}).get("eligible_full_intervention_bonus") == "1"
                )
                eligible_mothers_by_flw[flw_username] = eligible_count

            # Compute "cases still eligible" per FLW from drill-down data
            # Among eligible mothers, count those still on track (5+ completed OR <= 1 missed)
            cases_eligible_by_flw = {}
            for flw_username, mothers in flw_drilldown.items():
                eligible_mothers = [m for m in mothers if m.get("eligible")]
                still_on_track = 0
                for m in eligible_mothers:
                    completed_count = sum(
                        1 for v in m["visits"] if v["status"].startswith("Completed")
                    )
                    missed_count = sum(
                        1 for v in m["visits"] if v["status"] == "Missed"
                    )
                    if completed_count >= 5 or missed_count <= 1:
                        still_on_track += 1
                total_eligible = len(eligible_mothers)
                cases_eligible_by_flw[flw_username] = {
                    "eligible": still_on_track,
                    "total": total_eligible,
                    "pct": round(still_on_track / total_eligible * 100) if total_eligible > 0 else 0,
                }

            overview_flws = []
            for username in sorted(active_usernames):
                display_name = flw_names.get(username, username)
                overview_flws.append({
                    "username": username,
                    "display_name": display_name,
                    "cases_registered": mother_counts.get(username, 0),
                    "eligible_mothers": eligible_mothers_by_flw.get(username, 0),
                    "first_gs_score": first_gs_by_flw.get(username),
                    "post_test_attempts": None,  # TBD
                    "followup_rate": followup_rate_by_flw.get(username, 0),
                    "ebf_pct": ebf_pct_by_flw.get(username),
                    "revisit_distance_km": gps_median_by_flw.get(username),
                    "median_meters_per_visit": meters_per_visit_by_flw.get(username),
                    "median_minutes_per_visit": minutes_per_visit_by_flw.get(username),
                    **quality_metrics.get(username, {}),
                    "cases_still_eligible": cases_eligible_by_flw.get(username, {"eligible": 0, "total": 0, "pct": 0}),
                })

            overview_data = {
                "flw_summaries": overview_flws,
                "visit_status_distribution": visit_status_distribution,
            }

            # Fetch open tasks so the frontend can grey out the Task button and
            # provide inline task management (task_id needed for detail/update APIs)
            open_tasks = {}
            task_data_access = None
            try:
                from commcare_connect.tasks.data_access import TaskDataAccess

                task_data_access = TaskDataAccess(user=request.user, request=request)
                all_tasks = task_data_access.get_tasks()
                closed_statuses = {"closed", "resolved"}
                for t in all_tasks:
                    if t.username and t.status not in closed_statuses:
                        open_tasks[t.username.lower()] = {
                            "task_id": t.id,
                            "status": t.status,
                            "title": t.title,
                        }
            except Exception as e:
                logger.warning(f"[MBW Dashboard] Failed to fetch tasks: {e}")
            finally:
                if task_data_access:
                    task_data_access.close()
            open_task_usernames = sorted(open_tasks.keys())

            # Build combined response
            response_data = {
                "success": True,
                "opportunity_id": opportunity_id,
                "opportunity_name": labs_context.get("opportunity_name", ""),
                "from_cache": from_cache,
                "dev_fixture": getattr(settings, "MBW_DEV_FIXTURE", False),
                "gps_data": gps_data,
                "followup_data": followup_data,
                "overview_data": overview_data,
                "active_usernames": sorted(active_usernames),
                "flw_names": flw_names,
                "open_tasks": open_tasks,
                "open_task_usernames": open_task_usernames,
            }

            # Include monitoring session data if active
            if monitoring_session:
                response_data["monitoring_session"] = {
                    "id": monitoring_session.id,
                    "title": monitoring_session.title,
                    "status": monitoring_session.status,
                    "flw_results": monitoring_session.flw_results,
                    "progress": monitoring_session.get_monitoring_progress_stats(),
                    "selected_flw_usernames": monitoring_session.selected_flw_usernames,
                }

            # Save dashboard snapshot to run record (best-effort)
            if session_id and monitoring_session:
                # Strip case_id from visit objects to reduce size
                slim_followup = {**followup_data} if followup_data else {}
                if "flw_drilldown" in slim_followup:
                    slim_drilldown = {}
                    for uname, mothers in slim_followup["flw_drilldown"].items():
                        slim_drilldown[uname] = [
                            {
                                **m,
                                "visits": [
                                    {k: v for k, v in vis.items() if k != "case_id"}
                                    for vis in m.get("visits", [])
                                ],
                            }
                            for m in mothers
                        ]
                    slim_followup["flw_drilldown"] = slim_drilldown

                snapshot_payload = {
                    "gps_data": gps_data,
                    "followup_data": slim_followup,
                    "overview_data": overview_data,
                    "active_usernames": sorted(active_usernames),
                    "flw_names": flw_names,
                    "open_tasks": open_tasks,
                    "open_task_usernames": open_task_usernames,
                }
                try:
                    save_dashboard_snapshot(request, session_id, snapshot_payload)
                    logger.info(f"[MBW Dashboard] Saved snapshot for run {session_id}")
                except Exception as e:
                    logger.warning(f"[MBW Dashboard] Snapshot save failed: {e}")

            yield send_sse_event("Complete!", response_data)

        except Exception as e:
            logger.error(f"[MBW Dashboard] Stream failed: {e}", exc_info=True)
            sentry_sdk.capture_exception(e)
            yield send_sse_event("Error", error=f"Failed to load dashboard data: {str(e)}")


class MBWGPSDetailView(LoginRequiredMixin, View):
    """JSON API endpoint for GPS drill-down to get visits for a specific FLW."""

    def get(self, request, username: str):
        labs_oauth = request.session.get("labs_oauth", {})
        if not labs_oauth.get("access_token"):
            return JsonResponse({"error": "Session expired. Please refresh the page."}, status=401)

        labs_context = getattr(request, "labs_context", {})
        opportunity_id = labs_context.get("opportunity_id")

        if not opportunity_id:
            return JsonResponse({"error": "No opportunity selected"}, status=400)

        default_start, default_end = get_default_date_range()
        start_date = parse_date_param(request.GET.get("start_date"), default_start)
        end_date = parse_date_param(request.GET.get("end_date"), default_end)

        try:
            pipeline = AnalysisPipeline(request)
            result = pipeline.stream_analysis_ignore_events(MBW_GPS_PIPELINE_CONFIG, opportunity_id)

            visits_for_analysis = []
            username_lower = username.lower()
            for row in result.rows:
                if (row.username or "").lower() != username_lower:
                    continue

                gps_location = None
                if row.latitude is not None and row.longitude is not None:
                    gps_location = f"{row.latitude} {row.longitude}"

                visits_for_analysis.append({
                    "id": row.id,
                    "username": username_lower,
                    "visit_date": row.visit_date.isoformat() if row.visit_date else None,
                    "entity_name": row.entity_name,
                    "computed": row.computed,
                    "metadata": {"location": gps_location},
                })

            # Apply app version filter if configured
            app_version_op = request.GET.get("app_version_op", "")
            app_version_val = _parse_int_param(request.GET.get("app_version_val"))
            if app_version_op and app_version_val is not None:
                visits_for_analysis = [
                    v for v in visits_for_analysis
                    if _check_app_version(v["computed"].get("app_build_version"), app_version_op, app_version_val)
                ]

            gps_result = analyze_gps_metrics(visits_for_analysis, {})
            filtered_visits = filter_visits_by_date(gps_result.visits, start_date, end_date)

            return JsonResponse({
                "success": True,
                "username": username,
                "visits": [serialize_visit(v) for v in filtered_visits],
                "total_visits": len(filtered_visits),
                "flagged_visits": sum(1 for v in filtered_visits if v.is_flagged),
            })

        except Exception as e:
            logger.error(f"[MBW Dashboard] GPS detail failed: {e}", exc_info=True)
            sentry_sdk.capture_exception(e)
            return JsonResponse({"error": str(e)}, status=500)


class MBWSaveFlwResultView(LoginRequiredMixin, View):
    """Save an assessment result for a FLW in a monitoring session."""

    def post(self, request):
        labs_oauth = request.session.get("labs_oauth", {})
        if not labs_oauth.get("access_token"):
            return JsonResponse({"error": "Session expired"}, status=401)

        try:
            body = json.loads(request.body)
            session_id = _parse_int_param(body.get("session_id"))
            username = body.get("username")
            result = body.get("result")  # One of VALID_FLW_RESULTS or None
            notes = body.get("notes", "")

            if not session_id or not username:
                return JsonResponse({"error": "session_id and username are required"}, status=400)

            if result and result not in VALID_FLW_RESULTS:
                return JsonResponse(
                    {"error": f"result must be one of {VALID_FLW_RESULTS} or null"},
                    status=400,
                )

            assessed_by = request.user.id if request.user.is_authenticated else 0
            updated_session = save_flw_result_helper(request, session_id, username, result, notes, assessed_by)
            if not updated_session:
                return JsonResponse({"error": "Monitoring session not found"}, status=404)

            return JsonResponse({
                "success": True,
                "flw_results": updated_session.flw_results,
                "progress": updated_session.get_monitoring_progress_stats(),
            })

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            logger.error(f"[MBW Dashboard] Save FLW result failed: {e}", exc_info=True)
            return JsonResponse({"error": str(e)}, status=500)


class MBWCompleteSessionView(LoginRequiredMixin, View):
    """Mark a monitoring session as completed."""

    def post(self, request):
        labs_oauth = request.session.get("labs_oauth", {})
        if not labs_oauth.get("access_token"):
            return JsonResponse({"error": "Session expired"}, status=401)

        try:
            body = json.loads(request.body)
            session_id = _parse_int_param(body.get("session_id"))
            overall_result = body.get("overall_result", "completed")
            notes = body.get("notes", "")

            if not session_id:
                return JsonResponse({"error": "session_id is required"}, status=400)

            updated_session = complete_monitoring_run(request, session_id, overall_result, notes)
            if not updated_session:
                return JsonResponse({"error": "Monitoring session not found"}, status=404)

            return JsonResponse({
                "success": True,
                "status": updated_session.status,
                "overall_result": updated_session.overall_result,
            })

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            logger.error(f"[MBW Dashboard] Complete session failed: {e}", exc_info=True)
            return JsonResponse({"error": str(e)}, status=500)


class MBWSnapshotView(LoginRequiredMixin, View):
    """Return stored dashboard snapshot for a monitoring run."""

    def get(self, request):
        labs_oauth = request.session.get("labs_oauth", {})
        if not labs_oauth.get("access_token"):
            return JsonResponse({"error": "Session expired"}, status=401)

        run_id = _parse_int_param(request.GET.get("run_id") or request.GET.get("session_id"))
        if not run_id:
            return JsonResponse({"error": "run_id is required"}, status=400)

        monitoring_session = load_monitoring_run(request, run_id)
        if not monitoring_session:
            return JsonResponse({"error": "Run not found"}, status=404)

        snapshot = monitoring_session.dashboard_snapshot
        if not snapshot:
            return JsonResponse({"has_snapshot": False})

        return JsonResponse({
            "has_snapshot": True,
            "snapshot_timestamp": snapshot.get("timestamp"),
            "success": True,
            "from_snapshot": True,
            "gps_data": snapshot.get("gps_data"),
            "followup_data": snapshot.get("followup_data"),
            "overview_data": snapshot.get("overview_data"),
            "active_usernames": snapshot.get("active_usernames", []),
            "flw_names": snapshot.get("flw_names", {}),
            "open_tasks": snapshot.get("open_tasks", {}),
            "open_task_usernames": snapshot.get("open_task_usernames", []),
            "monitoring_session": {
                "id": monitoring_session.id,
                "title": monitoring_session.title,
                "status": monitoring_session.status,
                "flw_results": monitoring_session.flw_results,
                "progress": monitoring_session.get_monitoring_progress_stats(),
                "selected_flw_usernames": monitoring_session.selected_flw_usernames,
            },
        })


class MBWSuspendUserView(LoginRequiredMixin, View):
    """
    API endpoint to suspend a user.

    Note: This endpoint is retained but not called from the UI.
    "Suspended" is now an assessment label only (stored in flw_results),
    not a Connect API action. The actual Connect API endpoint for
    suspension from Labs environment needs to be confirmed.
    """

    def post(self, request):
        labs_oauth = request.session.get("labs_oauth", {})
        if not labs_oauth.get("access_token"):
            return JsonResponse({"error": "Session expired"}, status=401)

        try:
            body = json.loads(request.body)
            username = body.get("username")
            reason = body.get("reason", "Suspended from MBW Monitoring Dashboard")

            if not username:
                return JsonResponse({"error": "username is required"}, status=400)

            # TODO: Implement actual suspension via Connect API
            # The existing suspension mechanism (OpportunityAccess.suspended = True)
            # is DB-level and not accessible from Labs environment.
            # Need to confirm the Connect API endpoint for this.
            logger.warning(
                f"[MBW Dashboard] Suspend user requested for {username} "
                f"(reason: {reason}) - NOT IMPLEMENTED YET"
            )

            return JsonResponse({
                "success": False,
                "error": "User suspension is not yet available from the dashboard. "
                "Please use the main Connect interface to suspend users.",
            })

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            logger.error(f"[MBW Dashboard] Suspend failed: {e}", exc_info=True)
            return JsonResponse({"error": str(e)}, status=500)
