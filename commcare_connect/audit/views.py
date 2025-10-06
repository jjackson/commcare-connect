import json
import threading

from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import DetailView, TemplateView, View
from django_tables2 import SingleTableView

from commcare_connect.audit.management.extractors.connect_api_facade import ConnectAPIFacade
from commcare_connect.audit.models import AuditResult, AuditSession
from commcare_connect.audit.services.audit_creator import create_audit_sessions, preview_audit_sessions
from commcare_connect.audit.services.database_manager import get_database_stats, reset_audit_database
from commcare_connect.audit.services.progress_tracker import ProgressTracker
from commcare_connect.audit.tables import AuditSessionTable
from commcare_connect.opportunity.models import BlobMeta, UserVisit

User = get_user_model()


class AuditSessionListView(LoginRequiredMixin, SingleTableView):
    """List all audit sessions"""

    model = AuditSession
    table_class = AuditSessionTable
    template_name = "audit/audit_session_list.html"
    paginate_by = 20

    def get_queryset(self):
        return AuditSession.objects.order_by("-created_at")


class AuditSessionDetailView(LoginRequiredMixin, DetailView):
    """Main audit interface for reviewing visits one at a time"""

    model = AuditSession
    template_name = "audit/audit_session_detail.html"
    context_object_name = "session"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.get_object()

        # Get all UserVisits explicitly assigned to this session
        all_visits = session.visits.all().select_related("user", "opportunity", "deliver_unit").order_by("visit_date")

        # Get existing audit results
        existing_results = {result.user_visit_id: result for result in session.results.select_related("user_visit")}

        # Get current visit index from URL parameter
        visit_index = int(self.request.GET.get("visit", 0))
        total_visits = all_visits.count()

        # Ensure visit_index is within bounds
        if visit_index < 0:
            visit_index = 0
        elif visit_index >= total_visits:
            visit_index = max(0, total_visits - 1)

        # Get current visit
        current_visit = None
        if total_visits > 0:
            current_visit = all_visits[visit_index]
            current_visit.audit_result = existing_results.get(current_visit.id)

        # Progress information
        audited_count = len(existing_results)
        pending_count = total_visits - audited_count

        context.update(
            {
                "current_visit": current_visit,
                "visit_index": visit_index,
                "total_visits": total_visits,
                "audited_count": audited_count,
                "pending_count": pending_count,
                "progress_percentage": round((audited_count / total_visits) * 100, 1) if total_visits > 0 else 0,
                "has_previous": visit_index > 0,
                "has_next": visit_index < total_visits - 1,
                "previous_index": visit_index - 1 if visit_index > 0 else 0,
                "next_index": visit_index + 1 if visit_index < total_visits - 1 else visit_index,
            }
        )

        return context


class AuditResultUpdateView(LoginRequiredMixin, View):
    """AJAX endpoint for updating audit results"""

    def post(self, request, session_id):
        try:
            session = get_object_or_404(AuditSession, id=session_id)
            visit_id = request.POST.get("visit_id")
            result = request.POST.get("result")
            notes = request.POST.get("notes", "")
            image_notes_json = request.POST.get("image_notes", "{}")
            auto_advance = request.POST.get("auto_advance", "true") == "true"
            current_index = int(request.POST.get("current_index", 0))

            if not visit_id or result not in ["pass", "fail"]:
                return JsonResponse({"error": "Invalid data"}, status=400)

            visit = get_object_or_404(UserVisit, id=visit_id)

            # Create or update audit result
            audit_result, created = AuditResult.objects.update_or_create(
                audit_session=session, user_visit=visit, defaults={"result": result, "notes": notes}
            )

            # Handle image notes
            try:
                image_notes = json.loads(image_notes_json)
                # Clear existing image notes for this audit result
                audit_result.image_notes.all().delete()
                # Create new image notes
                for blob_id, note_text in image_notes.items():
                    if note_text.strip():  # Only save non-empty notes
                        from .models import AuditImageNote

                        AuditImageNote.objects.create(
                            audit_result=audit_result, blob_id=blob_id, note=note_text.strip()
                        )
            except json.JSONDecodeError:
                pass  # Ignore invalid JSON

            # Calculate updated progress using explicit visit set
            total_visits = session.visits.count()

            audited_count = session.results.count()
            progress_percentage = round((audited_count / total_visits) * 100, 1) if total_visits > 0 else 0

            # Determine next visit index for auto-advance
            next_index = current_index + 1 if auto_advance and current_index + 1 < total_visits else current_index

            return JsonResponse(
                {
                    "success": True,
                    "created": created,
                    "progress_percentage": progress_percentage,
                    "audited_count": audited_count,
                    "total_visits": total_visits,
                    "next_index": next_index,
                    "should_advance": auto_advance and next_index != current_index,
                }
            )

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


