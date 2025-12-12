"""
KMC-specific views using pipeline and SSE streaming.
"""

import logging
from collections.abc import Generator

import httpx
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.views.generic import TemplateView, View

from commcare_connect.custom_analysis.kmc import timeline_config
from commcare_connect.custom_analysis.kmc.pipeline_config import KMC_PIPELINE_CONFIG
from commcare_connect.labs.analysis.pipeline import AnalysisPipeline
from commcare_connect.labs.analysis.sse_streaming import AnalysisPipelineSSEMixin, BaseSSEStreamView, send_sse_event
from commcare_connect.labs.configurable_ui.views import GenericTimelineDataView, GenericTimelineDetailView
from commcare_connect.opportunity.models import BlobMeta

logger = logging.getLogger(__name__)


class KMCTimelineListView(LoginRequiredMixin, TemplateView):
    """List all KMC children using pipeline data."""

    template_name = "custom_analysis/kmc/child_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Check for context
        labs_context = getattr(self.request, "labs_context", {})
        opportunity_id = labs_context.get("opportunity_id")

        context["has_context"] = bool(opportunity_id)
        context["opportunity_id"] = opportunity_id

        # Check for OAuth token
        labs_oauth = self.request.session.get("labs_oauth", {})
        context["has_connect_token"] = bool(labs_oauth.get("access_token"))

        # Provide the SSE stream API URL
        context["stream_api_url"] = reverse("kmc:child_list_stream")

        return context


class KMCTimelineDetailView(GenericTimelineDetailView):
    """Display timeline for a single KMC child."""

    api_url_name = "kmc:api_child_data"


class KMCTimelineDataView(GenericTimelineDataView):
    """API endpoint for KMC child timeline data."""

    config_module = timeline_config
    pipeline_config = KMC_PIPELINE_CONFIG


