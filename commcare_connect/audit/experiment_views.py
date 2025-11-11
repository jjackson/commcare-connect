"""
Experiment-based Audit Views.

These views use the ExperimentRecord-based data access layer instead of
local Django models. They fetch data dynamically from Connect APIs and
store audit state in ExperimentRecords.

Templates are reused from the existing audit views for consistency.
"""

import json

import django_tables2 as tables
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, HttpResponse, JsonResponse
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import DetailView, TemplateView, View
from django_tables2 import SingleTableView

from commcare_connect.audit.data_access import AuditDataAccess
from commcare_connect.audit.experiment_models import AuditSessionRecord


class AuditTable(tables.Table):
    """Simple table for displaying audit sessions"""

    id = tables.Column(verbose_name="ID")
    title = tables.Column(verbose_name="Title")
    status = tables.Column(verbose_name="Status")
    date_created = tables.DateTimeColumn(verbose_name="Created", format="Y-m-d H:i")

    class Meta:
        model = AuditSessionRecord
        template_name = "django_tables2/bootstrap4.html"
        fields = ("id", "title", "status", "date_created")
        attrs = {"class": "table table-striped"}


class ExperimentAuditCreateView(LoginRequiredMixin, TemplateView):
    """Audit creation wizard interface (experiment-based)"""

    template_name = "audit/audit_creation_wizard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Create New Audit Session"
        return context


class ExperimentAuditListView(LoginRequiredMixin, SingleTableView):
    """List all experiment-based audit sessions"""

    model = AuditSessionRecord
    table_class = AuditTable
    template_name = "audit/audit_session_list.html"
    paginate_by = 20

    def get_queryset(self):
        # Get AuditSessionRecords from ExperimentRecords
        data_access = AuditDataAccess(request=self.request)
        try:
            return data_access.get_audit_sessions().order_by("-date_created")
        finally:
            data_access.close()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Check for Connect OAuth token
        from django.conf import settings

        # In labs mode, OAuth token is in session
        if getattr(settings, "IS_LABS_ENVIRONMENT", False):
            labs_oauth = self.request.session.get("labs_oauth", {})
            context["has_connect_token"] = bool(labs_oauth.get("access_token"))
            if labs_oauth.get("expires_at"):
                import datetime

                from django.utils import timezone

                context["token_expires_at"] = datetime.datetime.fromtimestamp(
                    labs_oauth["expires_at"], tz=timezone.get_current_timezone()
                )
            else:
                context["token_expires_at"] = None
        else:
            # Normal mode: check database for SocialAccount
            from allauth.socialaccount.models import SocialAccount, SocialToken

            try:
                social_account = SocialAccount.objects.get(user=self.request.user, provider="connect")
                social_token = SocialToken.objects.get(account=social_account)
                context["has_connect_token"] = True
                context["token_expires_at"] = social_token.expires_at
            except (SocialAccount.DoesNotExist, SocialToken.DoesNotExist):
                context["has_connect_token"] = False
                context["token_expires_at"] = None

        return context


