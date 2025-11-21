"""
Views for Labs Data Explorer
"""

import json
import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView
from django_tables2 import SingleTableView

from commcare_connect.labs.explorer.data_access import RecordExplorerDataAccess
from commcare_connect.labs.explorer.forms import RecordEditForm, RecordFilterForm, RecordUploadForm
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


class RecordListView(LoginRequiredMixin, SingleTableView):
    """Main list view for browsing LabsRecord data."""

    table_class = LabsRecordTable
    template_name = "labs/explorer/list.html"
    paginate_by = 25

    def get_queryset(self):
        """Get filtered records from API."""
        # Check for context - API requires at least one of org/program/opp
        labs_context = getattr(self.request, "labs_context", {})
        if (
            not labs_context.get("opportunity_id")
            and not labs_context.get("program_id")
            and not labs_context.get("organization_id")
        ):
            logger.warning("No labs context selected")
            return []

        # Get filter parameters
        experiment = self.request.GET.get("experiment", "")
        type_filter = self.request.GET.get("type", "")
        username = self.request.GET.get("username", "")
        date_start = self.request.GET.get("date_created_start", "")
        date_end = self.request.GET.get("date_created_end", "")

        # Get records from API
        try:
            data_access = RecordExplorerDataAccess(request=self.request)
            try:
                records = data_access.get_all_records(
                    experiment=experiment if experiment else None,
                    type=type_filter if type_filter else None,
                    username=username if username else None,
                )

                # Apply date filtering
                if date_start or date_end:
                    start_date, end_date = parse_date_range(date_start, date_end)
                    records = filter_records_by_date(records, start_date, end_date, "date_created")

                # Sort by date_created descending
                return sorted(records, key=lambda x: x.date_created or "", reverse=True)
            finally:
                data_access.close()
        except Exception as e:
            logger.error(f"Failed to get records: {e}")
            messages.error(self.request, f"Failed to load records: {e}")
            return []

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

        # Get distinct values for filter choices (only if we have both context and token)
        experiment_choices = []
        type_choices = []
        if context["has_context"] and context["has_connect_token"]:
            try:
                data_access = RecordExplorerDataAccess(request=self.request)
                try:
                    experiment_choices = data_access.get_distinct_values("experiment")
                    type_choices = data_access.get_distinct_values("type")
                finally:
                    data_access.close()
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
