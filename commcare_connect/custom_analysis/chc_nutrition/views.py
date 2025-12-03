"""
Views for CHC Nutrition analysis.

Provides FLW-level analysis of nutrition metrics using the labs analysis framework.

Uses the unified pipeline pattern via run_analysis_pipeline() which handles:
- Multi-tier caching (LabsRecord, Redis, file)
- Automatic terminal stage detection from config

The visit_result is kept in context for potential drill-down views.

SSE Streaming:
- CHCNutritionStreamView provides Server-Sent Events for real-time progress
- Frontend uses EventSource to receive progress updates as they happen
"""

import json
import logging
from collections.abc import Generator

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, StreamingHttpResponse
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from commcare_connect.custom_analysis.chc_nutrition.analysis_config import CHC_NUTRITION_CONFIG
from commcare_connect.labs.analysis.base import get_flw_names_for_opportunity
from commcare_connect.labs.analysis.pipeline import run_analysis_pipeline

logger = logging.getLogger(__name__)


class CHCNutritionAnalysisView(LoginRequiredMixin, TemplateView):
    """
    Main analysis view for CHC Nutrition project.

    Displays one row per FLW with aggregated nutrition and health metrics.
    Uses progressive loading: the page loads quickly with a loading indicator,
    then fetches data asynchronously via the CHCNutritionDataView API.
    """

    template_name = "custom_analysis/chc_nutrition/analysis.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Check labs context
        labs_context = getattr(self.request, "labs_context", {})
        opportunity_id = labs_context.get("opportunity_id")

        context["opportunity_id"] = opportunity_id
        context["opportunity_name"] = labs_context.get("opportunity_name")
        context["has_context"] = bool(opportunity_id)

        if not opportunity_id:
            context["error"] = "No opportunity selected. Please select an opportunity from the labs context."
            return context

        # Provide the API endpoint URLs for async data loading
        context["data_api_url"] = reverse("chc_nutrition:api_data")
        context["stream_api_url"] = reverse("chc_nutrition:api_stream")

        return context