class ExperimentAuditDetailView(LoginRequiredMixin, DetailView):
    """Main audit interface for reviewing visits one at a time (experiment-based)"""

    model = AuditSessionRecord
    template_name = "audit/audit_session_detail.html"
    context_object_name = "session"

    def get_queryset(self):
        # Get AuditSessionRecords from ExperimentRecords
        return AuditSessionRecord.objects.filter(experiment="audit", type="AuditSession")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.get_object()

        # Initialize data access
        data_access = AuditDataAccess(request=self.request)

        try:
            # Get visit IDs from session
            visit_ids = session.visit_ids
            total_visits = len(visit_ids)

            # Get current visit index from URL parameter (1-based, convert to 0-based)
            visit_index = int(self.request.GET.get("visit", 1)) - 1

            # Ensure visit_index is within bounds
            if visit_index < 0:
                visit_index = 0
            elif visit_index >= total_visits:
                visit_index = max(0, total_visits - 1)

            # Get current visit
            current_visit = None
            current_visit_images = []

            if total_visits > 0:
                current_visit_id = visit_ids[visit_index]

                # Fetch visit data from Connect API
                # Use opportunity_id from session if available
                opportunity_id = session.opportunity_id

                visit_data = data_access.get_visit_data(current_visit_id, opportunity_id=opportunity_id)

                if visit_data:
                    current_visit = visit_data

                    # Get blob metadata from CommCare
                    # Get cc_domain from opportunity details
                    opp_details = data_access.get_opportunity_details(opportunity_id)
                    cc_domain = opp_details.get("cc_domain") if opp_details else None

                    if cc_domain and visit_data.get("xform_id"):
                        try:
                            blob_metadata = data_access.get_blob_metadata_for_visit(visit_data["xform_id"], cc_domain)

                            # Get existing assessments from session JSON
                            assessments = session.get_assessments(current_visit_id)

                            # Build images list for template
                            for blob_id, blob_info in blob_metadata.items():
                                assessment = assessments.get(blob_id, {})
                                image_data = {
                                    "blob_id": blob_id,
                                    "question_id": blob_info.get("question_id"),
                                    "url": (
                                        f"/audit/experiment/image/{blob_id}/"
                                        f"?xform_id={visit_data['xform_id']}&domain={cc_domain}"
                                    ),
                                    "result": assessment.get("result"),
                                    "notes": assessment.get("notes", ""),
                                    "name": blob_info.get("filename"),
                                }
                                current_visit_images.append(image_data)

                        except Exception as e:
                            # Log error but continue
                            print(f"[WARNING] Could not fetch blob metadata: {e}")

                    # Get visit result from session JSON
                    visit_result = session.get_visit_result(current_visit_id)
                    if visit_result:
                        current_visit["audit_result"] = visit_result

            # Progress information
            progress_stats = session.get_progress_stats()

            context.update(
                {
                    "current_visit": current_visit,
                    "current_visit_images": current_visit_images,
                    "visit_index": visit_index,
                    "total_visits": total_visits,
                    "audited_count": progress_stats["assessed"],
                    "pending_count": progress_stats["total"] - progress_stats["assessed"],
                    "progress_percentage": progress_stats["percentage"],
                    "has_previous": visit_index > 0,
                    "has_next": visit_index < total_visits - 1,
                    "previous_index": visit_index - 1 if visit_index > 0 else 0,
                    "next_index": visit_index + 1 if visit_index < total_visits - 1 else visit_index,
                }
            )

        finally:
            data_access.close()

        return context


class ExperimentAuditResultUpdateView(LoginRequiredMixin, View):
    """AJAX endpoint for updating audit results (experiment-based)"""

    def post(self, request, session_id):
        try:
            # Initialize data access
            data_access = AuditDataAccess(request=request)

            try:
                # Get session
                session = data_access.get_audit_session(session_id)
                if not session:
                    return JsonResponse({"error": "Session not found"}, status=404)

                visit_id = int(request.POST.get("visit_id"))
                result = request.POST.get("result")
                notes = request.POST.get("notes", "")
                auto_advance = request.POST.get("auto_advance", "true") == "true"
                current_index = int(request.POST.get("current_index", 0))

                if not visit_id or result not in ["pass", "fail"]:
                    return JsonResponse({"error": "Invalid data"}, status=400)

                # Get xform_id and other data from visit
                visit_data = data_access.get_visit_data(visit_id, opportunity_id=session.opportunity_id)
                if not visit_data:
                    return JsonResponse({"error": "Visit not found"}, status=404)

                # Update visit result in session
                session.set_visit_result(
                    visit_id=visit_id,
                    xform_id=visit_data["xform_id"],
                    result=result,
                    notes=notes,
                    user_id=visit_data.get("user_id", 0),
                    opportunity_id=visit_data.get("opportunity_id", session.opportunity_id),
                )

                # Save session
                session = data_access.save_audit_session(session)

                # Calculate updated progress
                total_visits = len(session.visit_ids)
                audited_count = len([v for v in session.visit_results.values() if v.get("result")])
                progress_percentage = round((audited_count / total_visits) * 100, 1) if total_visits > 0 else 0

                # Determine next visit index for auto-advance
                next_index = current_index + 1 if auto_advance and current_index + 1 < total_visits else current_index

                return JsonResponse(
                    {
                        "success": True,
                        "progress_percentage": progress_percentage,
                        "audited_count": audited_count,
                        "total_visits": total_visits,
                        "next_index": next_index,
                        "should_advance": auto_advance and next_index != current_index,
                    }
                )

            finally:
                data_access.close()

        except Exception as e:
            import traceback

            print(f"[ERROR] {traceback.format_exc()}")
            return JsonResponse({"error": str(e)}, status=500)


