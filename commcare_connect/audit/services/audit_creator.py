"""
Audit Creation Service

This service orchestrates the complete audit creation workflow:
1. Creating opportunities
2. Loading users
3. Loading visits based on criteria
4. Creating audit sessions (with support for different granularities)
5. Downloading attachments
"""

from typing import Any

from commcare_connect.audit.management.extractors.connect_api_facade import ConnectAPIFacade
from commcare_connect.audit.models import AuditSession
from commcare_connect.audit.services.data_loader import AuditDataLoader
from commcare_connect.audit.services.progress_tracker import ProgressTracker


class AuditCreationResult:
    """Result of audit creation operation"""

    def __init__(self, success: bool, sessions: list[AuditSession] = None, stats: dict = None, error: str = None):
        self.success = success
        self.sessions = sessions or []
        self.stats = stats or {}
        self.error = error

    @property
    def sessions_created(self) -> int:
        return len(self.sessions)

    @property
    def first_session(self) -> AuditSession | None:
        return self.sessions[0] if self.sessions else None


class AuditPreviewResult:
    """Result of audit preview operation"""

    def __init__(self, success: bool, preview_data: list[dict] = None, error: str = None):
        self.success = success
        self.preview_data = preview_data or []
        self.error = error


def create_audit_sessions(
    facade: ConnectAPIFacade,
    opportunity_ids: list[int],
    criteria: dict[str, Any],
    auditor_username: str,
    limit_flws: int | None = None,
    progress_tracker: ProgressTracker | None = None,
) -> AuditCreationResult:
    """
    Create audit sessions based on provided criteria.

    Args:
        facade: Authenticated ConnectAPIFacade instance
        opportunity_ids: List of opportunity IDs to audit
        criteria: Dictionary containing audit criteria:
            - type: 'date_range', 'last_n_per_flw', or 'last_n_across_opp'
            - granularity: 'combined', 'per_opp', or 'per_flw'
            - startDate/endDate: For date_range type
            - countPerFlw: For last_n_per_flw type
            - countAcrossOpp: For last_n_across_opp type
        auditor_username: Username of person creating the audit
        limit_flws: Optional limit on number of FLWs to process (for testing)

    Returns:
        AuditCreationResult with sessions, stats, and success status
    """
    try:
        # Extract audit parameters
        audit_type = criteria.get("type")
        granularity = criteria.get("granularity", "combined")
        start_date = criteria.get("startDate") if audit_type == "date_range" else None
        end_date = criteria.get("endDate") if audit_type == "date_range" else None
        count_per_flw = criteria.get("countPerFlw") if audit_type == "last_n_per_flw" else None
        count_across_opp = criteria.get("countAcrossOpp") if audit_type == "last_n_across_opp" else None
        sample_cache_key = criteria.get("sampleCacheKey")

        # Check if we're using a pre-sampled visit list
        sampled_visit_ids = None
        if sample_cache_key:
            from django.core.cache import cache

            sampled_visit_ids = cache.get(sample_cache_key)
            if sampled_visit_ids:
                print(f"[INFO] Using pre-sampled visit IDs from cache ({len(sampled_visit_ids)} visits)")
            else:
                return AuditCreationResult(
                    success=False, error="Sample expired or not found. Please preview again before creating audit."
                )

        # Initialize data loader
        loader = AuditDataLoader(facade=facade, dry_run=False)

        # Step 1: Create minimal opportunities for FK integrity
        if progress_tracker:
            progress_tracker.update(0, 100, "Loading opportunities...", "loading", step_name="opportunities")
        print("  Creating opportunities...")
        opportunities = loader.create_minimal_opportunities(opportunity_ids)
        if progress_tracker:
            progress_tracker.complete_step("opportunities", "Opportunities loaded")

        # Build opportunity name for display
        def get_opportunity_name(opp_ids: list[int]) -> str:
            """Get a display name for one or more opportunities"""
            opp_list = [opportunities.get(opp_id) for opp_id in opp_ids if opportunities.get(opp_id)]
            if not opp_list:
                return f"{len(opp_ids)} opportunities"
            elif len(opp_list) == 1:
                return opp_list[0].name
            else:
                # For multiple, show first 2 and count if more
                names = [opp.name for opp in opp_list[:2]]
                if len(opp_list) > 2:
                    return f"{', '.join(names)} (+{len(opp_list) - 2} more)"
                return ", ".join(names)

        # Step 2: Load users
        if progress_tracker:
            progress_tracker.update(0, 100, "Loading users...", "loading", step_name="users")
        print("  Loading users from Superset...")
        users = loader.load_users(opportunity_ids)
        print(f"  Loaded {len(users)} users")
        if progress_tracker:
            progress_tracker.complete_step("users", f"Loaded {len(users)} users")

        # Step 3: Load visits and create sessions based on granularity
        if progress_tracker:
            progress_tracker.update(
                0, 100, "Loading visits and creating sessions...", "processing", step_name="sessions"
            )
        created_sessions = []
        all_visits = []  # Track all visits for image downloading

        if granularity == "combined":
            # One audit for all opportunities combined
            if progress_tracker:
                progress_tracker.update(0, 100, "Loading visits...", "processing", step_name="sessions")

            # Load visits - either from cache (sampled) or fresh query
            if sampled_visit_ids:
                visits = loader.load_visits_by_ids(sampled_visit_ids)
            else:
                visits = loader.load_visits(
                    opportunity_ids=opportunity_ids,
                    audit_type=audit_type,
                    start_date=start_date,
                    end_date=end_date,
                    count=count_per_flw or count_across_opp,
                )
            all_visits.extend(visits)

            if progress_tracker:
                progress_tracker.update(50, 100, "Creating audit session...", "processing", step_name="sessions")

            # Calculate actual date range from loaded visits
            session_start = start_date
            session_end = end_date
            if visits and (start_date is None or end_date is None):
                visit_dates = [
                    v.visit_date.date() if hasattr(v.visit_date, "date") else v.visit_date
                    for v in visits
                    if v.visit_date
                ]
                if visit_dates:
                    session_start = min(visit_dates)
                    session_end = max(visit_dates)

            session = loader.create_audit_session(
                auditor_username=auditor_username,
                opportunity_ids=opportunity_ids,
                granularity="combined",
                audit_type=audit_type,
                start_date=session_start,
                end_date=session_end,
                count=count_per_flw or count_across_opp,
                opportunity_name=get_opportunity_name(opportunity_ids),
            )
            # Explicitly assign the loaded visits to this session
            session.visits.set(visits)
            created_sessions.append(session)

            if progress_tracker:
                progress_tracker.update(100, 100, "Session created", "processing", step_name="sessions")

        elif granularity == "per_opp":
            # One audit per opportunity
            for idx, opp_id in enumerate(opportunity_ids, 1):
                if progress_tracker:
                    progress_tracker.update(
                        idx,
                        len(opportunity_ids),
                        f"Creating audit for opportunity {idx}/{len(opportunity_ids)}",
                        "processing",
                        step_name="sessions",
                    )

                # Load visits - either from cache (sampled) or fresh query
                if sampled_visit_ids:
                    # Filter sampled IDs for this opportunity
                    # We need to check which IDs belong to this opportunity
                    visits = loader.load_visits_by_ids(sampled_visit_ids)
                    visits = [v for v in visits if v.opportunity_id == opp_id]
                else:
                    visits = loader.load_visits(
                        opportunity_ids=[opp_id],
                        audit_type=audit_type,
                        start_date=start_date,
                        end_date=end_date,
                        count=count_per_flw or count_across_opp,
                    )
                all_visits.extend(visits)

                # Calculate actual date range from loaded visits
                session_start = start_date
                session_end = end_date
                if visits and (start_date is None or end_date is None):
                    visit_dates = [
                        v.visit_date.date() if hasattr(v.visit_date, "date") else v.visit_date
                        for v in visits
                        if v.visit_date
                    ]
                    if visit_dates:
                        session_start = min(visit_dates)
                        session_end = max(visit_dates)

                session = loader.create_audit_session(
                    auditor_username=auditor_username,
                    opportunity_ids=[opp_id],
                    granularity="per_opp",
                    audit_type=audit_type,
                    start_date=session_start,
                    end_date=session_end,
                    count=count_per_flw or count_across_opp,
                    opportunity_name=get_opportunity_name([opp_id]),
                )
                # Explicitly assign the loaded visits to this session
                session.visits.set(visits)
                created_sessions.append(session)

        elif granularity == "per_flw":
            # One audit per FLW across all opportunities
            print("  Fetching FLW list from Superset...")
            flws = facade.get_unique_flws_across_opportunities(opportunity_ids)
            print(f"  Found {len(flws)} FLWs")

            # Apply limit if specified (useful for integration testing)
            if limit_flws and len(flws) > limit_flws:
                flws = flws[:limit_flws]

            print(f"  Creating audit sessions for {len(flws)} FLWs...")
            for idx, flw in enumerate(flws, 1):
                # Check for cancellation
                if progress_tracker and progress_tracker.is_cancelled():
                    print("  Audit creation cancelled by user")
                    return AuditCreationResult(success=False, error="Cancelled by user")

                user_id = flw["user_id"]

                if idx % 10 == 1 or idx == len(flws):
                    print(f"    Processing FLW {idx}/{len(flws)} ({flw.get('username', 'unknown')})")

                # Update progress for per-FLW mode
                if progress_tracker and len(flws) > 1:
                    progress_tracker.update(
                        idx,
                        len(flws),
                        f"Creating audit for FLW {idx}/{len(flws)}: {flw.get('username', 'unknown')}",
                        "processing",
                        step_name="sessions",
                    )

                # Load visits - either from cache (sampled) or fresh query
                if sampled_visit_ids:
                    # Filter sampled IDs for this FLW
                    visits = loader.load_visits_by_ids(sampled_visit_ids)
                    visits = [v for v in visits if v.user_id == user_id]
                else:
                    visits = loader.load_visits(
                        opportunity_ids=opportunity_ids,
                        audit_type=audit_type,
                        start_date=start_date,
                        end_date=end_date,
                        count=count_per_flw or count_across_opp,
                        user_id=user_id,
                    )
                all_visits.extend(visits)

                # Determine which opportunities this FLW actually has visits in
                flw_opportunity_ids = list({v.opportunity_id for v in visits if v.opportunity_id})

                # Skip if no visits found for this FLW
                if not visits or not flw_opportunity_ids:
                    continue

                # Calculate actual date range from loaded visits (important for last_n type audits)
                session_start = start_date
                session_end = end_date
                if visits and (start_date is None or end_date is None):
                    visit_dates = [
                        v.visit_date.date() if hasattr(v.visit_date, "date") else v.visit_date
                        for v in visits
                        if v.visit_date
                    ]
                    if visit_dates:
                        session_start = min(visit_dates)
                        session_end = max(visit_dates)

                session = loader.create_audit_session(
                    auditor_username=auditor_username,
                    opportunity_ids=flw_opportunity_ids,  # Use only the opportunities this FLW has visits in
                    granularity="per_flw",
                    audit_type=audit_type,
                    start_date=session_start,
                    end_date=session_end,
                    count=count_per_flw or count_across_opp,
                    flw_username=flw.get("username"),
                    opportunity_name=get_opportunity_name(
                        flw_opportunity_ids
                    ),  # Generate name from FLW's actual opportunities
                )
                # Explicitly assign the loaded visits to this session
                session.visits.set(visits)
                created_sessions.append(session)

        # Mark sessions step as complete
        if progress_tracker:
            progress_tracker.complete_step("sessions", f"Created {len(created_sessions)} session(s)")

        # Step 4: Download attachments synchronously for all loaded visits
        # Remove duplicates (visits may be loaded multiple times in per_flw mode)
        unique_visits = list({v.id: v for v in all_visits}.values())

        # Check for cancellation before downloading
        if progress_tracker and progress_tracker.is_cancelled():
            print("  Audit creation cancelled by user before downloading attachments")
            return AuditCreationResult(success=False, error="Cancelled by user")

        # Download with progress tracking (the download_attachments method will handle progress updates)
        if progress_tracker:
            progress_tracker.update(
                0, len(unique_visits) or 1, "Starting attachment download...", "downloading", step_name="attachments"
            )
        loader.download_attachments(unique_visits, progress_tracker=progress_tracker)

        # Mark attachments step as complete
        if progress_tracker:
            progress_tracker.complete_step("attachments", "All attachments downloaded")

        # Complete progress tracking
        if progress_tracker:
            progress_tracker.update(100, 100, "Audit creation completed!", "complete")

        # Get statistics
        stats = loader.get_stats()

        return AuditCreationResult(success=True, sessions=created_sessions, stats=stats)

    except Exception as e:
        return AuditCreationResult(success=False, error=str(e))


