"""
Experiment-based Audit Views.

These views use the ExperimentRecord-based data access layer instead of
local Django models. They fetch data dynamically from Connect APIs and
store audit state in ExperimentRecords.

Templates are reused from the existing audit views for consistency.
"""

import json
from collections import defaultdict

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, HttpResponse, JsonResponse
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.generic import DetailView, TemplateView, View
from django_tables2 import SingleTableView

from commcare_connect.audit.data_access import AuditDataAccess
from commcare_connect.audit.models import AuditSessionRecord
from commcare_connect.audit.tables import AuditTable


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
        # Get AuditSessionRecords from API (returns list, not QuerySet)
        data_access = AuditDataAccess(request=self.request)
        try:
            sessions = data_access.get_audit_sessions()
            # Sort by date_created descending (API returns list, not QuerySet)
            return sorted(sessions, key=lambda x: x.date_created or "", reverse=True)
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

            # Check for CommCare OAuth token
            commcare_oauth = self.request.session.get("commcare_oauth", {})
            context["has_commcare_token"] = bool(commcare_oauth.get("access_token"))
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

            # In normal mode, CommCare OAuth not supported yet
            context["has_commcare_token"] = False

        return context


class ExperimentAuditDetailView(LoginRequiredMixin, DetailView):
    """Main audit interface for reviewing visits one at a time (experiment-based)"""

    model = AuditSessionRecord
    template_name = "audit/audit_session_detail.html"
    context_object_name = "session"

    def get_object(self, queryset=None):
        """Fetch session from API instead of using Django ORM."""
        session_id = self.kwargs.get("pk")
        data_access = AuditDataAccess(request=self.request)
        try:
            # Try to find the session across all opportunities the user has access to
            session = data_access.get_audit_session(session_id, try_multiple_opportunities=True)
            if not session:
                from django.http import Http404

                raise Http404(f"Session {session_id} not found")
            return session
        finally:
            data_access.close()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.get_object()

        # Initialize data access with session's opportunity ID if available
        data_access = AuditDataAccess(
            opportunity_id=session.opportunity_id if session.opportunity_id else None, request=self.request
        )

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


class ExperimentBulkAssessmentView(LoginRequiredMixin, DetailView):
    """Bulk assessment interface for experiment-based audit sessions."""

    model = AuditSessionRecord
    template_name = "audit/bulk_assessment.html"
    context_object_name = "session"

    def get_object(self, queryset=None):
        """Fetch session from API instead of using Django ORM."""
        session_id = self.kwargs.get("pk")
        data_access = AuditDataAccess(request=self.request)
        try:
            # Try to find the session across all opportunities the user has access to
            session = data_access.get_audit_session(session_id, try_multiple_opportunities=True)
            if not session:
                from django.http import Http404

                raise Http404(f"Session {session_id} not found")
            return session
        finally:
            data_access.close()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        question_filter = self.request.GET.get("question_id", "").strip()
        status_filter = self.request.GET.get("status", "all").strip().lower() or "all"

        context.update(
            {
                "selected_question_id": question_filter,
                "selected_status": status_filter,
                "bulk_data_url": reverse("audit:bulk_assessment_data", kwargs={"session_id": context["session"].pk}),
            }
        )

        return context


class ExperimentAuditResultUpdateView(LoginRequiredMixin, View):
    """AJAX endpoint for updating audit results (experiment-based)"""

    def post(self, request, session_id):
        try:
            # Initialize data access
            data_access = AuditDataAccess(request=request)

            try:
                # Get session
                session = data_access.get_audit_session(session_id, try_multiple_opportunities=True)
                if not session:
                    return JsonResponse({"error": "Session not found"}, status=404)

                visit_id = int(request.POST.get("visit_id"))
                result = request.POST.get("result")
                notes = request.POST.get("notes", "")
                auto_advance = request.POST.get("auto_advance", "true") == "true"
                current_index = int(request.POST.get("current_index", 0))

                if result not in ["pass", "fail", "", None]:
                    return JsonResponse({"error": "Invalid data"}, status=400)

                # Get xform_id and other data from visit
                visit_data = data_access.get_visit_data(visit_id, opportunity_id=session.opportunity_id)
                if not visit_data:
                    return JsonResponse({"error": "Visit not found"}, status=404)

                if result in ["pass", "fail"]:
                    # Update visit result in session
                    session.set_visit_result(
                        visit_id=visit_id,
                        xform_id=visit_data["xform_id"],
                        result=result,
                        notes=notes,
                        user_id=visit_data.get("user_id", 0),
                        opportunity_id=visit_data.get("opportunity_id", session.opportunity_id),
                    )
                else:
                    session.clear_visit_result(visit_id=visit_id)

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
                        "result": result if result else "",
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