class CHCNutritionDataView(LoginRequiredMixin, View):
    """API endpoint to load CHC Nutrition data asynchronously."""

    def get(self, request):
        """Return CHC Nutrition analysis data as JSON for progressive loading."""
        try:
            # Check labs context
            labs_context = getattr(request, "labs_context", {})
            opportunity_id = labs_context.get("opportunity_id")

            if not opportunity_id:
                return JsonResponse(
                    {"error": "No opportunity selected. Please select an opportunity from the labs context."},
                    status=400,
                )

            logger.info(f"[CHC Nutrition API] Starting analysis for opportunity {opportunity_id}")

            # Run the unified analysis pipeline
            # This handles all caching (LabsRecord if ?use_labs_record_cache=true, Redis, file)
            logger.info("[CHC Nutrition API] Step 1/3: Running analysis pipeline...")
            flw_result = run_analysis_pipeline(request, CHC_NUTRITION_CONFIG)
            logger.info(f"[CHC Nutrition API] Got {len(flw_result.rows)} FLWs from pipeline")

            # Step 2: Get FLW display names
            logger.info("[CHC Nutrition API] Step 2/3: Fetching FLW display names...")
            try:
                flw_names = get_flw_names_for_opportunity(request)
                logger.info(f"[CHC Nutrition API] Loaded display names for {len(flw_names)} FLWs")
            except Exception as e:
                logger.warning(f"Failed to fetch FLW names: {e}")
                flw_names = {}

            # Step 3: Build response data
            logger.info("[CHC Nutrition API] Step 3/3: Building response...")

            # Process FLW rows
            flws_data = []
            for flw in flw_result.rows:
                display_name = flw_names.get(flw.username, flw.username)

                # Calculate gender split
                male_count = flw.custom_fields.get("male_count") or 0
                female_count = flw.custom_fields.get("female_count") or 0
                total_gendered = male_count + female_count
                gender_split_female_pct = (
                    round((female_count / total_gendered) * 100, 1) if total_gendered > 0 else None
                )

                flw_data = {
                    "username": flw.username,
                    "display_name": display_name,
                    "total_visits": flw.total_visits,
                    "approved_visits": flw.approved_visits,
                    "approval_rate": round(flw.approval_rate, 1) if flw.approval_rate else 0,
                    "days_active": flw.days_active,
                    "custom_fields": flw.custom_fields,
                    "gender_split_female_pct": gender_split_female_pct,
                    "male_count": male_count,
                    "female_count": female_count,
                }
                flws_data.append(flw_data)

            # Calculate summary stats
            summary = flw_result.get_summary_stats()

            # Calculate nutrition summary
            nutrition_summary = self._get_nutrition_summary(flw_result)

            # Get opportunity info for audit button
            opportunity = labs_context.get("opportunity", {})
            deliver_app = opportunity.get("deliver_app", {})

            response_data = {
                "success": True,
                "flws": flws_data,
                "summary": summary,
                "nutrition_summary": nutrition_summary,
                "total_visits": flw_result.metadata.get("total_visits", 0),
                "opportunity_id": opportunity_id,
                "opportunity_name": labs_context.get("opportunity_name"),
                "deliver_app_cc_app_id": deliver_app.get("cc_app_id"),
                "deliver_app_cc_domain": deliver_app.get("cc_domain"),
                "from_cache": request.GET.get("refresh") != "1",
            }

            logger.info(
                f"[CHC Nutrition API] Complete! Returning {len(flws_data)} FLWs, "
                f"{nutrition_summary.get('total_muac_measurements', 0)} MUAC measurements"
            )
            return JsonResponse(response_data)

        except Exception as e:
            logger.error(f"[CHC Nutrition API] Failed to compute analysis: {e}", exc_info=True)
            return JsonResponse({"error": str(e)}, status=500)

    def _get_nutrition_summary(self, result) -> dict:
        """
        Calculate nutrition-specific summary statistics.

        Args:
            result: FLWAnalysisResult

        Returns:
            Dictionary of nutrition-specific metrics
        """
        if not result.rows:
            return {}

        # Aggregate across all FLWs (handle None values explicitly)
        total_muac_measurements = sum(row.custom_fields.get("muac_measurements_count") or 0 for row in result.rows)
        total_muac_consents = sum(row.custom_fields.get("muac_consent_count") or 0 for row in result.rows)
        total_children_unwell = sum(row.custom_fields.get("children_unwell_count") or 0 for row in result.rows)
        total_malnutrition_diagnosed = sum(
            row.custom_fields.get("malnutrition_diagnosed_count") or 0 for row in result.rows
        )
        total_under_treatment = sum(
            row.custom_fields.get("under_malnutrition_treatment_count") or 0 for row in result.rows
        )
        total_va_doses = sum(row.custom_fields.get("received_va_dose_before_count") or 0 for row in result.rows)

        # SAM and MAM counts
        total_sam = sum(row.custom_fields.get("sam_count") or 0 for row in result.rows)
        total_mam = sum(row.custom_fields.get("mam_count") or 0 for row in result.rows)

        # Calculate averages
        avg_muac_measurements_per_flw = total_muac_measurements / len(result.rows) if result.rows else 0

        # MUAC consent rate
        muac_consent_rate = (total_muac_consents / total_muac_measurements * 100) if total_muac_measurements > 0 else 0

        # SAM and MAM rates
        sam_rate = (total_sam / total_muac_measurements * 100) if total_muac_measurements > 0 else 0
        mam_rate = (total_mam / total_muac_measurements * 100) if total_muac_measurements > 0 else 0

        return {
            "total_muac_measurements": total_muac_measurements,
            "total_muac_consents": total_muac_consents,
            "muac_consent_rate": round(muac_consent_rate, 1),
            "avg_muac_measurements_per_flw": round(avg_muac_measurements_per_flw, 2),
            "total_children_unwell": total_children_unwell,
            "total_malnutrition_diagnosed": total_malnutrition_diagnosed,
            "total_under_treatment": total_under_treatment,
            "total_va_doses": total_va_doses,
            "total_sam": total_sam,
            "sam_rate": round(sam_rate, 1),
            "total_mam": total_mam,
            "mam_rate": round(mam_rate, 1),
        }