class AuditSessionCompleteView(LoginRequiredMixin, View):
    """Complete an audit session"""

    def post(self, request, session_id):
        try:
            session = get_object_or_404(AuditSession, id=session_id)

            overall_result = request.POST.get("overall_result")
            notes = request.POST.get("notes", "")
            kpi_notes = request.POST.get("kpi_notes", "")

            if overall_result not in ["pass", "fail"]:
                return JsonResponse({"error": "Invalid overall result"}, status=400)

            session.status = AuditSession.Status.COMPLETED
            session.overall_result = overall_result
            session.notes = notes
            session.kpi_notes = kpi_notes
            session.completed_at = timezone.now()
            session.save()

            return JsonResponse({"success": True})

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


class AuditSessionUncompleteView(LoginRequiredMixin, View):
    """Reopen a completed audit session"""

    def post(self, request, session_id):
        try:
            session = get_object_or_404(AuditSession, id=session_id)

            if session.status != AuditSession.Status.COMPLETED:
                return JsonResponse({"error": "Audit session is not completed"}, status=400)

            session.status = AuditSession.Status.IN_PROGRESS
            session.completed_at = None
            session.save()

            return JsonResponse({"success": True})

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


class AuditExportView(LoginRequiredMixin, DetailView):
    """Export audit session results as JSON"""

    model = AuditSession

    def get(self, request, *args, **kwargs):
        session = self.get_object()

        # Generate export data
        export_data = {
            "audit_session": {
                "id": session.id,
                "auditor_username": session.auditor_username,
                "flw_username": session.flw_username,
                "opportunity_name": session.opportunity_name,
                "domain": session.domain,
                "app_id": session.app_id,
                "date_range": [str(session.start_date), str(session.end_date)],
                "overall_result": session.overall_result,
                "notes": session.notes,
                "kpi_notes": session.kpi_notes,
                "created_at": session.created_at.isoformat(),
                "completed_at": session.completed_at.isoformat() if session.completed_at else None,
            },
            "visit_results": [],
        }

        # Build visit results with images and image notes
        for result in session.results.select_related("user_visit__user").prefetch_related("image_notes").all():
            # Get image notes keyed by blob_id for easy lookup
            image_notes_dict = {note.blob_id: note.note for note in result.image_notes.all()}

            # Build images list with notes
            images = []
            for img in result.user_visit.images.all():
                image_data = {
                    "filename": img.name,
                }
                # Add note if exists for this image
                if img.blob_id in image_notes_dict:
                    image_data["note"] = image_notes_dict[img.blob_id]
                images.append(image_data)

            visit_result = {
                "visit_id": result.user_visit.id,
                "xform_id": result.user_visit.xform_id,
                "visit_date": result.user_visit.visit_date.isoformat(),
                "entity_id": result.user_visit.entity_id,
                "entity_name": result.user_visit.entity_name,
                "user_username": result.user_visit.user.username,
                "result": result.result,
                "notes": result.notes,
                "images": images,
                "image_count": len(images),
                "audited_at": result.audited_at.isoformat(),
            }
            export_data["visit_results"].append(visit_result)

        # Return as JSON download
        response = HttpResponse(
            content_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="audit_export_{session.id}.json"'},
        )

        json.dump(export_data, response, indent=2)
        return response


