"""
Experiment-based Audit Views.

These views use the ExperimentRecord-based data access layer instead of
local Django models. They fetch data dynamically from Connect APIs and
store audit state in ExperimentRecords.

Templates are reused from the existing audit views for consistency.
"""

import json
import logging
import re
from collections import defaultdict

import httpx
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.generic import DetailView, TemplateView, View
from django_tables2 import SingleTableView

from commcare_connect.audit.data_access import AuditDataAccess
from commcare_connect.audit.models import AuditSessionRecord
from commcare_connect.audit.tables import AuditTable
from commcare_connect.labs.analysis.data_access import get_flw_names_for_opportunity

logger = logging.getLogger(__name__)


class ExperimentAuditCreateView(LoginRequiredMixin, TemplateView):
    """Audit creation wizard interface (experiment-based)"""

    template_name = "audit/audit_creation_wizard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Create New Audit Session"

        # Pass labs_context to template for pre-selection
        labs_context = getattr(self.request, "labs_context", {})
        context["default_opportunity_id"] = labs_context.get("opportunity_id") or ""
        context["default_program_id"] = labs_context.get("program_id") or ""

        # Pass opportunities from user's org_data (already fetched from opp_org_program API)
        org_data = getattr(self.request.user, "_org_data", {})
        opportunities = org_data.get("opportunities", [])

        # Filter by program if one is selected in labs_context
        program_id = labs_context.get("program_id")
        if program_id:
            opportunities = [o for o in opportunities if o.get("program") == program_id]

        # Format for template
        context["opportunities_json"] = json.dumps(
            [
                {
                    "id": opp.get("id"),
                    "name": opp.get("name"),
                    "organization_name": opp.get("organization", ""),
                    "program_name": "",
                    "visit_count": opp.get("visit_count", 0),
                    "end_date": opp.get("end_date"),
                    "active": opp.get("is_active", True),
                }
                for opp in opportunities
            ]
        )

        # Quick creation URL parameters for pre-filling the wizard
        # These allow other pages to link directly to audit creation with params
        quick_params = {
            "usernames": self.request.GET.get("usernames", ""),  # FLW usernames (comma-separated)
            "user_id": self.request.GET.get("user_id", ""),
            "audit_type": self.request.GET.get("audit_type", ""),  # date_range, last_n_per_flw, etc.
            "granularity": self.request.GET.get("granularity", ""),  # combined, per_opp, per_flw
            "start_date": self.request.GET.get("start_date", ""),
            "end_date": self.request.GET.get("end_date", ""),
            "count": self.request.GET.get("count", ""),  # for last_n types
            "title": self.request.GET.get("title", ""),
            "tag": self.request.GET.get("tag", ""),
            "auto_create": self.request.GET.get("auto_create", ""),  # if 'true', auto-submit
        }
        # Filter out empty values
        quick_params = {k: v for k, v in quick_params.items() if v}
        context["quick_params"] = json.dumps(quick_params)

        return context


class ExperimentAuditListView(LoginRequiredMixin, SingleTableView):
    """List all experiment-based audit sessions"""

    model = AuditSessionRecord
    table_class = AuditTable
    template_name = "audit/audit_session_list.html"
    paginate_by = 20

    def get_queryset(self):
        # Check if required context is present (program or opportunity)
        labs_context = getattr(self.request, "labs_context", {})
        if not labs_context.get("opportunity_id") and not labs_context.get("program_id"):
            # No program or opportunity selected, return empty list
            return []

        # Get AuditSessionRecords from API (returns list, not QuerySet)
        data_access = AuditDataAccess(request=self.request)
        try:
            sessions = data_access.get_audit_sessions()
            # Sort by id descending (higher IDs are more recent)
            return sorted(sessions, key=lambda x: x.id, reverse=True)
        finally:
            data_access.close()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Check if required context is present (program or opportunity)
        labs_context = getattr(self.request, "labs_context", {})
        context["has_context"] = bool(labs_context.get("opportunity_id") or labs_context.get("program_id"))

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
        from django.conf import settings

        context = super().get_context_data(**kwargs)
        question_filter = self.request.GET.get("question_id", "").strip()
        status_filter = self.request.GET.get("status", "all").strip().lower() or "all"

        session = context["session"]
        opportunity_id = session.opportunity_id

        # Look up org_slug from user's OAuth data (opportunities list)
        # Each opportunity in _org_data has an "organization" field with the org slug
        org_slug = ""
        if opportunity_id:
            org_data = getattr(self.request.user, "_org_data", {})
            opportunities = org_data.get("opportunities", [])
            for opp in opportunities:
                if opp.get("id") == opportunity_id:
                    org_slug = opp.get("organization", "")
                    break

        context.update(
            {
                "selected_question_id": question_filter,
                "selected_status": status_filter,
                "bulk_data_url": reverse("audit:bulk_assessment_data", kwargs={"session_id": session.pk}),
                "org_slug": org_slug,
                "opportunity_id": opportunity_id,
                "connect_url": settings.CONNECT_PRODUCTION_URL,
            }
        )

        return context


