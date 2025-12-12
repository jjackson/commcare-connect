"""
Views for Labs Data Explorer
"""

import json
import logging
from collections.abc import Generator

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView
from django_tables2 import SingleTableView

from commcare_connect.labs.analysis.pipeline import AnalysisPipeline
from commcare_connect.labs.analysis.sse_streaming import AnalysisPipelineSSEMixin, BaseSSEStreamView, send_sse_event
from commcare_connect.labs.explorer.analysis_config import VISIT_INSPECTOR_CONFIG
from commcare_connect.labs.explorer.data_access import RecordExplorerDataAccess
from commcare_connect.labs.explorer.forms import (
    RecordEditForm,
    RecordFilterForm,
    RecordUploadForm,
    VisitInspectorFilterForm,
)
from commcare_connect.labs.explorer.sql_validator import build_safe_query
from commcare_connect.labs.explorer.tables import LabsRecordTable
from commcare_connect.labs.explorer.utils import (
    export_records_to_json,
    filter_records_by_date,
    format_json,
    generate_export_filename,
    parse_date_range,
    validate_import_data,
)

logger = logging.getLogger(__name__)


class ExplorerIndexView(LoginRequiredMixin, TemplateView):
    """
    Landing page for Labs Explorer.

    Shows cards for Labs Record and Visit Inspector.
    """

    template_name = "labs/explorer/index.html"


class RecordListView(LoginRequiredMixin, SingleTableView):
    """Main list view for browsing LabsRecord data."""

    table_class = LabsRecordTable
    template_name = "labs/explorer/list.html"
    paginate_by = 25
    _all_records_cache = None  # Cache for all unfiltered records

    def _get_all_records_once(self):
        """Get all records from API once and cache them."""
        if self._all_records_cache is not None:
            return self._all_records_cache

        # Check for context - API requires at least one of org/program/opp
        labs_context = getattr(self.request, "labs_context", {})
        if (
            not labs_context.get("opportunity_id")
            and not labs_context.get("program_id")
            and not labs_context.get("organization_id")
        ):
            logger.warning("No labs context selected")
            return []

        # Fetch all records once (no filters - we'll filter in Python)
        try:
            data_access = RecordExplorerDataAccess(request=self.request)
            try:
                self._all_records_cache = data_access.get_all_records()
            finally:
                data_access.close()
        except Exception as e:
            logger.error(f"Failed to get records: {e}")
            messages.error(self.request, f"Failed to load records: {e}")
            self._all_records_cache = []

        return self._all_records_cache

    def get_queryset(self):
        """Get filtered records from cached data."""
        # Get all records (cached)
        all_records = self._get_all_records_once()
        if not all_records:
            return []

        # Get filter parameters
        experiment = self.request.GET.get("experiment", "")
        type_filter = self.request.GET.get("type", "")
        username = self.request.GET.get("username", "")
        date_start = self.request.GET.get("date_created_start", "")
        date_end = self.request.GET.get("date_created_end", "")

        # Filter records in Python
        filtered_records = all_records

        if experiment:
            filtered_records = [r for r in filtered_records if r.experiment == experiment]
        if type_filter:
            filtered_records = [r for r in filtered_records if r.type == type_filter]
        if username:
            filtered_records = [r for r in filtered_records if r.username == username]

        # Apply date filtering
        if date_start or date_end:
            start_date, end_date = parse_date_range(date_start, date_end)
            filtered_records = filter_records_by_date(filtered_records, start_date, end_date, "date_created")

        # Sort by id descending (most recent records first)
        return sorted(filtered_records, key=lambda x: x.id, reverse=True)

    def get_context_data(self, **kwargs):
        """Add filter form and other context."""
        context = super().get_context_data(**kwargs)

        # Check for context
        labs_context = getattr(self.request, "labs_context", {})
        context["has_context"] = bool(
            labs_context.get("opportunity_id") or labs_context.get("program_id") or labs_context.get("organization_id")
        )

        # Check for OAuth token
        labs_oauth = self.request.session.get("labs_oauth", {})
        context["has_connect_token"] = bool(labs_oauth.get("access_token"))

        # Get distinct values for filter choices from cached records
        experiment_choices = []
        type_choices = []
        if context["has_context"] and context["has_connect_token"]:
            try:
                # Use cached records to get distinct values (no extra API call)
                all_records = self._get_all_records_once()
                experiment_choices = sorted(list({r.experiment for r in all_records if r.experiment}))
                type_choices = sorted(list({r.type for r in all_records if r.type}))
            except Exception as e:
                logger.error(f"Failed to get distinct values: {e}")

        # Create filter form with choices
        context["filter_form"] = RecordFilterForm(
            data=self.request.GET,
            experiment_choices=experiment_choices,
            type_choices=type_choices,
        )

        return context