class KMCChildListStreamView(AnalysisPipelineSSEMixin, BaseSSEStreamView):
    """SSE streaming endpoint for loading KMC child list with progress - uses reusable mixin."""

    def stream_data(self, request) -> Generator[str, None, None]:
        """Stream child list data loading progress via SSE."""
        try:
            # Check for context
            labs_context = getattr(request, "labs_context", {})
            opportunity_id = labs_context.get("opportunity_id")

            if not opportunity_id:
                yield send_sse_event("Error", error="No opportunity selected")
                return

            # Check for OAuth token
            labs_oauth = request.session.get("labs_oauth", {})
            if not labs_oauth.get("access_token"):
                yield send_sse_event("Error", error="No OAuth token found. Please log in to Connect.")
                return

            # Run analysis pipeline with streaming - manually process like explorer does
            pipeline = AnalysisPipeline(request)
            pipeline_stream = pipeline.stream_analysis(KMC_PIPELINE_CONFIG, opportunity_id=opportunity_id)

            logger.info(f"[KMC] Starting stream for opportunity {opportunity_id}")

            result = None
            from_cache = False

            # Process pipeline events
            from commcare_connect.labs.analysis.pipeline import EVENT_DOWNLOAD, EVENT_RESULT, EVENT_STATUS

            for event_type, event_data in pipeline_stream:
                if event_type == EVENT_STATUS:
                    message = event_data.get("message", "Processing...")
                    from_cache = from_cache or "cache" in message.lower()
                    yield send_sse_event(message)

                elif event_type == EVENT_DOWNLOAD:
                    bytes_dl = event_data.get("bytes", 0)
                    total_bytes = event_data.get("total", 0)
                    if total_bytes > 0:
                        mb_dl = bytes_dl / (1024 * 1024)
                        mb_total = total_bytes / (1024 * 1024)
                        pct = int(bytes_dl / total_bytes * 100)
                        yield send_sse_event(f"Downloading: {mb_dl:.1f} / {mb_total:.1f} MB ({pct}%)")
                    else:
                        yield send_sse_event("Downloading visit data...")

                elif event_type == EVENT_RESULT:
                    result = event_data
                    break

            # Process result into child list
            if result:
                logger.info(f"[KMC] Got result with {len(result.rows) if hasattr(result, 'rows') else 0} rows")
                yield send_sse_event("Processing visits into children...")

                # Get FLW display names
                from commcare_connect.labs.analysis.data_access import get_flw_names_for_opportunity

                try:
                    flw_names = get_flw_names_for_opportunity(request, opportunity_id=opportunity_id)
                except Exception as e:
                    logger.warning(f"Failed to fetch FLW names: {e}")
                    flw_names = {}

                # Group by child_entity_id (Connect's linking field)
                children_dict = {}
                for row in result.rows:
                    child_id = row.entity_id or row.computed.get("child_entity_id")
                    if not child_id:
                        continue

                    if child_id not in children_dict:
                        children_dict[child_id] = {
                            "child_id": child_id,
                            "child_name": row.computed.get("child_name"),
                            "entity_name": row.entity_name or row.computed.get("entity_name"),
                            "flw_username": row.username,
                            "flw_display_name": flw_names.get(row.username, row.username),
                            "visits": [],
                        }

                    # Append visit for this child (outside the if block!)
                    children_dict[child_id]["visits"].append(
                        {
                            "weight": row.computed.get("weight"),  # Updated field name
                            "visit_date": row.computed.get("date")  # Updated field name
                            or (row.visit_date.isoformat() if row.visit_date else None),
                            "visit_number": row.computed.get("visit_number"),
                        }
                    )

                # Calculate aggregates for each child
                children_list = []
                for child_id, child_data in children_dict.items():
                    visits = child_data["visits"]
                    if not visits:
                        continue

                    # Sort by visit date
                    visits.sort(key=lambda v: v.get("visit_date") or "")

                    # Get first and last weights
                    weights = [v.get("weight") for v in visits if v.get("weight")]  # Updated field name
                    starting_weight = weights[0] if weights else None
                    current_weight = weights[-1] if weights else None

                    child_entry = {
                        "child_id": child_id,
                        "child_name": child_data["child_name"],
                        "entity_name": child_data["entity_name"],
                        "flw_username": child_data["flw_username"],
                        "flw_display_name": child_data["flw_display_name"],
                        "visit_count": len(visits),
                        "starting_weight": starting_weight,
                        "current_weight": current_weight,
                        "last_visit_date": visits[-1].get("visit_date") if visits else None,
                    }
                    logger.info(f"[KMC Stream] Adding child: {child_id[:20]}... with {len(visits)} visits")
                    children_list.append(child_entry)

                logger.info(f"[KMC] Processed {len(children_list)} children from {len(result.rows)} visits")

                yield send_sse_event(
                    "Complete",
                    data={
                        "children": children_list,
                        "opportunity_id": opportunity_id,
                        "from_cache": from_cache,
                    },
                )
            else:
                logger.warning("[KMC] No result from pipeline")
                yield send_sse_event("Error", error="No data returned from pipeline")

        except Exception as e:
            logger.error(f"[KMC] Stream failed: {e}", exc_info=True)
            yield send_sse_event("Error", error=f"Failed to load child data: {str(e)}")


class KMCImageProxyView(LoginRequiredMixin, View):
    """Proxy view to fetch images from Connect API with authentication."""

    def get(self, request, blob_id):
        """Download and return image from Connect."""
        opportunity_id = request.GET.get("opportunity_id")
        if not opportunity_id:
            return JsonResponse({"error": "opportunity_id required"}, status=400)

        # Get OAuth token from session
        labs_oauth = request.session.get("labs_oauth", {})
        access_token = labs_oauth.get("access_token")
        if not access_token:
            return JsonResponse({"error": "Not authenticated"}, status=401)

        # Fetch image from Connect
        production_url = settings.CONNECT_PRODUCTION_URL.rstrip("/")
        url = f"{production_url}/export/opportunity/{opportunity_id}/image/"

        try:
            with httpx.Client() as client:
                response = client.get(
                    url,
                    params={"blob_id": blob_id},
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=30.0,
                )
                response.raise_for_status()

                # Get content type from BlobMeta if available
                try:
                    blob_meta = BlobMeta.objects.get(blob_id=blob_id)
                    content_type = blob_meta.content_type or "image/jpeg"
                except BlobMeta.DoesNotExist:
                    content_type = "image/jpeg"

                return HttpResponse(response.content, content_type=content_type)

        except httpx.HTTPError as e:
            logging.error(f"[KMC] Failed to fetch image {blob_id}: {e}")
            return JsonResponse({"error": "Failed to fetch image"}, status=502)
