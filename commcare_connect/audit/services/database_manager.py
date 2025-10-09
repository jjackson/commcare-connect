"""
Database Management Service for Audit Application

This service handles database cleanup and management operations for the audit system.
"""

from django.contrib.auth import get_user_model
from django.db import transaction

from commcare_connect.audit.models import AuditDefinition, AuditSession
from commcare_connect.opportunity.models import BlobMeta, CommCareApp, DeliverUnit, Opportunity, PaymentUnit, UserVisit
from commcare_connect.organization.models import Organization, UserOrganizationMembership

User = get_user_model()


def reset_audit_database():
    """
    Reset all audit-related database tables.

    This function clears all audit data while preserving:
    - Connect web login accounts (staff/superuser accounts)
    - HQServers (to avoid OAuth application issues)

    Deletes:
    - All BlobMeta records (form attachments/images)
    - All UserVisit records (loaded from Superset for audits)
    - All AuditDefinition records (audit configurations)
    - All AuditSession records and results
    - All Opportunity records
    - Payment and deliver units
    - Organizations created for audits (slug='audit-org')
    - FLW users who had visits (loaded from Superset)
    - CommCare apps created for audits

    Returns:
        dict: Counts of deleted records
    """
    # Count before deletion
    deleted = {
        "opportunities": Opportunity.objects.count(),
        "visits": UserVisit.objects.count(),
        "audit_definitions": AuditDefinition.objects.count(),
        "audit_sessions": AuditSession.objects.count(),
        "users": User.objects.filter(is_superuser=False, is_staff=False).count(),
        "attachments": BlobMeta.objects.count(),
    }

    # Use transaction to ensure all-or-nothing
    with transaction.atomic():
        # First, identify FLW users (before deleting visits)
        # Convert to list to capture IDs (not lazy QuerySet that re-evaluates)

        # Get FLW users: those who have UserVisits (loaded from Superset for audits)
        flw_user_ids = list(UserVisit.objects.values_list("user_id", flat=True).distinct())

        # Delete in correct order to respect foreign keys
        # 1. Delete attachments (BlobMeta records tied to visits)
        BlobMeta.objects.all().delete()

        # 2. Delete visits (removes FK to users)
        UserVisit.objects.all().delete()

        # 3. Delete audit sessions and results
        AuditSession.objects.all().delete()

        # 4. Delete audit definitions (audit configurations and preview data)
        AuditDefinition.objects.all().delete()

        # 5. Delete payment and deliver units that block opportunity deletion
        PaymentUnit.objects.all().delete()
        DeliverUnit.objects.all().delete()

        # 6. Delete CommCare apps created for audit
        CommCareApp.objects.filter(cc_app_id="audit-app").delete()

        # 7. Now we can delete opportunities
        Opportunity.objects.all().delete()

        # 8. Clean up organizations created for audit (before users due to membership FK)
        Organization.objects.filter(slug="audit-org").delete()

        # 9. Delete organization memberships for FLW users
        UserOrganizationMembership.objects.filter(user_id__in=flw_user_ids).delete()

        # 10. Delete FLW users (preserve all Connect web login accounts)
        # Only deletes users who had visits (loaded from Superset for audits)
        User.objects.filter(id__in=flw_user_ids).delete()

    # Note: We don't delete HQServers to avoid OAuth application issues
    # HQServers require OAuth applications and are shared across the system

    return deleted


def get_database_stats():
    """
    Get current counts of audit-related database records.

    Returns:
        dict: Counts of key database records
    """
    # Count FLW users with visits (these are the ones that will be deleted on reset)
    flw_user_ids = UserVisit.objects.values_list("user_id", flat=True).distinct()
    flw_users_with_visits_count = len(flw_user_ids)

    return {
        "opportunities": Opportunity.objects.count(),
        "users": flw_users_with_visits_count,
        "visits": UserVisit.objects.count(),
        "audit_definitions": AuditDefinition.objects.count(),
        "audit_sessions": AuditSession.objects.count(),
    }
