from commcare_connect.opportunity.models import CompletedWorkStatus


def update_status_and_compute_payment(completed_works, opportunity, compute_payment=True):
    """
    Updates the status of completed works and optionally calculates total payment_accrued.
    """
    payment_accrued = 0
    for completed_work in completed_works:
        if completed_work.completed_count < 1:
            continue

        if opportunity.auto_approve_payments:
            update_completed_work_status(completed_work)

        if compute_payment:
            approved_count = completed_work.approved_count
            if approved_count > 0 and completed_work.status == CompletedWorkStatus.approved:
                payment_accrued += approved_count * completed_work.payment_unit.amount
    return payment_accrued


def update_completed_work_status(completed_work):
    visits = completed_work.uservisit_set.values_list("status", "reason")
    if any(status == "rejected" for status, _ in visits):
        completed_work.update_status(CompletedWorkStatus.rejected)
        completed_work.reason = "\n".join(reason for _, reason in visits if reason)
    elif all(status == "approved" for status, _ in visits):
        completed_work.update_status(CompletedWorkStatus.approved)

    completed_work.save()