class ExperimentAssessmentUpdateView(LoginRequiredMixin, View):
    """AJAX endpoint for updating individual image assessments (experiment-based)"""

    def post(self, request, session_id):
        try:
            # Initialize data access
            data_access = AuditDataAccess(request=request)

            try:
                # Get session
                session = data_access.get_audit_session(session_id)
                if not session:
                    return JsonResponse({"error": "Session not found"}, status=404)

                visit_id = int(request.POST.get("visit_id"))
                blob_id = request.POST.get("blob_id")
                question_id = request.POST.get("question_id", "")
                result = request.POST.get("result")
                notes = request.POST.get("notes", "")

                if not visit_id or not blob_id or result not in ["pass", "fail"]:
                    return JsonResponse({"error": "Invalid data"}, status=400)

                # Update assessment in session
                session.set_assessment(
                    visit_id=visit_id, blob_id=blob_id, question_id=question_id, result=result, notes=notes
                )

                # Save session
                session = data_access.save_audit_session(session)

                # Calculate updated progress
                progress_stats = session.get_progress_stats()

                return JsonResponse(
                    {
                        "success": True,
                        "progress_percentage": progress_stats["percentage"],
                        "assessed_count": progress_stats["assessed"],
                        "total_assessments": progress_stats["total"],
                    }
                )

            finally:
                data_access.close()

        except Exception as e:
            import traceback

            print(f"[ERROR] {traceback.format_exc()}")
            return JsonResponse({"error": str(e)}, status=500)


class ExperimentAuditCompleteView(LoginRequiredMixin, View):
    """Complete an experiment-based audit session"""

    def post(self, request, session_id):
        try:
            # Initialize data access
            data_access = AuditDataAccess(request=request)

            try:
                # Get session
                session = data_access.get_audit_session(session_id)
                if not session:
                    return JsonResponse({"error": "Session not found"}, status=404)

                overall_result = request.POST.get("overall_result")
                notes = request.POST.get("notes", "")
                kpi_notes = request.POST.get("kpi_notes", "")

                if overall_result not in ["pass", "fail"]:
                    return JsonResponse({"error": "Invalid overall result"}, status=400)

                # Complete session
                session = data_access.complete_audit_session(
                    session=session, overall_result=overall_result, notes=notes, kpi_notes=kpi_notes
                )

                return JsonResponse({"success": True})

            finally:
                data_access.close()

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


class ExperimentAuditImageView(LoginRequiredMixin, View):
    """Serve audit visit images (experiment-based)"""

    def get(self, request, blob_id):
        try:
            # Get xform_id and domain from query params
            xform_id = request.GET.get("xform_id")
            domain = request.GET.get("domain")

            if not xform_id or not domain:
                return HttpResponse("Missing xform_id or domain", status=400)

            # Initialize data access
            data_access = AuditDataAccess(request=request)

            try:
                # Get blob metadata
                blob_metadata = data_access.get_blob_metadata_for_visit(xform_id, domain)

                if blob_id not in blob_metadata:
                    return HttpResponse(f"Blob {blob_id} not found in form", status=404)

                blob_info = blob_metadata[blob_id]
                blob_url = blob_info.get("url")

                if not blob_url:
                    return HttpResponse("Blob URL not found", status=404)

                # Download blob
                blob_content = data_access.download_blob(blob_url)

                # Return as file response
                content_type = blob_info.get("content_type", "image/jpeg")
                filename = blob_info.get("filename", blob_id)

                response = FileResponse(blob_content, content_type=content_type, filename=filename)
                return response

            finally:
                data_access.close()

        except Exception as e:
            import traceback

            print(f"[ERROR] {traceback.format_exc()}")
            return HttpResponse(f"Image not found: {e}", status=404)