class ExperimentSaveAuditView(LoginRequiredMixin, View):
    """Save audit progress without completing"""

    def post(self, request, session_id):
        try:
            # Initialize data access
            data_access = AuditDataAccess(request=request)

            try:
                # Get session
                session = data_access.get_audit_session(session_id, try_multiple_opportunities=True)
                if not session:
                    return JsonResponse({"error": "Session not found"}, status=404)

                # Get visit_results from frontend
                visit_results_json = request.POST.get("visit_results")
                if visit_results_json:
                    try:
                        visit_results = json.loads(visit_results_json)
                        session.data["visit_results"] = visit_results
                    except json.JSONDecodeError as e:
                        return JsonResponse({"error": f"Invalid JSON: {e}"}, status=400)

                # Save session (keeps status as in_progress)
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
                session = data_access.get_audit_session(session_id, try_multiple_opportunities=True)
                if not session:
                    return JsonResponse({"error": "Session not found"}, status=404)

                # Get visit_results from frontend
                visit_results_json = request.POST.get("visit_results")
                if visit_results_json:
                    try:
                        visit_results = json.loads(visit_results_json)
                        session.data["visit_results"] = visit_results
                    except json.JSONDecodeError as e:
                        return JsonResponse({"error": f"Invalid JSON: {e}"}, status=400)

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

            visit_ids = session.visit_ids or []
            opportunity_id = session.opportunity_id
            primary_opportunity = ""
            earliest_visit = None
            latest_visit = None

            if opportunity_id:
                try:
                    opportunity_details = data_access.get_opportunity_details(opportunity_id)
                    primary_opportunity = opportunity_details.get("name") if opportunity_details else ""
                except Exception:
                    pass

            question_ids = set()
            visit_result_map: dict[str, str] = {}
            all_assessments: list[dict] = []
            bulk_primary_username = ""
            assessment_counter = 0  # Counter to ensure unique IDs even for duplicate visits

            # Use stored visit_images data - no need to fetch visits again!
            for visit_id in visit_ids:
                visit_result_entry = session.get_visit_result(visit_id) or {}
                visit_result_value = visit_result_entry.get("result")
                if visit_result_value:
                    visit_result_map[str(visit_id)] = visit_result_value

                assessments_map = session.get_assessments(visit_id)
                seen_blob_ids = set()

                # Get images from stored session data (includes question_id, username, visit_date, entity_name)
                images_metadata = session.data.get("visit_images", {}).get(str(visit_id), [])

                if not images_metadata:
                    continue

                # Get visit-level data from first image (all images have same visit data)
                first_image = images_metadata[0]
                username = first_image.get("username", "")
                if not bulk_primary_username and username:
                    bulk_primary_username = username

                visit_date_raw = first_image.get("visit_date", "")
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

                entity_name = first_image.get("entity_name", "No Entity")

                # Convert to dict for easy lookup
                blob_metadata = {
                    img["blob_id"]: {"question_id": img["question_id"], "filename": img["name"]}
                    for img in images_metadata
                }

                def build_image_url(blob_id: str) -> str:
                    # Use Connect API image endpoint
                    url = reverse("audit:audit_image_connect", kwargs={"opp_id": opportunity_id, "blob_id": blob_id})
                    return url

                for blob_id, metadata in blob_metadata.items():
                    question_id = metadata.get("question_id") or ""
                    question_ids.add(question_id)
                    assessment_data = assessments_map.get(blob_id, {})
                    result_value = assessment_data.get("result") or ""
                    status_value = result_value if result_value in {"pass", "fail"} else "pending"

                    # Use counter to ensure unique IDs even if same visit appears multiple times
                    assessment_counter += 1
                    all_assessments.append(
                        {
                            "id": f"{assessment_counter}:{visit_id}:{blob_id}",
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

                    # Use counter to ensure unique IDs
                    assessment_counter += 1
                    all_assessments.append(
                        {
                            "id": f"{assessment_counter}:{visit_id}:{blob_id}",
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

            # All filtering happens client-side now
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
                "assessments": all_assessments,
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


class ExperimentAuditImageConnectView(LoginRequiredMixin, View):
    """Serve audit visit images from Connect API (no CommCare HQ)"""

    def get(self, request, opp_id, blob_id):
        try:
            # Initialize data access with opportunity ID
            data_access = AuditDataAccess(opportunity_id=opp_id, request=request)

            try:
                # Download image from Connect API
                image_content = data_access.download_image_from_connect(blob_id, opp_id)

                # Return as image response
                response = HttpResponse(image_content, content_type="image/jpeg")
                response["Content-Disposition"] = f'inline; filename="{blob_id}.jpg"'
                return response

            finally:
                data_access.close()

        except Exception as e:
            import traceback

            print(f"[ERROR] Image fetch failed for blob_id={blob_id}, opp_id={opp_id}")
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

            # Check if preview passed pre-computed visit IDs (optimization: skip re-fetch)
            precomputed_visit_ids = data.get("visit_ids")
            precomputed_flw_data = data.get("flw_visit_ids")  # {username: [visit_ids]}

            if precomputed_visit_ids and precomputed_flw_data:
                # Use pre-computed data from preview (no CSV parsing needed!)
                import logging

                logging.info(
                    f"[OPTIMIZATION] Using precomputed data: {len(precomputed_visit_ids)} visit_ids, "
                    f"{len(precomputed_flw_data)} FLWs"
                )
                visit_ids = precomputed_visit_ids
                # Build all_visits_with_info from precomputed data (minimal info needed for grouping)
                all_visits_with_info = []
                for flw_username, flw_visit_ids in precomputed_flw_data.items():
                    for vid in flw_visit_ids:
                        all_visits_with_info.append({"id": vid, "username": flw_username})
            else:
                # Fallback: compute visit IDs (slower path, requires CSV parsing)
                import logging

                logging.info(
                    f"[FALLBACK] Precomputed data not available - "
                    f"visit_ids={bool(precomputed_visit_ids)}, flw_data={bool(precomputed_flw_data)}"
                )
                visit_ids, all_visits_with_info = data_access.get_visit_ids_for_audit(
                    opportunity_ids=opportunity_ids,
                    audit_type=audit_type,
                    criteria=normalized_criteria,
                    return_visits=True,
                )

            # Filter by selected FLW identifiers if provided
            selected_flw_user_ids = normalized_criteria.get("selected_flw_user_ids", [])
            granularity = criteria.get("granularity", "combined")

            # Get FLW names mapping for title construction
            flw_names = {}
            try:
                flw_names = get_flw_names_for_opportunity(request)
            except Exception:
                pass  # Fall back to using FLW IDs

            # Get opportunity name for title construction
            opp_name = None
            if opportunity_ids:
                try:
                    opps = data_access.search_opportunities("", limit=1000)
                    for opp in opps:
                        if opp.get("id") == opportunity_ids[0]:
                            opp_name = opp.get("name")
                            break
                except Exception:
                    pass  # Fall back to no prefix

            # User-provided title suffix
            title_suffix = criteria.get("title", "").strip()

            # For per_flw granularity with multiple FLWs, create separate sessions
            if granularity == "per_flw" and selected_flw_user_ids and len(selected_flw_user_ids) > 1:
                # OPTIMIZATION: Pre-compute all FLW visit IDs to batch operations
                flw_visit_id_map = {}
                all_flw_visit_ids = []
                for flw_id in selected_flw_user_ids:
                    flw_visit_ids = [
                        v["id"]
                        for v in all_visits_with_info
                        if v.get("username") == flw_id or v.get("user_id") == flw_id
                    ]
                    if flw_visit_ids:
                        flw_visit_id_map[flw_id] = flw_visit_ids
                        all_flw_visit_ids.extend(flw_visit_ids)

                if not flw_visit_id_map:
                    return JsonResponse({"error": "No visits found matching criteria"}, status=400)

                # OPTIMIZATION: Extract images for ALL visits at once (1 CSV parse instead of N)
                opp_id = opportunity_ids[0] if opportunity_ids else None
                all_visit_images = data_access.extract_images_for_visits(all_flw_visit_ids, opp_id)

                # OPTIMIZATION: Create ONE template for all sessions (1 POST instead of N)
                template = data_access.create_audit_template(
                    username=username,
                    opportunity_ids=opportunity_ids,
                    audit_type=audit_type,
                    granularity=granularity,
                    criteria=criteria,
                    preview_data=[],
                )

                # Create one session per FLW, reusing template and pre-extracted data
                sessions_created = []
                for flw_id, flw_visit_ids in flw_visit_id_map.items():
                    # Construct title: FLW Name - suffix
                    flw_display_name = flw_names.get(flw_id, flw_id)
                    session_title = f"{flw_display_name} - {title_suffix}" if title_suffix else flw_display_name

                    # Filter pre-extracted images to just this FLW's visits
                    flw_images = {str(vid): all_visit_images.get(str(vid), []) for vid in flw_visit_ids}

                    # Create session with pre-computed data (no redundant API calls)
                    session = data_access.create_audit_session(
                        template_id=template.id,
                        username=username,
                        visit_ids=flw_visit_ids,
                        title=session_title,
                        tag=criteria.get("tag", ""),
                        opportunity_id=opp_id,
                        audit_type=audit_type,
                        criteria=normalized_criteria,
                        opportunity_name=opp_name or "",
                        visit_images=flw_images,
                    )
                    sessions_created.append({"session_id": session.id, "flw_id": flw_id, "visits": len(flw_visit_ids)})

                return JsonResponse(
                    {
                        "success": True,
                        "redirect_url": str(reverse_lazy("audit:session_list")),
                        "sessions_created": len(sessions_created),
                        "sessions": sessions_created,
                        "stats": {"total_visits": sum(s["visits"] for s in sessions_created)},
                    }
                )

            # For combined/per_opp granularity or single FLW, create one session
            if selected_flw_user_ids:
                # Filter visits to selected FLWs
                visit_ids = [
                    v["id"]
                    for v in all_visits_with_info
                    if v.get("username") in selected_flw_user_ids or v.get("user_id") in selected_flw_user_ids
                ]

            if not visit_ids:
                return JsonResponse({"error": "No visits found matching criteria"}, status=400)

            # Construct title based on granularity
            if granularity == "per_flw" and selected_flw_user_ids and len(selected_flw_user_ids) == 1:
                # Single FLW selected
                flw_id = selected_flw_user_ids[0]
                flw_display_name = flw_names.get(flw_id, flw_id)
                session_title = f"{flw_display_name} - {title_suffix}" if title_suffix else flw_display_name
            elif opp_name:
                # Use opportunity name as prefix
                session_title = f"{opp_name} - {title_suffix}" if title_suffix else opp_name
            else:
                # Fallback to just suffix or date
                session_title = title_suffix if title_suffix else f"Audit {timezone.now().strftime('%Y-%m-%d')}"

            # OPTIMIZATION: Extract images for all visits at once (1 CSV parse)
            opp_id = opportunity_ids[0] if opportunity_ids else None
            all_visit_images = data_access.extract_images_for_visits(visit_ids, opp_id)

            # Create template
            template = data_access.create_audit_template(
                username=username,
                opportunity_ids=opportunity_ids,
                audit_type=audit_type,
                granularity=granularity,
                criteria=criteria,
                preview_data=[],
            )

            # Create session with pre-computed data (no redundant API calls)
            session = data_access.create_audit_session(
                template_id=template.id,
                username=username,
                visit_ids=visit_ids,
                title=session_title,
                tag=criteria.get("tag", ""),
                opportunity_id=opp_id,
                audit_type=audit_type,
                criteria=normalized_criteria,
                opportunity_name=opp_name or "",
                visit_images=all_visit_images,
            )

            # Determine redirect URL
            redirect_url = reverse_lazy("audit:session_list")

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

        # Get program_id from labs_context to filter opportunities
        labs_context = getattr(request, "labs_context", {})
        program_id = labs_context.get("program_id")

        data_access = AuditDataAccess(request=request)
        try:
            opportunities = data_access.search_opportunities(query, limit, program_id=program_id)

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

            # Get visit IDs AND filtered visits in one call (avoids redundant fetches)
            visit_ids, filtered_visits = data_access.get_visit_ids_for_audit(
                opportunity_ids=opportunity_ids,
                audit_type=audit_type,
                criteria=normalized_criteria,
                return_visits=True,
            )

            # Fetch FLW names mapping (username -> display name)
            flw_names = {}
            try:
                flw_names = get_flw_names_for_opportunity(request)
            except Exception as e:
                import logging

                logging.warning(f"Could not fetch FLW names: {e}")

            # Group filtered visits by FLW
            flw_data = {}
            for visit in filtered_visits:
                # Use username as primary identifier
                username = visit.get("username")
                if not username:
                    continue

                if username not in flw_data:
                    flw_data[username] = {
                        "user_id": visit.get("user_id"),  # May be None
                        "name": flw_names.get(username, username),  # Use proper name, fallback to username
                        "connect_id": username,
                        "visit_count": 0,
                        "visits": [],
                        "opportunity_id": visit.get("opportunity_id"),
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
                        "visit_ids": [v["id"] for v in flw["visits"]],  # For create to skip re-fetch
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
                        "visit_ids": visit_ids,  # Pass to create to skip re-computation
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


class VisitDetailFromProductionView(LoginRequiredMixin, TemplateView):
    """Fetch and display visit detail HTML from Connect production."""

    template_name = "audit/visit_detail_from_production.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        visit_id = self.kwargs.get("visit_id")

        if not visit_id:
            context["error"] = "Visit ID is required"
            return context

        # Get OAuth token from session
        labs_oauth = self.request.session.get("labs_oauth", {})
        access_token = labs_oauth.get("access_token")

        if not access_token:
            # If user is authenticated (LabsUser exists), they just need to refresh their session
            # Otherwise they need to log in
            if self.request.user.is_authenticated:
                context["error"] = "OAuth token not found in session. Please refresh your session or log in again."
            else:
                context["error"] = "OAuth token not found. Please log in again."
            return context

        # Get visit data to find opportunity_id
        data_access = AuditDataAccess(request=self.request)
        try:
            # Try to get visit data from any opportunity the user has access to
            visit_data = None
            opportunity_id = None
            org_slug = ""

            # Get opportunity_id from labs_context if available
            labs_context = getattr(self.request, "labs_context", {})
            opportunity_id = labs_context.get("opportunity_id")

            # If not in context, try to find visit across all opportunities
            if not opportunity_id:
                org_data = getattr(self.request.user, "_org_data", {})
                opportunities = org_data.get("opportunities", [])
                for opp in opportunities:
                    opp_id = opp.get("id")
                    if opp_id:
                        visit_data = data_access.get_visit_data(visit_id, opportunity_id=opp_id)
                        if visit_data:
                            opportunity_id = opp_id
                            org_slug = opp.get("organization", "")
                            break
            else:
                # Get org_slug from user's org_data
                org_data = getattr(self.request.user, "_org_data", {})
                opportunities = org_data.get("opportunities", [])
                for opp in opportunities:
                    if opp.get("id") == opportunity_id:
                        org_slug = opp.get("organization", "")
                        break
                visit_data = data_access.get_visit_data(visit_id, opportunity_id=opportunity_id)

            if not visit_data or not opportunity_id or not org_slug:
                context["error"] = f"Visit {visit_id} not found or you don't have access to it."
                return context

            # Validate that we have all required components for the URL
            if not org_slug.strip():
                context["error"] = f"Unable to determine organization for visit {visit_id}."
                return context

            # Fetch HTML from Connect production
            production_url = settings.CONNECT_PRODUCTION_URL.rstrip("/")
            visit_detail_url = f"{production_url}/a/{org_slug}/opportunity/{opportunity_id}/user_visit_details/{visit_id}/"

            try:
                http_client = httpx.Client(
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=30.0,
                    follow_redirects=True,
                )
                response = http_client.get(visit_detail_url)
                http_client.close()

                if response.status_code == 200:
                    # Extract the visit detail HTML from the response
                    html_content = response.text

                    # Extract the visit-details div content
                    # Find the opening tag of div with id="visit-details"
                    opening_tag_pattern = r'<div[^>]*id=["\']visit-details["\'][^>]*>'
                    opening_match = re.search(opening_tag_pattern, html_content, re.IGNORECASE)
                    
                    if opening_match:
                        start_pos = opening_match.start()
                        # Find the matching closing </div> tag by counting nested divs
                        div_count = 0
                        pos = start_pos
                        while pos < len(html_content):
                            # Check for opening div tag (but skip HTML comments)
                            if html_content[pos:pos+4] == "<div":
                                # Make sure it's not a closing tag, comment, or script/style tag
                                if (pos + 4 < len(html_content) and 
                                    html_content[pos+1] != "/" and
                                    not html_content[pos:pos+9].startswith("<!--")):
                                    div_count += 1
                            # Check for closing div tag
                            elif html_content[pos:pos+6] == "</div>":
                                div_count -= 1
                                if div_count == 0:
                                    end_pos = pos + 6
                                    context["visit_detail_html"] = html_content[start_pos:end_pos]
                                    break
                            pos += 1
                        else:
                            # Couldn't find matching closing tag, use a simple fallback
                            # Try to find the div with x-data containing slides
                            slides_match = re.search(
                                r'<div[^>]*x-data=["\'][^>]*slides[^>]*>',
                                html_content,
                                re.IGNORECASE
                            )
                            if slides_match:
                                context["visit_detail_html"] = html_content[slides_match.start():]
                            else:
                                context["visit_detail_html"] = html_content
                    else:
                        # Fallback: try to find div with x-data containing "slides"
                        slides_match = re.search(
                            r'<div[^>]*x-data=["\'][^>]*slides[^>]*>',
                            html_content,
                            re.IGNORECASE
                        )
                        if slides_match:
                            context["visit_detail_html"] = html_content[slides_match.start():]
                        else:
                            # Last resort: use body content or full HTML
                            body_match = re.search(r'<body[^>]*>(.*?)</body>', html_content, re.DOTALL | re.IGNORECASE)
                            if body_match:
                                context["visit_detail_html"] = body_match.group(1)
                            else:
                                context["visit_detail_html"] = html_content

                    context["visit_id"] = visit_id
                else:
                    logger.error(
                        f"Failed to fetch visit detail: {response.status_code} - {response.text[:200]}"
                    )
                    context["error"] = f"Failed to load visit details (HTTP {response.status_code})"
            except httpx.RequestError as e:
                logger.error(f"Error fetching visit detail: {str(e)}")
                context["error"] = f"Error connecting to Connect production: {str(e)}"
            except Exception as e:
                logger.error(f"Unexpected error: {str(e)}")
                context["error"] = f"Unexpected error: {str(e)}"

        finally:
            data_access.close()

        return context
