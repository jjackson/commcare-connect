"""
Celery tasks for asynchronous audit creation.

Provides async audit creation with:
- Multi-stage progress tracking
- SSE streaming support
- Workflow integration
"""

import logging
import time

from commcare_connect.utils.celery import set_task_progress
from config import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True)
def test_async_simple(self, sleep_seconds: int = 3) -> dict:
    """
    Simple test task for verifying async behavior.

    Used by test_async_audit management command to verify Celery is working.
    """
    set_task_progress(self, "Starting...", current_stage=1, total_stages=3)
    time.sleep(sleep_seconds / 3)

    set_task_progress(self, "Working...", current_stage=2, total_stages=3)
    time.sleep(sleep_seconds / 3)

    set_task_progress(self, "Finishing...", current_stage=3, total_stages=3)
    time.sleep(sleep_seconds / 3)

    return {"success": True, "message": "Test completed"}


def _update_job_progress(
    data_access,
    task_id: str,
    username: str,
    status: str = "running",
    current_stage: int = 0,
    total_stages: int = 4,
    stage_name: str = "",
    message: str = "",
    processed: int = 0,
    total: int = 0,
    result: dict | None = None,
    error: str | None = None,
):
    """Update the job record with progress."""
    try:
        job = data_access.get_audit_creation_job_by_task_id(task_id)
        if job:
            data_access.update_audit_creation_job(
                job_id=job["id"],
                username=username,
                status=status,
                progress={
                    "current_stage": current_stage,
                    "total_stages": total_stages,
                    "stage_name": stage_name,
                    "message": message,
                    "processed": processed,
                    "total": total,
                },
                result=result,
                error=error,
            )
    except Exception as e:
        logger.warning(f"[AuditCreation] Failed to update job progress: {e}")


def _run_ai_review_on_sessions(
    data_access,
    session_ids: list[int],
    ai_agent_id: str,
    access_token: str,
    opp_id: int,
) -> dict:
    """
    Run AI review agent on the specified audit sessions.

    This runs the AI agent on each image in the session that has related field data.
    Results are logged but not yet persisted to the session (future enhancement).

    Args:
        data_access: AuditDataAccess instance
        session_ids: List of session IDs to review
        ai_agent_id: ID of the AI agent to use
        access_token: OAuth token for API access
        opp_id: Opportunity ID

    Returns:
        Dict with review results summary
    """
    from commcare_connect.labs.ai_review_agents.registry import get_agent
    from commcare_connect.labs.ai_review_agents.types import ReviewContext

    # Get the agent
    agent = get_agent(ai_agent_id)
    logger.info(f"[AIReview] Running agent '{ai_agent_id}' on {len(session_ids)} sessions")

    total_reviewed = 0
    total_passed = 0
    total_failed = 0
    total_errors = 0
    total_skipped = 0

    for session_id in session_ids:
        try:
            # Get session data
            session = data_access.get_audit_session(session_id)
            if not session:
                logger.warning(f"[AIReview] Session {session_id} not found")
                continue

            # Get visit_images from session data
            # This contains the images and their related field data
            visit_images = session.data.get("visit_images", {})
            if not visit_images:
                logger.info(f"[AIReview] Session {session_id} has no visit_images")
                continue

            # Iterate through visits and their images
            for visit_id_str, images in visit_images.items():
                for image_data in images:
                    try:
                        blob_id = image_data.get("blob_id")
                        if not blob_id:
                            continue

                        # Get reading from related_fields
                        # The related_fields structure is: [{label, value, field_path}, ...]
                        related_fields = image_data.get("related_fields", [])
                        reading = None
                        for rf in related_fields:
                            if rf.get("value"):
                                reading = str(rf.get("value"))
                                break

                        if not reading:
                            total_skipped += 1
                            continue

                        # Fetch the image from Connect API
                        try:
                            image_bytes = data_access.download_image_from_connect(blob_id, opp_id)
                            if not image_bytes:
                                total_skipped += 1
                                continue
                        except Exception as e:
                            logger.warning(f"[AIReview] Failed to fetch image {blob_id}: {e}")
                            total_skipped += 1
                            continue

                        # Create review context
                        context = ReviewContext(
                            images={"scale": image_bytes},
                            form_data={"reading": reading},
                            metadata={
                                "visit_id": visit_id_str,
                                "blob_id": blob_id,
                                "opportunity_id": opp_id,
                                "session_id": session_id,
                            },
                        )

                        # Run review
                        result = agent.review(context)
                        total_reviewed += 1

                        if result.passed:
                            total_passed += 1
                            logger.debug(f"[AIReview] PASS: blob={blob_id}, reading={reading}")
                        elif result.failed:
                            total_failed += 1
                            logger.debug(f"[AIReview] FAIL: blob={blob_id}, reading={reading}")
                        else:
                            total_errors += 1
                            logger.debug(f"[AIReview] ERROR: blob={blob_id}, errors={result.errors}")

                    except Exception as e:
                        logger.warning(f"[AIReview] Failed to review image: {e}")
                        total_errors += 1

        except Exception as e:
            logger.warning(f"[AIReview] Failed to process session {session_id}: {e}")

    logger.info(
        f"[AIReview] Complete: reviewed={total_reviewed}, "
        f"passed={total_passed}, failed={total_failed}, errors={total_errors}, skipped={total_skipped}"
    )

    return {
        "agent_id": ai_agent_id,
        "agent_name": agent.name,
        "sessions_processed": len(session_ids),
        "total_reviewed": total_reviewed,
        "total_passed": total_passed,
        "total_failed": total_failed,
        "total_errors": total_errors,
        "total_skipped": total_skipped,
    }