class ExperimentAuditCreateAPIView(LoginRequiredMixin, View):
    """API endpoint for creating experiment-based audit sessions - synchronous"""

    def post(self, request):
        data_access = None
        try:
            data = json.loads(request.body)
            opportunity_ids = data.get("opportunities", [])
            criteria = data.get("criteria", {})

            if not opportunity_ids or not criteria:
                return JsonResponse({"error": "Missing required data"}, status=400)

            # Get auditor user ID
            auditor_id = request.user.id

            # Initialize data access
            data_access = AuditDataAccess(request=request)

            # Extract and normalize criteria
            audit_type = criteria.get("type", criteria.get("audit_type", "date_range"))

            # Map frontend camelCase to backend snake_case
            normalized_criteria = {
                "audit_type": audit_type,
                "start_date": criteria.get("startDate"),
                "end_date": criteria.get("endDate"),
                "count_per_flw": criteria.get("countPerFlw", 10),
                "count_per_opp": criteria.get("countPerOpp", 10),
                "count_across_all": criteria.get("countAcrossAll", 100),
                "sample_percentage": criteria.get("sample_percentage", criteria.get("samplePercentage", 100)),
                "selected_flw_user_ids": criteria.get("selected_flw_user_ids", []),
            }

            # Get visit IDs based on criteria
            visit_ids = data_access.get_visit_ids_for_audit(
                opportunity_ids=opportunity_ids, audit_type=audit_type, criteria=normalized_criteria
            )

            # Filter by selected FLW identifiers if provided
            # TODO: Check with team whether to use user_id or username as primary identifier
            # Currently using username as primary, with user_id fallback
            selected_flw_user_ids = normalized_criteria.get("selected_flw_user_ids", [])
            if selected_flw_user_ids and visit_ids:
                # Fetch visits and filter by username (or user_id as fallback)
                filtered_visit_ids = []
                for opp_id in opportunity_ids:
                    visits = data_access.get_visits_batch(visit_ids, opp_id)
                    filtered_visit_ids.extend(
                        [
                            v["id"]
                            for v in visits
                            if v.get("username") in selected_flw_user_ids or v.get("user_id") in selected_flw_user_ids
                        ]
                    )
                visit_ids = filtered_visit_ids

            if not visit_ids:
                return JsonResponse({"error": "No visits found matching criteria"}, status=400)

            # Create template
            template = data_access.create_audit_template(
                user_id=auditor_id,
                opportunity_ids=opportunity_ids,
                audit_type=audit_type,
                granularity=criteria.get("granularity", "combined"),
                criteria=criteria,
                preview_data=[],
            )

            # Create session
            session = data_access.create_audit_session(
                template_id=template.id,
                auditor_id=auditor_id,
                visit_ids=visit_ids,
                title=criteria.get("title", f"Audit {timezone.now().strftime('%Y-%m-%d')}"),
                tag=criteria.get("tag", ""),
                opportunity_id=opportunity_ids[0] if opportunity_ids else None,
            )

            # Determine redirect URL
            redirect_url = reverse_lazy("audit:session_detail", kwargs={"pk": session.pk})

            return JsonResponse(
                {
                    "success": True,
                    "redirect_url": str(redirect_url),
                    "session_id": session.id,
                    "stats": {"total_visits": len(visit_ids)},
                }
            )

        except Exception as e:
            import traceback

            print(f"[ERROR] {traceback.format_exc()}")
            return JsonResponse({"error": str(e)}, status=500)
        finally:
            if data_access:
                data_access.close()


class ExperimentOpportunitySearchAPIView(LoginRequiredMixin, View):
    """API endpoint for searching opportunities (experiment-based)"""

    def get(self, request):
        query = request.GET.get("q", "").strip()
        limit = int(request.GET.get("limit", 1000))  # Default to 1000, no max limit

        data_access = AuditDataAccess(request=request)
        try:
            opportunities = data_access.search_opportunities(query, limit)

            # Convert to JSON-serializable format
            opportunities_data = [
                {
                    "id": opp.get("id"),
                    "name": opp.get("name"),
                    "description": opp.get("description", ""),
                    "organization_name": opp.get("organization_name", ""),
                    "program_name": opp.get("program_name", ""),
                    "visit_count": opp.get("total_visits", 0),
                    "start_date": opp.get("start_date"),
                    "end_date": opp.get("end_date"),
                    "active": opp.get("active", True),
                    "is_test": opp.get("is_test", False),
                }
                for opp in opportunities
            ]

            return JsonResponse({"success": True, "opportunities": opportunities_data})

        except Exception as e:
            import traceback

            print(f"[ERROR] {traceback.format_exc()}")
            return JsonResponse({"success": False, "error": str(e), "opportunities": []}, status=500)
        finally:
            data_access.close()