class AuditExportAllView(LoginRequiredMixin, View):
    """Export all completed audit sessions as a single JSON file"""

    def get(self, request):
        # Get all completed audit sessions
        completed_sessions = AuditSession.objects.filter(status=AuditSession.Status.COMPLETED).order_by(
            "-completed_at"
        )

        if not completed_sessions.exists():
            return JsonResponse({"error": "No completed audit sessions to export"}, status=404)

        # Generate export data for all sessions
        all_audits = []
        for session in completed_sessions:
            visit_results = []

            # Build visit results with images and image notes
            for result in session.results.select_related("user_visit__user").prefetch_related("image_notes").all():
                # Get image notes keyed by blob_id for easy lookup
                image_notes_dict = {note.blob_id: note.note for note in result.image_notes.all()}

                # Build images list with notes
                images = []
                for img in result.user_visit.images.all():
                    image_data = {
                        "filename": img.name,
                    }
                    # Add note if exists for this image
                    if img.blob_id in image_notes_dict:
                        image_data["note"] = image_notes_dict[img.blob_id]
                    images.append(image_data)

                visit_result = {
                    "visit_id": result.user_visit.id,
                    "xform_id": result.user_visit.xform_id,
                    "visit_date": result.user_visit.visit_date.isoformat(),
                    "entity_id": result.user_visit.entity_id,
                    "entity_name": result.user_visit.entity_name,
                    "user_username": result.user_visit.user.username,
                    "result": result.result,
                    "notes": result.notes,
                    "images": images,
                    "image_count": len(images),
                    "audited_at": result.audited_at.isoformat(),
                }
                visit_results.append(visit_result)

            audit_data = {
                "audit_session": {
                    "id": session.id,
                    "auditor_username": session.auditor_username,
                    "flw_username": session.flw_username,
                    "opportunity_name": session.opportunity_name,
                    "domain": session.domain,
                    "app_id": session.app_id,
                    "date_range": [str(session.start_date), str(session.end_date)],
                    "overall_result": session.overall_result,
                    "notes": session.notes,
                    "kpi_notes": session.kpi_notes,
                    "created_at": session.created_at.isoformat(),
                    "completed_at": session.completed_at.isoformat() if session.completed_at else None,
                },
                "visit_results": visit_results,
            }
            all_audits.append(audit_data)

        # Create combined export
        export_data = {
            "export_metadata": {
                "export_date": timezone.now().isoformat(),
                "total_audits": len(all_audits),
                "exported_by": request.user.username or request.user.email,
            },
            "audits": all_audits,
        }

        # Return as JSON download
        filename = f'audit_export_all_{timezone.now().strftime("%Y%m%d_%H%M%S")}.json'
        response = HttpResponse(
            content_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

        json.dump(export_data, response, indent=2)
        return response


class AuditImageView(LoginRequiredMixin, View):
    """Serve audit visit images"""

    def get(self, request, blob_id):
        blob_meta = get_object_or_404(BlobMeta, blob_id=blob_id)

        try:
            from django.core.files.storage import default_storage

            file_content = default_storage.open(str(blob_meta.blob_id))

            response = FileResponse(file_content, content_type=blob_meta.content_type, filename=blob_meta.name)
            return response

        except Exception as e:
            return HttpResponse(f"Image not found: {e}", status=404)


class AuditVisitDataView(LoginRequiredMixin, View):
    """AJAX endpoint to fetch visit data without page reload"""

    def get(self, request, session_id):
        session = get_object_or_404(AuditSession, id=session_id)
        visit_index = int(request.GET.get("visit", 0))

        # Get all visits explicitly assigned to this session
        all_visits = session.visits.all().select_related("user", "opportunity", "deliver_unit").order_by("visit_date")

        existing_results = {result.user_visit_id: result for result in session.results.select_related("user_visit")}

        total_visits = all_visits.count()

        if visit_index < 0:
            visit_index = 0
        elif visit_index >= total_visits:
            visit_index = max(0, total_visits - 1)

        current_visit = None
        if total_visits > 0:
            current_visit = all_visits[visit_index]
            current_visit.audit_result = existing_results.get(current_visit.id)

        audited_count = len(existing_results)

        # Prepare visit data
        visit_data = {
            "visit_index": visit_index,
            "total_visits": total_visits,
            "audited_count": audited_count,
            "pending_count": total_visits - audited_count,
            "progress_percentage": round((audited_count / total_visits) * 100, 1) if total_visits > 0 else 0,
            "has_previous": visit_index > 0,
            "has_next": visit_index < total_visits - 1,
            "previous_index": visit_index - 1 if visit_index > 0 else 0,
            "next_index": visit_index + 1 if visit_index < total_visits - 1 else visit_index,
        }

        if current_visit:
            # Get existing image notes if audit result exists
            image_notes = {}
            if hasattr(current_visit, "audit_result") and current_visit.audit_result:
                from .models import AuditImageNote

                existing_image_notes = AuditImageNote.objects.filter(audit_result=current_visit.audit_result)
                image_notes = {note.blob_id: note.note for note in existing_image_notes}

            visit_data.update(
                {
                    "visit_id": current_visit.id,
                    "visit_date": current_visit.visit_date.strftime("%b %d, %H:%M"),
                    "entity_name": current_visit.entity_name or "No Entity",
                    "location": current_visit.location or "No Location",
                    "image_count": current_visit.images.count(),
                    "audit_result": {
                        "result": current_visit.audit_result.result if current_visit.audit_result else None,
                        "notes": current_visit.audit_result.notes if current_visit.audit_result else "",
                    }
                    if hasattr(current_visit, "audit_result") and current_visit.audit_result
                    else None,
                    "image_notes": image_notes,
                    "images": [
                        {
                            "blob_id": image.blob_id,
                            "url": request.build_absolute_uri(f"/audit/image/{image.blob_id}/"),
                            "counter": idx + 1,
                        }
                        for idx, image in enumerate(current_visit.images.all())
                    ],
                }
            )

        return JsonResponse(visit_data)


class AuditCreationWizardView(LoginRequiredMixin, TemplateView):
    """Main audit creation wizard interface"""

    template_name = "audit/audit_creation_wizard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Create New Audit Session"
        return context


class ProgramSearchAPIView(LoginRequiredMixin, View):
    """API endpoint for searching opportunities (renamed from programs for backward compatibility)"""

    def get(self, request):
        query = request.GET.get("q", "").strip()
        limit = min(int(request.GET.get("limit", 20)), 100)  # Cap at 100 results

        print(f"[VIEW DEBUG] query='{query}', limit={limit}")
        print(f"[VIEW DEBUG] user={request.user}")

        facade = ConnectAPIFacade()
        print("[VIEW DEBUG] facade created")

        facade.authenticate()
        print("[VIEW DEBUG] facade authenticated")

        opportunities = facade.search_opportunities(query, limit)
        print(f"[VIEW DEBUG] opportunities returned: {len(opportunities)}")

        if opportunities:
            for opp in opportunities:
                print(f"[VIEW DEBUG] - ID: {opp.id}, Name: {opp.name}, Visits: {opp.visit_count}")
        else:
            print("[VIEW DEBUG] No opportunities found")

        # Convert opportunities to JSON-serializable format
        opportunities_data = []
        for opportunity in opportunities:
            opportunities_data.append(
                {
                    "id": opportunity.id,
                    "name": opportunity.name,
                    "description": opportunity.description,
                    "program_id": opportunity.program_id,
                    "program_name": opportunity.program_name,
                    "organization_id": opportunity.organization_id,
                    "organization_name": opportunity.organization_name,
                    "start_date": opportunity.start_date.isoformat() if opportunity.start_date else None,
                    "end_date": opportunity.end_date.isoformat() if opportunity.end_date else None,
                    "deliver_app_id": opportunity.deliver_app_id,
                    "deliver_app_domain": opportunity.deliver_app_domain,
                    "deliver_app_cc_app_id": opportunity.deliver_app_cc_app_id,
                    "is_test": opportunity.is_test,
                    "active": opportunity.active,
                    "visit_count": opportunity.visit_count,
                }
            )

        facade.close()

        return JsonResponse(
            {"success": True, "opportunities": opportunities_data, "count": len(opportunities_data), "query": query}
        )


class ProgramOpportunitiesAPIView(LoginRequiredMixin, View):
    """API endpoint for getting opportunities within a program"""

    def get(self, request, program_id):
        try:
            facade = ConnectAPIFacade()
            if not facade.authenticate():
                return JsonResponse({"error": "Failed to authenticate with data source"}, status=500)

            try:
                opportunities = facade.get_opportunities_by_program(program_id)

                # Convert opportunities to JSON-serializable format
                opportunities_data = []
                for opp in opportunities:
                    opportunities_data.append(
                        {
                            "id": opp.id,
                            "name": opp.name,
                            "description": opp.description,
                            "program_id": opp.program_id,
                            "program_name": opp.program_name,
                            "organization_id": opp.organization_id,
                            "organization_name": opp.organization_name,
                            "start_date": opp.start_date.isoformat() if opp.start_date else None,
                            "end_date": opp.end_date.isoformat() if opp.end_date else None,
                            "deliver_app_id": opp.deliver_app_id,
                            "deliver_app_domain": opp.deliver_app_domain,
                            "deliver_app_cc_app_id": opp.deliver_app_cc_app_id,
                            "is_test": opp.is_test,
                            "active": opp.active,
                        }
                    )

                return JsonResponse(
                    {
                        "success": True,
                        "opportunities": opportunities_data,
                        "count": len(opportunities_data),
                        "program_id": program_id,
                    }
                )

            finally:
                facade.close()

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


class AuditPreviewAPIView(LoginRequiredMixin, View):
    """API endpoint for previewing audit scope (FLW counts and visit numbers)"""

    def post(self, request):
        try:
            data = json.loads(request.body)
            opportunity_ids = data.get("opportunities", [])
            criteria = data.get("criteria", {})

            if not opportunity_ids or not criteria:
                return JsonResponse({"error": "Missing opportunities or criteria"}, status=400)

            # Initialize and authenticate facade
            facade = ConnectAPIFacade()
            if not facade.authenticate():
                return JsonResponse({"error": "Failed to authenticate with data source"}, status=500)

            try:
                # Use the same service that creates audits to generate preview
                result = preview_audit_sessions(
                    facade=facade,
                    opportunity_ids=opportunity_ids,
                    criteria=criteria,
                )

                if not result.success:
                    return JsonResponse({"error": result.error}, status=500)

                return JsonResponse({"success": True, "results": result.preview_data})

            finally:
                facade.close()

        except Exception as e:
            import traceback

            return JsonResponse({"error": str(e), "traceback": traceback.format_exc()}, status=500)


class AuditSessionCreateAPIView(LoginRequiredMixin, View):
    """API endpoint for creating audit sessions and loading data"""

    def _run_audit_creation_in_background(self, task_id, opportunity_ids, criteria, auditor_username):
        """Run audit creation in a background thread"""
        progress_tracker = ProgressTracker(task_id=task_id)
        facade = None

        try:
            # Initialize and authenticate facade
            facade = ConnectAPIFacade()
            if not facade.authenticate():
                progress_tracker.error("Failed to authenticate with data source")
                return

            # Create audit sessions using the service with progress tracking
            result = create_audit_sessions(
                facade=facade,
                opportunity_ids=opportunity_ids,
                criteria=criteria,
                auditor_username=auditor_username,
                progress_tracker=progress_tracker,
            )

            if not result.success:
                progress_tracker.error(result.error)
                return

            # Redirect to the first session if only one, otherwise to the list
            if result.sessions_created == 1:
                redirect_url = reverse_lazy("audit:session_detail", kwargs={"pk": result.first_session.pk})
            else:
                redirect_url = reverse_lazy("audit:session_list")

            # Mark as complete with result data
            progress_tracker.complete(
                "Audit created successfully!",
                result_data={
                    "redirect_url": str(redirect_url),
                    "sessions_created": result.sessions_created,
                    "stats": result.stats,
                },
            )

        except Exception as e:
            import traceback

            progress_tracker.error(str(e), traceback.format_exc())
        finally:
            if facade:
                facade.close()

    def post(self, request):
        try:
            data = json.loads(request.body)
            opportunity_ids = data.get("opportunities", [])
            criteria = data.get("criteria", {})

            if not opportunity_ids or not criteria:
                return JsonResponse({"error": "Missing required data"}, status=400)

            # Use username or email as auditor identifier
            auditor_username = request.user.username or request.user.email

            # Initialize progress tracker and set initial state in cache
            progress_tracker = ProgressTracker()
            progress_tracker.update(0, 5, "Starting audit creation...", "initializing")

            # Start the audit creation in a background thread
            thread = threading.Thread(
                target=self._run_audit_creation_in_background,
                args=(progress_tracker.task_id, opportunity_ids, criteria, auditor_username),
                daemon=True,
            )
            thread.start()

            # Return task_id immediately so client can start polling
            return JsonResponse(
                {
                    "success": True,
                    "task_id": progress_tracker.task_id,
                }
            )

        except Exception as e:
            import traceback

            return JsonResponse({"error": str(e), "traceback": traceback.format_exc()}, status=500)


class AuditProgressAPIView(LoginRequiredMixin, View):
    """API endpoint for polling audit creation progress"""

    def get(self, request):
        task_id = request.GET.get("task_id")
        if not task_id:
            return JsonResponse({"error": "Missing task_id"}, status=400)

        progress_tracker = ProgressTracker(task_id=task_id)
        progress_data = progress_tracker.get_progress()

        if progress_data is None:
            return JsonResponse({"error": "Task not found"}, status=404)

        return JsonResponse(progress_data)

    def delete(self, request):
        """Cancel an in-progress audit creation"""
        task_id = request.GET.get("task_id")
        if not task_id:
            return JsonResponse({"error": "Missing task_id"}, status=400)

        progress_tracker = ProgressTracker(task_id=task_id)
        progress_tracker.cancel()

        return JsonResponse({"success": True, "message": "Cancellation requested"})


class DatabaseStatsAPIView(LoginRequiredMixin, View):
    """API endpoint for getting database statistics"""

    def get(self, request):
        try:
            stats = get_database_stats()
            return JsonResponse({"success": True, "stats": stats})

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


class DatabaseResetAPIView(LoginRequiredMixin, View):
    """API endpoint for resetting audit-related database tables"""

    def post(self, request):
        try:
            deleted = reset_audit_database()
            return JsonResponse({"success": True, "deleted": deleted})

        except Exception as e:
            import traceback

            return JsonResponse({"error": str(e), "traceback": traceback.format_exc()}, status=500)