@celery_app.task(bind=True)
def run_audit_creation(
    self,
    access_token: str,
    username: str,
    opportunities: list[dict],
    criteria: dict,
    visit_ids: list[int] | None = None,
    flw_visit_ids: dict | None = None,
    template_overrides: dict | None = None,
    workflow_run_id: int | None = None,
    ai_agent_id: str | None = None,
) -> dict:
    """
    Create audit template and session(s) asynchronously.

    Stages:
    1. Fetch visit IDs (if not provided)
    2. Extract images with related fields
    3. Create template
    4. Create session(s)
    5. Run AI review agent (if specified)

    Args:
        access_token: OAuth token for API calls
        username: User creating the audit
        opportunities: List of opportunity dicts with id and name
        criteria: Audit criteria dict
        visit_ids: Pre-computed visit IDs (optional, skips fetch)
        flw_visit_ids: Pre-computed FLW->visit_ids mapping (optional)
        template_overrides: Values to override in criteria (from workflow)
        workflow_run_id: Workflow run ID if triggered from workflow
        ai_agent_id: Optional AI review agent to run after creation

    Returns:
        Result dict with template_id, session_ids, etc.
    """
    from commcare_connect.audit.data_access import AuditCriteria, AuditDataAccess, create_mock_request

    # Apply template overrides
    if template_overrides:
        criteria = {**criteria, **template_overrides}

    opportunity_ids = [o["id"] for o in opportunities]
    opp_id = opportunity_ids[0] if opportunity_ids else None
    task_id = self.request.id

    logger.info(
        f"[AuditCreation] Starting async audit creation: "
        f"opportunities={opportunity_ids}, user={username}, task_id={task_id}"
    )

    # Parse criteria
    audit_criteria = AuditCriteria.from_dict(criteria)
    granularity = criteria.get("granularity", "combined")
    audit_type = audit_criteria.audit_type
    related_fields = audit_criteria.related_fields or []

    # DEBUG: Log the parsed criteria
    logger.info(
        f"[AuditCreation] Parsed criteria: audit_type={audit_type}, "
        f"count_across_all={audit_criteria.count_across_all}, "
        f"count_per_flw={audit_criteria.count_per_flw}, "
        f"count_per_opp={audit_criteria.count_per_opp}, "
        f"sample_percentage={audit_criteria.sample_percentage}"
    )
    logger.info(f"[AuditCreation] Raw criteria from frontend: {criteria}")

    # Determine stages
    needs_visit_fetch = not visit_ids
    is_per_flw = granularity == "per_flw"
    has_ai_agent = bool(ai_agent_id)
    # Base stages: (fetch visits) + extract images + create template + create sessions + (AI review)
    total_stages = 4 if needs_visit_fetch else 3
    if has_ai_agent:
        total_stages += 1  # Add AI review stage

    set_task_progress(
        self,
        "Initializing...",
        current_stage=1,
        total_stages=total_stages,
        stage_name="Initializing",
    )

    try:
        # Initialize data access
        mock_request = create_mock_request(access_token, opp_id)
        data_access = AuditDataAccess(opportunity_id=opp_id, request=mock_request)

        # Update job to running status
        _update_job_progress(
            data_access,
            task_id,
            username,
            status="running",
            current_stage=1,
            total_stages=total_stages,
            stage_name="Initializing",
            message="Starting audit creation...",
        )

        current_stage = 1

        # =========================================================================
        # STAGE 1: Fetch visit IDs (if not provided)
        # =========================================================================
        if needs_visit_fetch:
            msg = f"Stage {current_stage}/{total_stages}: Fetching visit IDs..."
            set_task_progress(
                self, msg, current_stage=current_stage, total_stages=total_stages, stage_name="Fetching visits"
            )
            _update_job_progress(
                data_access,
                task_id,
                username,
                status="running",
                current_stage=current_stage,
                total_stages=total_stages,
                stage_name="Fetching visits",
                message=msg,
            )

            visit_ids = data_access.get_visit_ids_for_audit(opportunity_ids, audit_criteria)
            logger.info(f"[AuditCreation] Fetched {len(visit_ids)} visit IDs")

            current_stage += 1

        # Filter to selected FLWs if provided
        selected_flw_user_ids = criteria.get("selected_flw_user_ids", [])
        if selected_flw_user_ids and flw_visit_ids:
            # Use only visits from selected FLWs
            visit_ids = []
            for flw_id in selected_flw_user_ids:
                visit_ids.extend(flw_visit_ids.get(flw_id, []))
            visit_ids = list(set(visit_ids))
            logger.info(f"[AuditCreation] Filtered to {len(visit_ids)} visits for selected FLWs")

        # =========================================================================
        # STAGE 2: Extract images
        # =========================================================================
        msg = f"Stage {current_stage}/{total_stages}: Extracting images..."
        set_task_progress(
            self, msg, current_stage=current_stage, total_stages=total_stages, stage_name="Extracting images"
        )
        _update_job_progress(
            data_access,
            task_id,
            username,
            status="running",
            current_stage=current_stage,
            total_stages=total_stages,
            stage_name="Extracting images",
            message=msg,
        )

        all_visit_images = data_access.extract_images_for_visits(visit_ids, opp_id, related_fields=related_fields)
        image_count = sum(len(imgs) for imgs in all_visit_images.values())
        logger.info(f"[AuditCreation] Extracted {image_count} images from {len(visit_ids)} visits")

        current_stage += 1

        # =========================================================================
        # STAGE 3: Create template
        # =========================================================================
        msg = f"Stage {current_stage}/{total_stages}: Creating template..."
        set_task_progress(
            self, msg, current_stage=current_stage, total_stages=total_stages, stage_name="Creating template"
        )
        _update_job_progress(
            data_access,
            task_id,
            username,
            status="running",
            current_stage=current_stage,
            total_stages=total_stages,
            stage_name="Creating template",
            message=msg,
        )

        template = data_access.create_audit_template(
            username=username,
            opportunity_ids=opportunity_ids,
            audit_type=audit_type,
            granularity=granularity,
            criteria=audit_criteria,
        )
        logger.info(f"[AuditCreation] Created template {template.id}")

        current_stage += 1

        # =========================================================================
        # STAGE 4: Create session(s)
        # =========================================================================
        msg = f"Stage {current_stage}/{total_stages}: Creating session(s)..."
        set_task_progress(
            self, msg, current_stage=current_stage, total_stages=total_stages, stage_name="Creating sessions"
        )
        _update_job_progress(
            data_access,
            task_id,
            username,
            status="running",
            current_stage=current_stage,
            total_stages=total_stages,
            stage_name="Creating sessions",
            message=msg,
        )

        sessions_created = []
        session_title = criteria.get("title", "")
        session_tag = criteria.get("tag", "")

        if is_per_flw and flw_visit_ids and selected_flw_user_ids:
            # Create one session per FLW
            total_flws = len(selected_flw_user_ids)
            for idx, flw_id in enumerate(selected_flw_user_ids):
                flw_visit_list = flw_visit_ids.get(flw_id, [])
                if not flw_visit_list:
                    continue

                # Filter images to this FLW's visits
                flw_images = {str(vid): all_visit_images.get(str(vid), []) for vid in flw_visit_list}

                flw_title = f"{flw_id} - {session_title}" if session_title else flw_id

                session = data_access.create_audit_session(
                    template_id=template.id,
                    username=username,
                    visit_ids=flw_visit_list,
                    title=flw_title,
                    tag=session_tag,
                    opportunity_id=opp_id,
                    criteria=audit_criteria,
                    opportunity_name=opportunities[0].get("name") if opportunities else None,
                    visit_images=flw_images,
                    related_fields=related_fields,
                )

                sessions_created.append(
                    {
                        "id": session.id,
                        "title": flw_title,
                        "visits": len(flw_visit_list),
                        "images": sum(len(imgs) for imgs in flw_images.values()),
                    }
                )

                set_task_progress(
                    self,
                    f"Stage {current_stage}/{total_stages}: Created session {idx + 1}/{total_flws}",
                    current_stage=current_stage,
                    total_stages=total_stages,
                    stage_name="Creating sessions",
                    processed=idx + 1,
                    total=total_flws,
                )

            logger.info(f"[AuditCreation] Created {len(sessions_created)} per-FLW sessions")
        else:
            # Create single combined session
            opp_name = opportunities[0].get("name") if opportunities else ""
            combined_title = f"{opp_name} - {session_title}" if session_title else opp_name

            session = data_access.create_audit_session(
                template_id=template.id,
                username=username,
                visit_ids=visit_ids,
                title=combined_title,
                tag=session_tag,
                opportunity_id=opp_id,
                criteria=audit_criteria,
                opportunity_name=opp_name,
                visit_images=all_visit_images,
                related_fields=related_fields,
            )

            sessions_created.append(
                {
                    "id": session.id,
                    "title": combined_title,
                    "visits": len(visit_ids),
                    "images": image_count,
                }
            )

            logger.info(f"[AuditCreation] Created combined session {session.id}")

        current_stage += 1

        # =========================================================================
        # STAGE 5 (optional): Run AI Review Agent
        # =========================================================================
        ai_review_results = None
        if has_ai_agent and sessions_created:
            msg = f"Stage {current_stage}/{total_stages}: Running AI review..."
            set_task_progress(
                self, msg, current_stage=current_stage, total_stages=total_stages, stage_name="AI Review"
            )
            _update_job_progress(
                data_access,
                task_id,
                username,
                status="running",
                current_stage=current_stage,
                total_stages=total_stages,
                stage_name="AI Review",
                message=msg,
            )

            try:
                ai_review_results = _run_ai_review_on_sessions(
                    data_access=data_access,
                    session_ids=[s["id"] for s in sessions_created],
                    ai_agent_id=ai_agent_id,
                    access_token=access_token,
                    opp_id=opp_id,
                )
                logger.info(f"[AuditCreation] AI review complete: {ai_review_results}")
            except Exception as e:
                logger.warning(f"[AuditCreation] AI review failed (non-fatal): {e}")
                ai_review_results = {"error": str(e)}

            current_stage += 1

        # Mark complete
        result = {
            "success": True,
            "template_id": template.id,
            "sessions": sessions_created,
            "total_visits": sum(s["visits"] for s in sessions_created),
            "total_images": sum(s["images"] for s in sessions_created),
        }
        if ai_review_results:
            result["ai_review"] = ai_review_results

        set_task_progress(
            self,
            "Complete",
            is_complete=True,
            current_stage=total_stages,
            total_stages=total_stages,
            stage_name="Complete",
            result=result,
        )

        # Update job record to completed
        _update_job_progress(
            data_access,
            task_id,
            username,
            status="completed",
            current_stage=total_stages,
            total_stages=total_stages,
            stage_name="Complete",
            message="Audit creation complete",
            result=result,
        )

        data_access.close()

        logger.info(
            f"[AuditCreation] Complete: {len(sessions_created)} sessions, "
            f"{result['total_visits']} visits, {result['total_images']} images"
        )

        return result

    except Exception as e:
        logger.error(f"[AuditCreation] Failed: {e}", exc_info=True)
        set_task_progress(
            self,
            f"Failed: {str(e)}",
            is_complete=True,
            error=str(e),
        )

        # Try to update job record to failed
        try:
            mock_request = create_mock_request(access_token, opp_id)
            err_data_access = AuditDataAccess(opportunity_id=opp_id, request=mock_request)
            _update_job_progress(
                err_data_access,
                task_id,
                username,
                status="failed",
                error=str(e),
            )
            err_data_access.close()
        except Exception:
            pass

        raise