class ExperimentAuditProgressAPIView(LoginRequiredMixin, View):
    """API endpoint for polling audit creation progress (experiment-based)

    Note: Progress tracking was removed with old service layer.
    This endpoint is kept for API compatibility but returns minimal data.
    """

    def get(self, request):
        task_id = request.GET.get("task_id")
        if not task_id:
            return JsonResponse({"error": "Missing task_id"}, status=400)

        # Return simple progress data (old ProgressTracker service was removed)
        return JsonResponse(
            {
                "task_id": task_id,
                "status": "complete",
                "progress": 100,
                "message": "Progress tracking unavailable in experiment implementation",
            }
        )

    def delete(self, request):
        """Cancel an in-progress audit creation"""
        task_id = request.GET.get("task_id")
        if not task_id:
            return JsonResponse({"error": "Missing task_id"}, status=400)

        # Old ProgressTracker was removed - return success for compatibility
        return JsonResponse({"success": True, "message": "Cancellation not supported in experiment implementation"})


class ExperimentAuditPreviewAPIView(LoginRequiredMixin, View):
    """API endpoint for previewing audit sessions (experiment-based) - synchronous"""

    def post(self, request):
        data_access = None
        try:
            data = json.loads(request.body)
            opportunity_ids = data.get("opportunities", [])
            criteria = data.get("criteria", {})

            if not opportunity_ids or not criteria:
                return JsonResponse({"error": "Missing required data"}, status=400)

            # Initialize data access
            data_access = AuditDataAccess(request=request)

            # Extract and normalize criteria
            audit_type = criteria.get("type", criteria.get("audit_type", "date_range"))

            # Map frontend camelCase to backend snake_case
            normalized_criteria = {
                "audit_type": audit_type,
                "start_date": criteria.get("startDate"),
                "end_date": criteria.get("endDate"),
                "count_per_flw": criteria.get("countPerFlw", 10),
                "count_per_opp": criteria.get("countPerOpp", 10),
                "count_across_all": criteria.get("countAcrossAll", 100),
                "sample_percentage": criteria.get("sample_percentage", criteria.get("samplePercentage", 100)),
            }

            # Get visit IDs based on criteria
            visit_ids = data_access.get_visit_ids_for_audit(
                opportunity_ids=opportunity_ids, audit_type=audit_type, criteria=normalized_criteria
            )

            # Fetch detailed visit data and group by FLW
            # TODO: Check with team whether to use user_id or username as primary identifier
            # Currently using username since it's unique and always populated
            flw_data = {}
            for opp_id in opportunity_ids:
                visits = data_access.get_visits_batch(visit_ids, opp_id)

                for visit in visits:
                    # Use username as primary identifier
                    username = visit.get("username")
                    if not username:
                        continue

                    if username not in flw_data:
                        flw_data[username] = {
                            "user_id": visit.get("user_id"),  # May be None
                            "name": username,
                            "connect_id": username,
                            "visit_count": 0,
                            "visits": [],
                            "opportunity_id": opp_id,
                            "opportunity_name": visit.get("opportunity_name", ""),
                        }

                    flw_data[username]["visit_count"] += 1
                    flw_data[username]["visits"].append(
                        {
                            "id": visit.get("id"),
                            "visit_date": visit.get("visit_date"),
                        }
                    )

            # Calculate date ranges and format for frontend
            preview_results = []
            for username, flw in flw_data.items():
                # Sort visits by date
                visits = sorted(flw["visits"], key=lambda v: v["visit_date"])
                earliest = visits[0]["visit_date"] if visits else None
                latest = visits[-1]["visit_date"] if visits else None

                preview_results.append(
                    {
                        "user_id": flw["user_id"],  # May be None
                        "username": username,
                        "name": flw["name"],
                        "connect_id": flw["connect_id"],
                        "visit_count": flw["visit_count"],
                        "earliest_visit": earliest,
                        "latest_visit": latest,
                        "opportunity_id": flw["opportunity_id"],
                        "opportunity_name": flw["opportunity_name"],
                        "prior_audit_tags": [],  # TODO: Fetch from audit history
                    }
                )

            return JsonResponse(
                {
                    "success": True,
                    "preview": {
                        "total_visits": len(visit_ids),
                        "total_flws": len(preview_results),
                        "flws": preview_results,
                    },
                }
            )

        except Exception as e:
            import traceback

            print(f"[ERROR] {traceback.format_exc()}")
            return JsonResponse({"error": str(e)}, status=500)
        finally:
            if data_access:
                data_access.close()
