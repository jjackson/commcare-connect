"""
Helper functions for tasks using ExperimentRecord-based TaskRecord model.

Simplified helpers that use TaskDataAccess instead of Django ORM.
OAuth API is the source of truth for permissions - no local checks needed.
"""

from commcare_connect.tasks.data_access import TaskDataAccess


def get_user_tasks_queryset(user):
    """
    Get filtered queryset of tasks user can access via OAuth.

    Args:
        user: Django User or LabsUser instance

    Returns:
        QuerySet of TaskRecord instances (OAuth enforces access)
    """
    from commcare_connect.labs.config import LABS_DEFAULT_OPPORTUNITY_ID

    data_access = TaskDataAccess(opportunity_id=LABS_DEFAULT_OPPORTUNITY_ID, user=user)
    return data_access.get_tasks()


def create_task_from_audit(
    audit_session_id: int,
    user_id: int,
    opportunity_id: int,
    task_type: str,
    description: str,
    created_by_id: int,
    **kwargs,
):
    """
    Create task from audit trigger.

    This is a clean API for future automation when audit failures
    automatically create tasks.

    Args:
        audit_session_id: ID of the audit session that triggered this task
        user_id: The FLW user ID this task is about
        opportunity_id: The opportunity ID this task relates to
        task_type: Type of task (warning/deactivation)
        description: Description of what happened
        created_by_id: User ID creating the task (or system user)
        **kwargs: Additional fields (priority, assigned_to_id, title, status, etc.)

    Returns:
        The created TaskRecord instance
    """
    from commcare_connect.labs.config import LABS_DEFAULT_OPPORTUNITY_ID

    data_access = TaskDataAccess(opportunity_id=LABS_DEFAULT_OPPORTUNITY_ID)

    return data_access.create_task(
        user_id=user_id,
        opportunity_id=opportunity_id,
        created_by_id=created_by_id,
        task_type=task_type,
        description=description,
        audit_session_id=audit_session_id,
        title=kwargs.get("title", f"{task_type.title()} for user {user_id}"),
        priority=kwargs.get("priority", "medium"),
        status=kwargs.get("status", "unassigned"),
        assigned_to_id=kwargs.get("assigned_to_id"),
        learning_assignment_text=kwargs.get("learning_assignment_text", ""),
        creator_name=kwargs.get("creator_name", f"User {created_by_id}"),
    )
