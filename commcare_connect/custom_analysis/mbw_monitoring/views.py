"""
Views for MBW Monitoring Dashboard.

Three-tab dashboard (Overview, GPS Analysis, Follow-Up Rate) with SSE data loading,
client-side filtering, and interactive features.
"""

import json
import logging
import statistics
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

from commcare_connect.custom_analysis.mbw.gps_analysis import (
    analyze_gps_metrics,
    build_result_from_analyzed_visits,
)
from commcare_connect.custom_analysis.mbw.pipeline_config import MBW_GPS_PIPELINE_CONFIG
from commcare_connect.custom_analysis.mbw.views import (
    filter_visits_by_date,
    serialize_flw_summary,
    serialize_visit,
)
from commcare_connect.custom_analysis.mbw_monitoring.data_fetchers import (
    _get_cache_config,
    bust_mbw_hq_cache,
    count_mother_cases_by_flw,
    extract_case_ids_from_visits,
    extract_mother_case_ids_from_cases,
    fetch_mother_cases_by_ids,
    fetch_opportunity_metadata,
    fetch_visit_cases_by_ids,
    get_active_connect_usernames,
    group_visit_cases_by_flw,
)
from commcare_connect.custom_analysis.mbw_monitoring.followup_analysis import (
    aggregate_flw_followup,
    aggregate_mother_metrics,
    aggregate_visit_status_distribution,
)
from commcare_connect.labs.analysis.pipeline import AnalysisPipeline
from commcare_connect.labs.analysis.sse_streaming import AnalysisPipelineSSEMixin, BaseSSEStreamView, send_sse_event