class ExperimentAuditVisitDataView(LoginRequiredMixin, View):
    """Fetch visit data for dynamic navigation within the audit detail view."""

    def get(self, request, session_id):
        data_access = AuditDataAccess(request=request)
        try:
            session = data_access.get_audit_session(session_id, try_multiple_opportunities=True)
            if not session:
                return JsonResponse({"error": "Session not found"}, status=404)

            visit_ids = session.visit_ids or []
            total_visits = len(visit_ids)

            try:
                visit_index = int(request.GET.get("visit", 1)) - 1
            except (TypeError, ValueError):
                visit_index = 0

            if total_visits == 0:
                progress_stats = session.get_progress_stats()
                return JsonResponse(
                    {
                        "visit_index": 0,
                        "total_visits": 0,
                        "audited_count": progress_stats["assessed"],
                        "pending_count": progress_stats["total"] - progress_stats["assessed"],
                        "progress_percentage": progress_stats["percentage"],
                        "has_previous": False,
                        "has_next": False,
                        "previous_index": 0,
                        "next_index": 0,
                        "assessments": [],
                    }
                )

            visit_index = max(0, min(visit_index, total_visits - 1))
            visit_id = visit_ids[visit_index]
            opportunity_id = session.opportunity_id

            visit_data = data_access.get_visit_data(visit_id, opportunity_id=opportunity_id)

            try:
                opportunity_details = data_access.get_opportunity_details(opportunity_id) if opportunity_id else None
                cc_domain = opportunity_details.get("cc_domain") if opportunity_details else None
            except Exception:
                cc_domain = None

            blob_metadata = {}
            if cc_domain and visit_data and visit_data.get("xform_id"):
                try:
                    blob_metadata = data_access.get_blob_metadata_for_visit(visit_data["xform_id"], cc_domain)
                except Exception:
                    blob_metadata = {}

            assessments_map = session.get_assessments(visit_id)

            def build_image_url(blob_id: str) -> str:
                url = reverse("audit:audit_image", kwargs={"blob_id": blob_id})
                if cc_domain and visit_data and visit_data.get("xform_id"):
                    url = f"{url}?xform_id={visit_data['xform_id']}&domain={cc_domain}"
                return url

            assessments = []
            for blob_id, metadata in blob_metadata.items():
                assessment_data = assessments_map.get(blob_id, {})
                assessments.append(
                    {
                        "id": f"{visit_id}:{blob_id}",
                        "blob_id": blob_id,
                        "question_id": metadata.get("question_id") or "",
                        "filename": metadata.get("filename") or "",
                        "image_url": build_image_url(blob_id),
                        "result": assessment_data.get("result"),
                        "notes": assessment_data.get("notes", ""),
                    }
                )

            for blob_id, assessment_data in assessments_map.items():
                if blob_id in blob_metadata:
                    continue
                assessments.append(
                    {
                        "id": f"{visit_id}:{blob_id}",
                        "blob_id": blob_id,
                        "question_id": assessment_data.get("question_id") or "",
                        "filename": "",
                        "image_url": build_image_url(blob_id),
                        "result": assessment_data.get("result"),
                        "notes": assessment_data.get("notes", ""),
                    }
                )

            progress_stats = session.get_progress_stats()
            visit_result = session.get_visit_result(visit_id) or {}

            response_data = {
                "visit_index": visit_index,
                "total_visits": total_visits,
                "audited_count": progress_stats["assessed"],
                "pending_count": progress_stats["total"] - progress_stats["assessed"],
                "progress_percentage": progress_stats["percentage"],
                "has_previous": visit_index > 0,
                "has_next": visit_index < total_visits - 1,
                "previous_index": visit_index - 1 if visit_index > 0 else 0,
                "next_index": visit_index + 1 if visit_index < total_visits - 1 else visit_index,
                "visit_id": visit_id,
                "visit_date": visit_data.get("visit_date") if visit_data else None,
                "entity_name": visit_data.get("entity_name") if visit_data else "",
                "location": visit_data.get("location") if visit_data else "",
                "image_count": len(assessments),
                "audit_result": visit_result or {"result": None, "notes": ""},
                "assessments": assessments,
            }

            return JsonResponse(response_data)

        except Exception as e:
            import traceback

            print(f"[ERROR] {traceback.format_exc()}")
            return JsonResponse({"error": str(e)}, status=500)
        finally:
            data_access.close()