class RecordEditView(LoginRequiredMixin, TemplateView):
    """Dedicated page for editing a record's JSON data."""

    template_name = "labs/explorer/edit.html"

    def get_context_data(self, **kwargs):
        """Load record and create edit form."""
        context = super().get_context_data(**kwargs)
        record_id = kwargs.get("pk")

        # Get record from API
        try:
            data_access = RecordExplorerDataAccess(request=self.request)
            try:
                record = data_access.get_record_by_id(record_id)
                if not record:
                    messages.error(self.request, f"Record {record_id} not found")
                    return context

                context["record"] = record

                # Create form with current data
                if self.request.method == "GET":
                    form = RecordEditForm(initial={"data": format_json(record.data)})
                    context["form"] = form
            finally:
                data_access.close()
        except Exception as e:
            logger.error(f"Failed to load record: {e}")
            messages.error(self.request, f"Failed to load record: {e}")

        return context

    def post(self, request, *args, **kwargs):
        """Handle form submission to update record."""
        record_id = kwargs.get("pk")
        form = RecordEditForm(data=request.POST)

        if form.is_valid():
            # Get updated data from form
            new_data = form.cleaned_data["data"]

            # Update record via API
            try:
                data_access = RecordExplorerDataAccess(request=request)
                try:
                    data_access.update_record(
                        record_id=record_id,
                        data=new_data,
                    )
                    messages.success(request, f"Record {record_id} updated successfully")
                    return redirect(reverse("explorer:list"))
                finally:
                    data_access.close()
            except Exception as e:
                logger.error(f"Failed to update record: {e}")
                messages.error(request, f"Failed to update record: {e}")

        # If validation failed or update failed, show form with errors
        context = self.get_context_data(**kwargs)
        context["form"] = form
        return render(request, self.template_name, context)


class DownloadRecordsView(LoginRequiredMixin, View):
    """Download records as JSON file."""

    def get(self, request):
        """Handle download request."""
        # Get selected record IDs or download all filtered
        selected_ids = request.GET.getlist("selected_ids")

        # Get filter parameters
        experiment = request.GET.get("experiment", "")
        type_filter = request.GET.get("type", "")
        username = request.GET.get("username", "")
        date_start = request.GET.get("date_created_start", "")
        date_end = request.GET.get("date_created_end", "")

        try:
            data_access = RecordExplorerDataAccess(request=request)
            try:
                # Get records based on filters or selected IDs
                if selected_ids:
                    # Download only selected records
                    all_records = data_access.get_all_records()
                    records = [r for r in all_records if str(r.id) in selected_ids]
                else:
                    # Download all filtered records
                    records = data_access.get_all_records(
                        experiment=experiment if experiment else None,
                        type=type_filter if type_filter else None,
                        username=username if username else None,
                    )

                    # Apply date filtering
                    if date_start or date_end:
                        start_date, end_date = parse_date_range(date_start, date_end)
                        records = filter_records_by_date(records, start_date, end_date, "date_created")

                # Export to JSON
                json_content = export_records_to_json(records)
                filename = generate_export_filename(experiment if experiment else None)

                # Create response
                response = HttpResponse(json_content, content_type="application/json")
                response["Content-Disposition"] = f'attachment; filename="{filename}"'
                return response
            finally:
                data_access.close()
        except Exception as e:
            logger.error(f"Failed to download records: {e}")
            messages.error(request, f"Failed to download records: {e}")
            return redirect(reverse("explorer:list"))


class UploadRecordsView(LoginRequiredMixin, View):
    """Upload/import records from JSON file."""

    def post(self, request):
        """Handle file upload."""
        form = RecordUploadForm(data=request.POST, files=request.FILES)

        if form.is_valid():
            # Get parsed data from form
            records_data = form.parsed_data

            # Validate structure
            is_valid, error, validated_data = validate_import_data(json.dumps(records_data))
            if not is_valid:
                messages.error(request, f"Invalid data: {error}")
                return redirect(reverse("explorer:list"))

            # Import records
            try:
                data_access = RecordExplorerDataAccess(request=request)
                try:
                    created_records = data_access.bulk_create_records(validated_data)
                    messages.success(request, f"Successfully imported {len(created_records)} record(s)")
                finally:
                    data_access.close()
            except Exception as e:
                logger.error(f"Failed to import records: {e}")
                messages.error(request, f"Failed to import records: {e}")
        else:
            # Show form errors
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")

        return redirect(reverse("explorer:list"))