def preview_audit_sessions(
    facade: ConnectAPIFacade,
    opportunity_ids: list[int],
    criteria: dict[str, Any],
) -> AuditPreviewResult:
    """
    Preview what audit sessions would be created based on criteria.

    This uses the same logic as create_audit_sessions to ensure preview
    accurately reflects what will be created.

    For sampling < 100%, this loads lightweight visit IDs, samples them,
    caches the sampled IDs, and returns the cache key for creation to use.

    Args:
        facade: Authenticated ConnectAPIFacade instance
        opportunity_ids: List of opportunity IDs to audit
        criteria: Dictionary containing audit criteria (same format as create_audit_sessions)
            - samplePercentage: Optional percentage to sample (1-100, default 100)

    Returns:
        AuditPreviewResult with preview data for each opportunity/granularity
    """
    try:
        # Extract audit parameters (same as create_audit_sessions)
        audit_type = criteria.get("type")
        granularity = criteria.get("granularity", "combined")
        start_date = criteria.get("startDate") if audit_type == "date_range" else None
        end_date = criteria.get("endDate") if audit_type == "date_range" else None
        count_per_flw = criteria.get("countPerFlw") if audit_type == "last_n_per_flw" else None
        count_across_opp = criteria.get("countAcrossOpp") if audit_type == "last_n_across_opp" else None
        sample_percentage = criteria.get("samplePercentage", 100)

        # Check if we need to sample
        needs_sampling = sample_percentage < 100

        # If sampling, load visit IDs and sample them
        sample_cache_key = None
        sampled_visit_counts_by_opp = {}  # Track actual sampled counts per opportunity
        if needs_sampling:
            print(f"[INFO] Sampling enabled: {sample_percentage}%")
            print("[INFO] Loading visit IDs for sampling...")

            # Load lightweight visit IDs (fast, minimal memory)
            # Track which opportunity each visit belongs to for accurate preview counts
            visit_id_to_opp = {}  # Map visit_id -> opportunity_id
            all_visit_ids = []

            if granularity == "per_flw":
                # For per_flw, we need to load IDs per FLW
                flws = facade.get_unique_flws_across_opportunities(opportunity_ids)
                for flw in flws:
                    user_id = flw["user_id"]
                    visit_ids = facade.get_user_visit_ids_for_audit(
                        opportunity_ids=opportunity_ids,
                        audit_type=audit_type,
                        start_date=start_date,
                        end_date=end_date,
                        count=count_per_flw or count_across_opp,
                        user_id=user_id,
                    )
                    all_visit_ids.extend(visit_ids)
            else:
                # For combined/per_opp, load all visit IDs and track their opportunity
                for opp_id in opportunity_ids:
                    visit_ids = facade.get_user_visit_ids_for_audit(
                        opportunity_ids=[opp_id],
                        audit_type=audit_type,
                        start_date=start_date,
                        end_date=end_date,
                        count=count_per_flw or count_across_opp,
                    )
                    # Track which opportunity these visits belong to
                    for vid in visit_ids:
                        visit_id_to_opp[vid] = opp_id
                    all_visit_ids.extend(visit_ids)

            # Remove duplicates (visits may appear in multiple opportunity queries)
            all_visit_ids = list(set(all_visit_ids))
            print(f"[INFO] Loaded {len(all_visit_ids)} visit IDs")

            # Sample the IDs
            import random
            import uuid

            sample_size = int(len(all_visit_ids) * sample_percentage / 100)
            sampled_visit_ids = (
                random.sample(all_visit_ids, sample_size) if sample_size < len(all_visit_ids) else all_visit_ids
            )
            print(f"[INFO] Sampled {len(sampled_visit_ids)} visit IDs ({sample_percentage}%)")

            # Count actual sampled visits per opportunity
            for vid in sampled_visit_ids:
                opp_id = visit_id_to_opp.get(vid)
                if opp_id:
                    sampled_visit_counts_by_opp[opp_id] = sampled_visit_counts_by_opp.get(opp_id, 0) + 1

            # Cache the sampled IDs with 1 hour expiry
            from django.core.cache import cache

            sample_cache_key = f"audit_sample_{uuid.uuid4()}"
            cache.set(sample_cache_key, sampled_visit_ids, timeout=3600)
            print(f"[INFO] Cached sampled visit IDs with key: {sample_cache_key}")

        preview_data = []

        # Get opportunity details for preview
        for opp_id in opportunity_ids:
            opportunities = facade.search_opportunities(str(opp_id), 1)
            if not opportunities:
                continue

            opportunity = opportunities[0]

            # Get FLW and visit counts based on criteria
            # These are the same methods that will be called during actual creation
            if audit_type == "date_range":
                counts = facade.get_flw_visit_counts_by_date_range(opp_id, start_date, end_date)
            elif audit_type == "last_n_per_flw":
                counts = facade.get_flw_visit_counts_last_n_per_flw(opp_id, count_per_flw)
            elif audit_type == "last_n_across_opp":
                counts = facade.get_flw_visit_counts_last_n_across_opp(opp_id, count_across_opp)
            else:
                continue

            # Calculate how many sessions would be created based on granularity
            sessions_to_create = 1  # Default for combined/per_opp
            if granularity == "per_flw":
                sessions_to_create = counts["total_flws"]

            # Get actual sampled visit count for this opportunity
            total_visits_before_sampling = counts["total_visits"]
            if needs_sampling and opp_id in sampled_visit_counts_by_opp:
                # Use ACTUAL sampled count (exact)
                total_visits_after_sampling = sampled_visit_counts_by_opp[opp_id]
            elif needs_sampling:
                # Fallback to approximation if tracking failed (e.g., per_flw granularity)
                total_visits_after_sampling = int(total_visits_before_sampling * sample_percentage / 100)
            else:
                # No sampling
                total_visits_after_sampling = total_visits_before_sampling

            preview_item = {
                "opportunity_id": opp_id,
                "opportunity_name": opportunity.name,
                "total_flws": counts["total_flws"],
                "total_visits": total_visits_after_sampling,  # Show actual sampled count
                "total_visits_before_sampling": total_visits_before_sampling if needs_sampling else None,
                "sample_percentage": sample_percentage if needs_sampling else None,
                "avg_visits_per_flw": round(total_visits_after_sampling / max(counts["total_flws"], 1), 1),
                "date_range": counts.get("date_range"),
                "flws": counts.get("flws", []),
                "sessions_to_create": sessions_to_create,
                "granularity": granularity,
                "audit_type": audit_type,
            }

            # Add cache key to first preview item (it's shared across all opportunities)
            if needs_sampling and sample_cache_key and len(preview_data) == 0:
                preview_item["sample_cache_key"] = sample_cache_key

            preview_data.append(preview_item)

        return AuditPreviewResult(success=True, preview_data=preview_data)

    except Exception as e:
        import traceback

        return AuditPreviewResult(success=False, error=f"{str(e)}\n{traceback.format_exc()}")