class ExperimentAssessmentUpdateView(LoginRequiredMixin, View):
    """AJAX endpoint for updating individual image assessments (experiment-based)"""

    def post(self, request, session_id):
        try:
            # Initialize data access
            data_access = AuditDataAccess(request=request)

            try:
                # Get session
                session = data_access.get_audit_session(session_id, try_multiple_opportunities=True)
                if not session:
                    return JsonResponse({"error": "Session not found"}, status=404)

                visit_id = int(request.POST.get("visit_id"))
                blob_id = request.POST.get("blob_id")
                question_id = request.POST.get("question_id", "")
                result = request.POST.get("result")
                notes = request.POST.get("notes", "")

                if not visit_id or not blob_id or result not in ["pass", "fail", "", None]:
                    return JsonResponse({"error": "Invalid data"}, status=400)

                # Update assessment in session
                if result in ["pass", "fail"] or notes:
                    session.set_assessment(
                        visit_id=visit_id, blob_id=blob_id, question_id=question_id, result=result, notes=notes
                    )
                else:
                    session.clear_assessment(visit_id=visit_id, blob_id=blob_id)

                # Save session
                session = data_access.save_audit_session(session)

                # Calculate updated progress
                progress_stats = session.get_progress_stats()

                return JsonResponse(
                    {
                        "success": True,
                        "result": result if result else "",
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
                session = data_access.get_audit_session(session_id, try_multiple_opportunities=True)
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
                session.data["completed_at"] = timezone.now().isoformat()
                session = data_access.save_audit_session(session)

                return JsonResponse({"success": True})

            finally:
                data_access.close()

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


class ExperimentAuditUncompleteView(LoginRequiredMixin, View):
    """Reopen a completed experiment-based audit session."""

    def post(self, request, session_id):
        data_access = AuditDataAccess(request=request)
        try:
            session = data_access.get_audit_session(session_id, try_multiple_opportunities=True)
            if not session:
                return JsonResponse({"error": "Session not found"}, status=404)

            session.data["status"] = "in_progress"
            session.data["completed_at"] = None

            session = data_access.save_audit_session(session)
            return JsonResponse({"success": True})

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
        finally:
            data_access.close()


class ExperimentApplyAssessmentResultsView(LoginRequiredMixin, View):
    """Apply image assessment outcomes to visit-level results."""

    def post(self, request, session_id):
        data_access = AuditDataAccess(request=request)
        try:
            session = data_access.get_audit_session(session_id, try_multiple_opportunities=True)
            if not session:
                return JsonResponse({"error": "Session not found"}, status=404)

            opportunity_id = session.opportunity_id
            updated_count = 0
            visits_passed = 0
            visits_failed = 0

            for visit_id in session.visit_ids or []:
                assessments = session.get_assessments(visit_id)
                if not assessments:
                    continue

                has_failure = any(a.get("result") == "fail" for a in assessments.values())
                all_assessed = all(a.get("result") in {"pass", "fail"} for a in assessments.values())

                visit_result = session.get_visit_result(visit_id) or {}
                current_result = visit_result.get("result")

                new_result = None
                if has_failure:
                    new_result = "fail"
                    visits_failed += 1
                elif all_assessed:
                    new_result = "pass"
                    visits_passed += 1

                if new_result and new_result != current_result:
                    visit_data = data_access.get_visit_data(visit_id, opportunity_id=opportunity_id)
                    if not visit_data:
                        continue

                    session.set_visit_result(
                        visit_id=visit_id,
                        xform_id=visit_data.get("xform_id", ""),
                        result=new_result,
                        notes=visit_result.get("notes", ""),
                        user_id=visit_data.get("user_id", 0),
                        opportunity_id=visit_data.get("opportunity_id", opportunity_id),
                    )
                    updated_count += 1

            session = data_access.save_audit_session(session)

            return JsonResponse(
                {
                    "success": True,
                    "updated_count": updated_count,
                    "visits_passed": visits_passed,
                    "visits_failed": visits_failed,
                }
            )

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
        finally:
            data_access.close()


class ExperimentBulkAssessmentDataView(LoginRequiredMixin, View):
    """Return bulk assessment data asynchronously."""

    def get(self, request, session_id):
        data_access = AuditDataAccess(request=request)
        try:
            session = data_access.get_audit_session(session_id, try_multiple_opportunities=True)
            if not session:
                return JsonResponse({"error": "Session not found"}, status=404)

            question_filter = request.GET.get("question_id", "").strip()
            status_filter = request.GET.get("status", "all").strip().lower() or "all"

            visit_ids = session.visit_ids or []
            opportunity_id = session.opportunity_id
            cc_domain = None
            primary_opportunity = ""
            earliest_visit = None
            latest_visit = None

            if opportunity_id:
                try:
                    opportunity_details = data_access.get_opportunity_details(opportunity_id)
                    cc_domain = opportunity_details.get("cc_domain") if opportunity_details else None
                    primary_opportunity = opportunity_details.get("name") if opportunity_details else ""
                except Exception:
                    cc_domain = None

            question_ids = set()
            visit_result_map: dict[str, str] = {}
            all_assessments: list[dict] = []
            bulk_primary_username = ""

            for visit_id in visit_ids:
                try:
                    visit_data = data_access.get_visit_data(visit_id, opportunity_id=opportunity_id)
                except Exception:
                    visit_data = None

                if not visit_data:
                    continue

                username = visit_data.get("username") or visit_data.get("user_login") or ""
                if not bulk_primary_username and username:
                    bulk_primary_username = username

                visit_date_raw = visit_data.get("visit_date")
                visit_date_dt = parse_datetime(visit_date_raw) if visit_date_raw else None
                if visit_date_dt and timezone.is_naive(visit_date_dt):
                    visit_date_dt = timezone.make_aware(visit_date_dt, timezone.utc)
                visit_date_local = timezone.localtime(visit_date_dt) if visit_date_dt else None
                visit_date_display = visit_date_local.strftime("%b %d, %H:%M") if visit_date_local else ""
                visit_date_sort = visit_date_local.isoformat() if visit_date_local else ""

                if visit_date_local:
                    if earliest_visit is None or visit_date_local < earliest_visit:
                        earliest_visit = visit_date_local
                    if latest_visit is None or visit_date_local > latest_visit:
                        latest_visit = visit_date_local

                xform_id = visit_data.get("xform_id")
                entity_name = visit_data.get("entity_name") or "No Entity"

                visit_result_entry = session.get_visit_result(visit_id) or {}
                visit_result_value = visit_result_entry.get("result")
                if visit_result_value:
                    visit_result_map[str(visit_id)] = visit_result_value

                assessments_map = session.get_assessments(visit_id)
                seen_blob_ids = set()

                blob_metadata = {}
                if cc_domain and xform_id:
                    try:
                        blob_metadata = data_access.get_blob_metadata_for_visit(xform_id, cc_domain)
                    except Exception:
                        blob_metadata = {}

                def build_image_url(blob_id: str) -> str:
                    url = reverse("audit:audit_image", kwargs={"blob_id": blob_id})
                    if cc_domain and xform_id:
                        url = f"{url}?xform_id={xform_id}&domain={cc_domain}"
                    return url

                for blob_id, metadata in blob_metadata.items():
                    question_id = metadata.get("question_id") or ""
                    question_ids.add(question_id)
                    assessment_data = assessments_map.get(blob_id, {})
                    result_value = assessment_data.get("result") or ""
                    status_value = result_value if result_value in {"pass", "fail"} else "pending"

                    all_assessments.append(
                        {
                            "id": f"{visit_id}:{blob_id}",
                            "visit_id": visit_id,
                            "blob_id": blob_id,
                            "question_id": question_id,
                            "filename": metadata.get("filename") or "",
                            "result": result_value,
                            "notes": assessment_data.get("notes", ""),
                            "status": status_value,
                            "image_url": build_image_url(blob_id),
                            "visit_date": visit_date_display,
                            "visit_date_sort": visit_date_sort,
                            "entity_name": entity_name,
                            "username": username,
                        }
                    )
                    seen_blob_ids.add(blob_id)

                for blob_id, assessment_data in assessments_map.items():
                    if blob_id in seen_blob_ids:
                        continue
                    question_id = assessment_data.get("question_id") or ""
                    question_ids.add(question_id)
                    result_value = assessment_data.get("result") or ""
                    status_value = result_value if result_value in {"pass", "fail"} else "pending"

                    all_assessments.append(
                        {
                            "id": f"{visit_id}:{blob_id}",
                            "visit_id": visit_id,
                            "blob_id": blob_id,
                            "question_id": question_id,
                            "filename": "",
                            "result": result_value,
                            "notes": assessment_data.get("notes", ""),
                            "status": status_value,
                            "image_url": build_image_url(blob_id),
                            "visit_date": visit_date_display,
                            "visit_date_sort": visit_date_sort,
                            "entity_name": entity_name,
                            "username": username,
                        }
                    )

            filtered_assessments = [
                assessment
                for assessment in all_assessments
                if (not question_filter or assessment["question_id"] == question_filter)
                and (status_filter == "all" or assessment["status"] == status_filter)
            ]

            total_assessments = len(all_assessments)
            pass_count = sum(1 for a in all_assessments if a["status"] == "pass")
            fail_count = sum(1 for a in all_assessments if a["status"] == "fail")
            pending_count = total_assessments - pass_count - fail_count

            visit_summaries_map: dict[int, dict] = defaultdict(
                lambda: {
                    "visit_id": None,
                    "visit_date": "",
                    "visit_date_sort": "",
                    "username": "",
                    "entity_name": "",
                    "assessments": [],
                }
            )

            for assessment in all_assessments:
                summary = visit_summaries_map[assessment["visit_id"]]
                summary["visit_id"] = assessment["visit_id"]
                summary["visit_date"] = assessment["visit_date"]
                summary["visit_date_sort"] = assessment["visit_date_sort"]
                summary["username"] = assessment["username"]
                summary["entity_name"] = assessment["entity_name"]
                summary["assessments"].append(assessment)

            visit_summaries = []
            for summary in visit_summaries_map.values():
                assessments = summary["assessments"]
                total = len(assessments)
                passed = sum(1 for a in assessments if a["status"] == "pass")
                failed = sum(1 for a in assessments if a["status"] == "fail")
                pending = total - passed - failed

                suggested_result = None
                if failed > 0:
                    suggested_result = "fail"
                elif total > 0 and pending == 0:
                    suggested_result = "pass"

                visit_summaries.append(
                    {
                        "visit_id": summary["visit_id"],
                        "visit_date": summary["visit_date"],
                        "username": summary["username"],
                        "entity_name": summary["entity_name"],
                        "total_assessments": total,
                        "passed_count": passed,
                        "failed_count": failed,
                        "pending_count": pending,
                        "suggested_result": suggested_result,
                        "visit_date_sort": summary["visit_date_sort"],
                    }
                )

            visit_summaries.sort(key=lambda item: item["visit_date_sort"] or "")
            start_date_display = earliest_visit.strftime("%b %d, %Y") if earliest_visit else ""
            end_date_display = latest_visit.strftime("%b %d, %Y") if latest_visit else ""

            response_data = {
                "assessments": filtered_assessments,
                "question_ids": sorted(q for q in question_ids if q),
                "total_assessments": total_assessments,
                "pending_count": pending_count,
                "pass_count": pass_count,
                "fail_count": fail_count,
                "visit_summaries": visit_summaries,
                "bulk_primary_username": bulk_primary_username,
                "bulk_opportunity_name": primary_opportunity,
                "bulk_start_date": start_date_display,
                "bulk_end_date": end_date_display,
                "visit_results": visit_result_map,
            }

            return JsonResponse(response_data)

        except Exception as e:
            import traceback

            print(f"[ERROR] {traceback.format_exc()}")
            return JsonResponse({"error": str(e)}, status=500)
        finally:
            data_access.close()


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

            # Get auditor username
            username = request.user.username

            # Initialize data access with first selected opportunity ID
            # (Currently requires exactly one opportunity, will support multiple in future)
            data_access = AuditDataAccess(opportunity_id=opportunity_ids[0], request=request)

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
                username=username,
                opportunity_ids=opportunity_ids,
                audit_type=audit_type,
                granularity=criteria.get("granularity", "combined"),
                criteria=criteria,
                preview_data=[],
            )

            # Create session
            session = data_access.create_audit_session(
                template_id=template.id,
                username=username,
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
                    "organization_name": opp.get("organization", ""),  # API returns slug only
                    "program_name": "",  # API returns program ID only, not name
                    "visit_count": opp.get("visit_count", 0),
                    "end_date": opp.get("end_date"),
                    "active": opp.get("is_active", True),  # API field is is_active
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