class DeleteRecordsView(LoginRequiredMixin, View):
    """Delete selected records."""

    def post(self, request):
        """Handle delete request."""
        # Get selected record IDs from POST data
        selected_ids = request.POST.getlist("selected_ids")

        if not selected_ids:
            messages.error(request, "No records selected for deletion")
            return redirect(reverse("explorer:list"))

        # Convert to integers
        try:
            record_ids = [int(id_str) for id_str in selected_ids]
        except ValueError:
            messages.error(request, "Invalid record IDs")
            return redirect(reverse("explorer:list"))

        # Delete records via API
        try:
            data_access = RecordExplorerDataAccess(request=request)
            try:
                data_access.delete_records(record_ids)
                messages.success(request, f"Successfully deleted {len(record_ids)} record(s)")
            finally:
                data_access.close()
        except Exception as e:
            logger.error(f"Failed to delete records: {e}")
            messages.error(request, f"Failed to delete records: {e}")

        return redirect(reverse("explorer:list"))


class VisitInspectorView(LoginRequiredMixin, TemplateView):
    """Visit Inspector page for downloading and querying raw visit data."""

    template_name = "labs/explorer/visit_inspector.html"

    def get_context_data(self, **kwargs):
        """Provide initial page context - actual data loading happens via SSE."""
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
        context["stream_api_url"] = reverse("explorer:visit_inspector_stream")

        # Create filter form
        context["filter_form"] = VisitInspectorFilterForm()

        return context


class VisitInspectorQueryView(LoginRequiredMixin, View):
    """Handle SQL query execution for visit filtering."""

    def post(self, request):
        """Execute user's SQL WHERE clause and return results."""
        form = VisitInspectorFilterForm(data=request.POST)

        if not form.is_valid():
            # Return errors as JSON
            errors = []
            for field, field_errors in form.errors.items():
                for error in field_errors:
                    errors.append(f"{field}: {error}")
            return JsonResponse({"success": False, "errors": errors}, status=400)

        # Get validated WHERE clause
        where_clause = form.cleaned_data["where_clause"]

        # Get opportunity_id from context
        labs_context = getattr(request, "labs_context", {})
        opportunity_id = labs_context.get("opportunity_id")

        if not opportunity_id:
            return JsonResponse({"success": False, "errors": ["No opportunity selected"]}, status=400)

        try:
            # Build safe query
            query, params = build_safe_query(opportunity_id, where_clause, limit=1000)

            # Execute query in read-only mode
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()

            # Convert to list of dicts
            results = []
            for row in rows:
                row_dict = {}
                for col, val in zip(columns, row):
                    # Convert date/datetime to string for JSON serialization
                    if hasattr(val, "isoformat"):
                        row_dict[col] = val.isoformat()
                    else:
                        row_dict[col] = val
                results.append(row_dict)

            logger.info(f"[VisitInspector] Query returned {len(results)} results")

            return JsonResponse(
                {
                    "success": True,
                    "count": len(results),
                    "results": results,
                }
            )

        except Exception as e:
            logger.error(f"[VisitInspector] Query failed: {e}")
            return JsonResponse({"success": False, "errors": [f"Query failed: {str(e)}"]}, status=500)


class VisitViewView(LoginRequiredMixin, TemplateView):
    """View a single visit's data in a formatted page."""

    template_name = "labs/explorer/visit_view.html"

    def get_context_data(self, **kwargs):
        """Load visit and display in formatted view."""
        context = super().get_context_data(**kwargs)
        visit_id = kwargs.get("visit_id")

        # Get opportunity_id from context
        labs_context = getattr(self.request, "labs_context", {})
        opportunity_id = labs_context.get("opportunity_id")

        if not opportunity_id:
            messages.error(self.request, "No opportunity selected")
            return context

        try:
            # Query the SQL cache for this visit
            query = """
                SELECT visit_id, username, visit_date, status, deliver_unit,
                       entity_id, entity_name, flagged, form_json
                FROM labs_raw_visit_cache
                WHERE opportunity_id = %s AND visit_id = %s
                LIMIT 1
            """

            with connection.cursor() as cursor:
                cursor.execute(query, [opportunity_id, visit_id])
                row = cursor.fetchone()

            if not row:
                messages.error(self.request, f"Visit {visit_id} not found")
                return context

            # Extract data
            context["visit_id"] = row[0]
            context["username"] = row[1]
            context["visit_date"] = row[2]
            context["status"] = row[3]
            context["deliver_unit"] = row[4]
            context["entity_id"] = row[5]
            context["entity_name"] = row[6]
            context["flagged"] = row[7]
            form_json = row[8]

            # Format JSON for display
            if isinstance(form_json, str):
                form_json = json.loads(form_json)

            context["visit_json"] = json.dumps(form_json, indent=2, ensure_ascii=False, separators=(",", ": "))
            context["visit_data"] = True

            logger.info(f"[VisitInspector] Viewing visit {visit_id}")

        except Exception as e:
            logger.error(f"[VisitInspector] Failed to load visit {visit_id}: {e}")
            messages.error(self.request, f"Failed to load visit: {e}")
            context["visit_data"] = False

        return context