logger = logging.getLogger(__name__)


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
    """

    template_name = "custom_analysis/mbw_monitoring/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        labs_context = getattr(self.request, "labs_context", {})
        opportunity_id = labs_context.get("opportunity_id")

        context["opportunity_id"] = opportunity_id
        context["opportunity_name"] = labs_context.get("opportunity_name", "")
        context["has_context"] = bool(opportunity_id)

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

            # Bust cache: when MBW_DEV_FIXTURE is on and ?bust_cache=1 is passed,
            # clear the HQ case caches and force a full re-fetch
            bust_cache = request.GET.get("bust_cache") == "1"
            if bust_cache:
                bust_mbw_hq_cache()
                yield send_sse_event("Cache busted — re-fetching all data...")

            # Step 1: Fetch GPS visit forms via pipeline
            yield send_sse_event("Loading visit forms from Connect...")

            pipeline = AnalysisPipeline(request)
            pipeline_stream = pipeline.stream_analysis(MBW_GPS_PIPELINE_CONFIG, opportunity_id=opportunity_id)
            yield from self.stream_pipeline_events(pipeline_stream)

            pipeline_result = self._pipeline_result
            from_cache = self._pipeline_from_cache

            if not pipeline_result:
                yield send_sse_event("Error", error="No data returned from Connect API")
                return

            total_rows = len(pipeline_result.rows)
            logger.info(f"[MBW Dashboard] Pipeline returned {total_rows} visits")

            # Step 2: Get active Connect users and FLW names
            yield send_sse_event("Loading FLW data...")
            try:
                active_usernames, flw_names = get_active_connect_usernames(request)
            except Exception as e:
                logger.warning(f"[MBW Dashboard] Failed to fetch FLW names: {e}")
                active_usernames = set()
                flw_names = {}

            # Step 3: GPS analysis (on ALL visits, then filter by date)
            yield send_sse_event("Analyzing GPS data...")

            visits_for_gps = []
            for row in pipeline_result.rows:
                if row.username not in active_usernames:
                    continue
                gps_location = None
                if row.latitude is not None and row.longitude is not None:
                    gps_location = f"{row.latitude} {row.longitude}"

                visits_for_gps.append({
                    "id": row.id,
                    "username": row.username,
                    "visit_date": row.visit_date.isoformat() if row.visit_date else None,
                    "entity_name": row.entity_name,
                    "computed": row.computed,
                    "metadata": {"location": gps_location},
                })

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

            # Step 4: Fetch opportunity metadata to get cc_domain
            yield send_sse_event("Fetching opportunity metadata...")
            followup_data = None
            overview_data = None
            visit_status_distribution = None

            try:
                metadata = fetch_opportunity_metadata(access_token, opportunity_id)
                cc_domain = metadata["cc_domain"]

                # Step 5: Extract case IDs and fetch visit cases from CommCare HQ
                case_ids = extract_case_ids_from_visits(pipeline_result.rows)
                logger.info(f"[MBW Dashboard] Found {len(case_ids)} unique case IDs")

                if case_ids:
                    yield send_sse_event(f"Fetching {len(case_ids)} visit cases from CommCare HQ...")

                    try:
                        visit_cases = fetch_visit_cases_by_ids(
                            request, cc_domain, case_ids, bust_cache=bust_cache
                        )
                        logger.info(f"[MBW Dashboard] Fetched {len(visit_cases)} visit cases")

                        # Step 6: Extract and fetch mother cases
                        mother_case_ids = extract_mother_case_ids_from_cases(visit_cases)
                        mother_cases = []
                        if mother_case_ids:
                            yield send_sse_event(f"Fetching {len(mother_case_ids)} mother cases...")
                            mother_cases = fetch_mother_cases_by_ids(
                                request, cc_domain, mother_case_ids, bust_cache=bust_cache
                            )

                        # Step 7: Group and calculate follow-up metrics
                        yield send_sse_event("Calculating follow-up metrics...")

                        visit_cases_by_flw = group_visit_cases_by_flw(
                            visit_cases, pipeline_result.rows, active_usernames
                        )

                        current_date = date.today()
                        flw_followup = aggregate_flw_followup(visit_cases_by_flw, current_date, flw_names)
                        visit_status_distribution = aggregate_visit_status_distribution(
                            visit_cases_by_flw, current_date
                        )

                        # Build mother case lookup for enriching drill-down data
                        mother_cases_map = {
                            c.get("case_id"): c for c in mother_cases
                        } if mother_cases else {}

                        # Pre-compute per-FLW mother drill-down data so the frontend
                        # doesn't need to make separate API calls on row expand
                        flw_drilldown = {}
                        for flw_username, flw_cases in visit_cases_by_flw.items():
                            flw_drilldown[flw_username] = aggregate_mother_metrics(
                                flw_cases, current_date, mother_cases_map
                            )

                        followup_data = {
                            "flw_summaries": flw_followup,
                            "total_cases": len(visit_cases),
                            "flw_drilldown": flw_drilldown,
                        }

                        # Step 8: Build overview metrics
                        yield send_sse_event("Building overview...")

                        mother_counts = count_mother_cases_by_flw(mother_cases, active_usernames)

                        # Build GPS median distances per FLW
                        gps_median_by_flw = {}
                        for flw in gps_result.flw_summaries:
                            if flw.avg_case_distance_km is not None:
                                gps_median_by_flw[flw.username] = round(flw.avg_case_distance_km, 2)

                        # Build completed visits from follow-up data
                        completed_by_flw = {}
                        for flw_summary in flw_followup:
                            completed_by_flw[flw_summary["username"]] = flw_summary["completed_total"]

                        overview_flws = []
                        for username in sorted(active_usernames):
                            display_name = flw_names.get(username, username)
                            overview_flws.append({
                                "username": username,
                                "display_name": display_name,
                                "cases_registered": mother_counts.get(username, 0),
                                "first_gs_score": None,  # TBD
                                "post_test_attempts": None,  # TBD
                                "pct_visits_due_5_plus_days": None,  # TBD
                                "completed_visits": completed_by_flw.get(username, 0),
                                "median_meters_per_case": gps_median_by_flw.get(username),
                            })

                        overview_data = {
                            "flw_summaries": overview_flws,
                            "visit_status_distribution": visit_status_distribution,
                        }

                    except ValueError as e:
                        logger.warning(f"[MBW Dashboard] CommCare HQ fetch failed: {e}")
                        yield send_sse_event(f"Warning: Could not fetch CommCare HQ data: {e}")
                else:
                    logger.info("[MBW Dashboard] No case IDs found in visit data")

            except ValueError as e:
                logger.warning(f"[MBW Dashboard] Metadata fetch failed: {e}")
                yield send_sse_event(f"Warning: Could not fetch CommCare HQ data: {e}")

            # Fetch open task usernames so the frontend can grey out the Task button
            open_task_usernames = []
            try:
                from commcare_connect.tasks.data_access import TaskDataAccess

                data_access = TaskDataAccess(user=request.user, request=request)
                all_tasks = data_access.get_tasks()
                data_access.close()
                closed_statuses = {"closed", "resolved"}
                open_task_usernames = sorted(set(
                    t.username for t in all_tasks
                    if t.username and t.status not in closed_statuses
                ))
            except Exception as e:
                logger.warning(f"[MBW Dashboard] Failed to fetch tasks: {e}")

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
                "open_task_usernames": open_task_usernames,
            }

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
            for row in result.rows:
                if row.username != username:
                    continue

                gps_location = None
                if row.latitude is not None and row.longitude is not None:
                    gps_location = f"{row.latitude} {row.longitude}"

                visits_for_analysis.append({
                    "id": row.id,
                    "username": row.username,
                    "visit_date": row.visit_date.isoformat() if row.visit_date else None,
                    "entity_name": row.entity_name,
                    "computed": row.computed,
                    "metadata": {"location": gps_location},
                })

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


class MBWSuspendUserView(LoginRequiredMixin, View):
    """
    API endpoint to suspend a user.

    Note: This is a placeholder for MVP. The actual Connect API endpoint
    for suspension from Labs environment needs to be confirmed.
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