class CHCNutritionStreamView(LoginRequiredMixin, View):
    """
    SSE streaming endpoint for CHC Nutrition analysis with real-time progress.

    Uses Server-Sent Events to push progress updates to the frontend as each
    step of the analysis pipeline completes. This gives users visibility into
    what's actually happening during long-running operations.

    Progress events are sent as JSON with format:
        {"step": 1, "total": 7, "message": "...", "complete": false}

    The final event includes the full data payload:
        {"step": 7, "total": 7, "message": "Complete!", "complete": true, "data": {...}}
    """

    def get(self, request):
        """Stream analysis progress via Server-Sent Events."""
        # Check authentication
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Not authenticated"}, status=401)

        # Check labs context
        labs_context = getattr(request, "labs_context", {})
        opportunity_id = labs_context.get("opportunity_id")

        if not opportunity_id:
            return JsonResponse(
                {"error": "No opportunity selected. Please select an opportunity from the labs context."},
                status=400,
            )

        # Return streaming response
        response = StreamingHttpResponse(
            self._stream_analysis(request, labs_context, opportunity_id),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"  # Disable nginx buffering
        return response

    def _stream_analysis(self, request, labs_context: dict, opportunity_id: int) -> Generator[str, None, None]:
        """
        Generator that yields SSE events as analysis progresses.

        Each yield sends a Server-Sent Event to the client.
        Uses streaming download for real-time progress during data fetch.
        """
        total_steps = 7

        def send_progress(step: int, message: str, data: dict | None = None) -> str:
            """Format and return an SSE event."""
            event_data = {
                "step": step,
                "total": total_steps,
                "message": message,
                "complete": step == total_steps,
            }
            if data is not None:
                event_data["data"] = data
            return f"data: {json.dumps(event_data)}\n\n"

        def format_bytes(num_bytes: int) -> str:
            """Format bytes as human-readable string (e.g., '15.2 MB')."""
            mb = num_bytes / (1024 * 1024)
            return f"{mb:.1f} MB"

        try:
            # Step 1: Checking cache
            yield send_progress(1, "Checking cache...")
            logger.info(f"[CHC Nutrition Stream] Step 1/{total_steps}: Checking cache for opp {opportunity_id}")

            # Import here to avoid circular imports
            from commcare_connect.labs.analysis.cache import AnalysisCacheManager

            force_refresh = request.GET.get("refresh") == "1"

            # Check if we have cached results
            cache_manager = AnalysisCacheManager(opportunity_id, CHC_NUTRITION_CONFIG)
            cached = None if force_refresh else cache_manager.get_results_cache()

            if cached and not force_refresh:
                # Step 2: Cache hit - fast path
                yield send_progress(2, "Cache hit! Loading cached results...")
                logger.info(f"[CHC Nutrition Stream] Cache HIT for opp {opportunity_id}")

                flw_result = cached["result"]

                # Skip to step 5 for FLW names
                yield send_progress(5, "Fetching FLW display names...")
                try:
                    flw_names = get_flw_names_for_opportunity(request)
                except Exception as e:
                    logger.warning(f"Failed to fetch FLW names: {e}")
                    flw_names = {}

                # Step 6: Build response
                yield send_progress(6, "Building response...")
                response_data = self._build_response(request, flw_result, flw_names, labs_context, from_cache=True)

                # Step 7: Complete
                yield send_progress(7, "Complete!", response_data)
                return

            # Step 2: Fetching data from Connect API with streaming progress
            yield send_progress(2, "Connecting to Connect API...")
            logger.info(f"[CHC Nutrition Stream] Step 2/{total_steps}: Streaming download from Connect")

            # Get access token and visit count for cache validation
            access_token = request.session.get("labs_oauth", {}).get("access_token")
            opportunity = labs_context.get("opportunity", {})
            current_visit_count = opportunity.get("visit_count")

            # Use streaming download with progress updates
            from commcare_connect.labs.analysis.base import LocalUserVisit
            from commcare_connect.labs.api_cache import _parse_csv_bytes, stream_user_visits_with_progress

            csv_bytes = None

            for event in stream_user_visits_with_progress(
                opportunity_id=opportunity_id,
                access_token=access_token,
                current_visit_count=current_visit_count,
                force_refresh=force_refresh,
            ):
                event_type = event[0]

                if event_type == "cached":
                    # Raw CSV was in cache - no download needed
                    csv_bytes = event[1]
                    yield send_progress(2, f"Using cached data ({format_bytes(len(csv_bytes))})...")
                    logger.info(f"[CHC Nutrition Stream] Raw CSV cache hit: {len(csv_bytes)} bytes")

                elif event_type == "progress":
                    # Download progress update
                    _, bytes_downloaded, total_bytes = event
                    if total_bytes > 0:
                        pct = int(bytes_downloaded / total_bytes * 100)
                        msg = f"Downloading... {format_bytes(bytes_downloaded)} / {format_bytes(total_bytes)} ({pct}%)"
                    else:
                        msg = f"Downloading... {format_bytes(bytes_downloaded)}"
                    yield send_progress(2, msg)

                elif event_type == "complete":
                    # Download complete
                    csv_bytes = event[1]
                    yield send_progress(2, f"Download complete ({format_bytes(len(csv_bytes))})")
                    logger.info(f"[CHC Nutrition Stream] Download complete: {len(csv_bytes)} bytes")

            # Step 3: Parse CSV data directly (no re-fetch!)
            yield send_progress(3, "Parsing visit data...")
            logger.info(f"[CHC Nutrition Stream] Step 3/{total_steps}: Parsing {len(csv_bytes)} bytes")

            # Parse CSV bytes directly into visit dicts, then wrap as LocalUserVisit
            visit_dicts = _parse_csv_bytes(csv_bytes, opportunity_id, skip_form_json=False)
            all_visits = [LocalUserVisit(data) for data in visit_dicts]

            yield send_progress(3, f"Processing {len(all_visits)} visits...")
            logger.info(f"[CHC Nutrition Stream] Parsed {len(all_visits)} visits")

            # Compute visit-level analysis using prefetched visits (no re-fetch)
            from commcare_connect.labs.analysis.visit_analyzer import VisitAnalyzer

            visit_analyzer = VisitAnalyzer(request, CHC_NUTRITION_CONFIG)
            visit_result = visit_analyzer.compute(prefetched_visits=all_visits)
            visit_count = visit_result.metadata.get("total_visits", 0)

            # Cache visit results
            cache_manager.set_visit_results_cache(visit_count, visit_result)

            # Step 4: Aggregating to FLW level
            yield send_progress(4, f"Aggregating {visit_count} visits to FLW level...")
            logger.info(f"[CHC Nutrition Stream] Step 4/{total_steps}: Aggregating to FLW level")

            from commcare_connect.labs.analysis.flw_analyzer import FLWAnalyzer

            flw_analyzer = FLWAnalyzer(request, CHC_NUTRITION_CONFIG)
            flw_result = flw_analyzer.from_visit_result(visit_result)

            # Cache FLW results
            cache_manager.set_results_cache(visit_count, flw_result)

            # Sync context
            from commcare_connect.labs.analysis.cache import sync_labs_context_visit_count

            sync_labs_context_visit_count(request, visit_count, opportunity_id)

            # Step 5: Fetching FLW display names
            yield send_progress(5, "Fetching FLW display names...")
            logger.info(f"[CHC Nutrition Stream] Step 5/{total_steps}: Fetching FLW names")

            try:
                flw_names = get_flw_names_for_opportunity(request)
                logger.info(f"[CHC Nutrition Stream] Loaded display names for {len(flw_names)} FLWs")
            except Exception as e:
                logger.warning(f"Failed to fetch FLW names: {e}")
                flw_names = {}

            # Step 6: Building response
            yield send_progress(6, f"Building response with {len(flw_result.rows)} FLWs...")
            logger.info(f"[CHC Nutrition Stream] Step 6/{total_steps}: Building response")

            response_data = self._build_response(request, flw_result, flw_names, labs_context, from_cache=False)

            # Step 7: Complete
            yield send_progress(7, "Complete!", response_data)
            logger.info(
                f"[CHC Nutrition Stream] Step 7/{total_steps}: Complete! "
                f"{len(flw_result.rows)} FLWs, {visit_count} visits"
            )

        except Exception as e:
            logger.error(f"[CHC Nutrition Stream] Error: {e}", exc_info=True)
            error_event = {
                "error": str(e),
                "step": 0,
                "total": total_steps,
                "message": f"Error: {str(e)}",
                "complete": True,
            }
            yield f"data: {json.dumps(error_event)}\n\n"

    def _build_response(self, request, flw_result, flw_names: dict, labs_context: dict, from_cache: bool) -> dict:
        """Build the final response data payload."""
        flws_data = []
        for flw in flw_result.rows:
            display_name = flw_names.get(flw.username, flw.username)

            # Calculate gender split
            male_count = flw.custom_fields.get("male_count") or 0
            female_count = flw.custom_fields.get("female_count") or 0
            total_gendered = male_count + female_count
            gender_split_female_pct = round((female_count / total_gendered) * 100, 1) if total_gendered > 0 else None

            flw_data = {
                "username": flw.username,
                "display_name": display_name,
                "total_visits": flw.total_visits,
                "approved_visits": flw.approved_visits,
                "approval_rate": round(flw.approval_rate, 1) if flw.approval_rate else 0,
                "days_active": flw.days_active,
                "custom_fields": flw.custom_fields,
                "gender_split_female_pct": gender_split_female_pct,
                "male_count": male_count,
                "female_count": female_count,
            }
            flws_data.append(flw_data)

        # Calculate summary stats
        summary = flw_result.get_summary_stats()

        # Calculate nutrition summary
        nutrition_summary = self._get_nutrition_summary(flw_result)

        # Get opportunity info
        opportunity = labs_context.get("opportunity", {})
        deliver_app = opportunity.get("deliver_app", {})

        return {
            "success": True,
            "flws": flws_data,
            "summary": summary,
            "nutrition_summary": nutrition_summary,
            "total_visits": flw_result.metadata.get("total_visits", 0),
            "opportunity_id": labs_context.get("opportunity_id"),
            "opportunity_name": labs_context.get("opportunity_name"),
            "deliver_app_cc_app_id": deliver_app.get("cc_app_id"),
            "deliver_app_cc_domain": deliver_app.get("cc_domain"),
            "from_cache": from_cache,
        }

    def _get_nutrition_summary(self, result) -> dict:
        """Calculate nutrition-specific summary statistics."""
        if not result.rows:
            return {}

        total_muac_measurements = sum(row.custom_fields.get("muac_measurements_count") or 0 for row in result.rows)
        total_muac_consents = sum(row.custom_fields.get("muac_consent_count") or 0 for row in result.rows)
        total_children_unwell = sum(row.custom_fields.get("children_unwell_count") or 0 for row in result.rows)
        total_malnutrition_diagnosed = sum(
            row.custom_fields.get("malnutrition_diagnosed_count") or 0 for row in result.rows
        )
        total_under_treatment = sum(
            row.custom_fields.get("under_malnutrition_treatment_count") or 0 for row in result.rows
        )
        total_va_doses = sum(row.custom_fields.get("received_va_dose_before_count") or 0 for row in result.rows)
        total_sam = sum(row.custom_fields.get("sam_count") or 0 for row in result.rows)
        total_mam = sum(row.custom_fields.get("mam_count") or 0 for row in result.rows)

        avg_muac_measurements_per_flw = total_muac_measurements / len(result.rows) if result.rows else 0
        muac_consent_rate = (total_muac_consents / total_muac_measurements * 100) if total_muac_measurements > 0 else 0
        sam_rate = (total_sam / total_muac_measurements * 100) if total_muac_measurements > 0 else 0
        mam_rate = (total_mam / total_muac_measurements * 100) if total_muac_measurements > 0 else 0

        return {
            "total_muac_measurements": total_muac_measurements,
            "total_muac_consents": total_muac_consents,
            "muac_consent_rate": round(muac_consent_rate, 1),
            "avg_muac_measurements_per_flw": round(avg_muac_measurements_per_flw, 2),
            "total_children_unwell": total_children_unwell,
            "total_malnutrition_diagnosed": total_malnutrition_diagnosed,
            "total_under_treatment": total_under_treatment,
            "total_va_doses": total_va_doses,
            "total_sam": total_sam,
            "sam_rate": round(sam_rate, 1),
            "total_mam": total_mam,
            "mam_rate": round(mam_rate, 1),
        }