class DownloadVisitView(LoginRequiredMixin, View):
    """Download a single visit's form_json as a .json file."""

    def get(self, request, visit_id):
        """Retrieve visit and return as downloadable JSON."""
        # Get opportunity_id from context
        labs_context = getattr(request, "labs_context", {})
        opportunity_id = labs_context.get("opportunity_id")

        if not opportunity_id:
            messages.error(request, "No opportunity selected")
            return redirect(reverse("explorer:visit_inspector"))

        try:
            # Query the SQL cache for this visit
            query = """
                SELECT visit_id, username, visit_date, status, form_json
                FROM labs_raw_visit_cache
                WHERE opportunity_id = %s AND visit_id = %s
                LIMIT 1
            """

            with connection.cursor() as cursor:
                cursor.execute(query, [opportunity_id, visit_id])
                row = cursor.fetchone()

            if not row:
                messages.error(request, f"Visit {visit_id} not found")
                return redirect(reverse("explorer:visit_inspector"))

            # Extract form_json (5th column)
            form_json = row[4]

            # Check if form_json is already a dict or needs parsing
            if isinstance(form_json, str):
                # If it's a string, parse it first
                form_json = json.loads(form_json)

            # Format as pretty JSON with minimal escaping
            json_content = json.dumps(form_json, indent=2, ensure_ascii=False, separators=(",", ": "))

            # Create response with download header and UTF-8 encoding
            response = HttpResponse(json_content, content_type="application/json; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="opp{opportunity_id}-visit_{visit_id}.json"'

            logger.info(f"[VisitInspector] Downloaded visit {visit_id}")
            return response

        except Exception as e:
            logger.error(f"[VisitInspector] Failed to download visit {visit_id}: {e}")
            messages.error(request, f"Failed to download visit: {e}")
            return redirect(reverse("explorer:visit_inspector"))


class VisitInspectorStreamView(AnalysisPipelineSSEMixin, BaseSSEStreamView):
    """
    SSE streaming endpoint for Visit Inspector with real-time progress.

    Uses the base SSE infrastructure to stream analysis pipeline events.
    """

    def stream_data(self, request) -> Generator[str, None, None]:
        """Stream visit data loading progress via SSE."""
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

            # Initial status
            yield send_sse_event("Checking cache...")

            # Run analysis pipeline with streaming
            pipeline = AnalysisPipeline(request)
            pipeline_stream = pipeline.stream_analysis(VISIT_INSPECTOR_CONFIG)

            # Use mixin to convert pipeline events to SSE
            result = None
            from_cache = False

            for sse_event, cache_flag in self.stream_pipeline_events(pipeline_stream):
                from_cache = cache_flag
                yield sse_event

                # Check if we got a result (mixin returns it)
                if cache_flag is not False:  # This means we've processed all events
                    result = sse_event  # Actually need to get result differently
                    break

            # Alternative: manually process to get result
            result = None
            from_cache = False
            pipeline_stream = pipeline.stream_analysis(VISIT_INSPECTOR_CONFIG)

            for event_type, event_data in pipeline_stream:
                if event_type == "status":
                    message = event_data.get("message", "Processing...")
                    from_cache = from_cache or "cache" in message.lower()
                    yield send_sse_event(message)

                elif event_type == "download":
                    bytes_dl = event_data.get("bytes", 0)
                    total_bytes = event_data.get("total", 0)
                    if total_bytes > 0:
                        mb_dl = bytes_dl / (1024 * 1024)
                        mb_total = total_bytes / (1024 * 1024)
                        pct = int(bytes_dl / total_bytes * 100)
                        yield send_sse_event(f"Downloading: {mb_dl:.1f} / {mb_total:.1f} MB ({pct}%)")
                    else:
                        yield send_sse_event("Downloading visit data...")

                elif event_type == "result":
                    result = event_data
                    break

            # Build completion response
            if result:
                visit_count = len(result.rows) if hasattr(result, "rows") else 0
                logger.info(f"[VisitInspector] Cached {visit_count} visits for opportunity {opportunity_id}")

                yield send_sse_event(
                    "Complete",
                    data={
                        "visit_count": visit_count,
                        "opportunity_id": opportunity_id,
                        "from_cache": from_cache,
                    },
                )

        except Exception as e:
            logger.error(f"[VisitInspector] Stream failed: {e}")
            yield send_sse_event("Error", error=f"Failed to load visit data: {str(e)}")
