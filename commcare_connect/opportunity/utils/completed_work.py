from commcare_connect.opportunity.models import (
    CompletedWork,
    CompletedWorkStatus,
    OpportunityAccess,
    Payment,
    VisitReviewStatus,
    VisitValidationStatus,
)


def update_status(completed_works, opportunity_access, compute_payment=True):
    """
    Updates the status of completed works and optionally calculates & update total payment_accrued.

    If compute_payment is True, the saved fields related to completed/approved work and payments
    earned will also be saved against the model.
    """
    payment_accrued = 0
    for completed_work in completed_works:
        made_changes = False
        completed_count = completed_work.completed_count
        if completed_count < 1:
            continue

        if opportunity_access.opportunity.auto_approve_payments:
            visits = completed_work.uservisit_set.values_list("status", "reason", "review_status")
            if any(status == VisitValidationStatus.rejected for status, *_ in visits):
                completed_work.status = CompletedWorkStatus.rejected
                completed_work.reason = "\n".join(reason for _, reason, _ in visits if reason)
            elif all(status == VisitValidationStatus.approved for status, *_ in visits):
                completed_work.status = CompletedWorkStatus.approved

            if (
                opportunity_access.opportunity.managed
                and not all(review_status == VisitReviewStatus.agree for *_, review_status in visits)
                and completed_work.status == CompletedWorkStatus.approved
            ):
                completed_work.status = CompletedWorkStatus.pending

            made_changes = True

        if compute_payment:
            approved_count = completed_work.approved_count

            amount_accrued = org_amount_accrued = 0
            if approved_count > 0 and completed_work.status == CompletedWorkStatus.approved:
                amount_accrued = approved_count * completed_work.payment_unit.amount
                # if it's a managed opportunity we also need to update the org payment amounts
                if opportunity_access.opportunity.managed:
                    org_amount_accrued = approved_count * opportunity_access.managed_opportunity.org_pay_per_visit
                payment_accrued += amount_accrued

            completed_work.saved_completed_count = completed_count
            completed_work.saved_approved_count = approved_count
            completed_work.saved_payment_accrued = amount_accrued
            completed_work.saved_org_payment_accrued = org_amount_accrued

        if made_changes:
            completed_work.save()

    if compute_payment:
        opportunity_access.payment_accrued = payment_accrued
        opportunity_access.save()


def update_work_payment_date(access: OpportunityAccess):
    payments = Payment.objects.filter(opportunity_access=access).order_by("date_paid")
    completed_works = CompletedWork.objects.filter(opportunity_access=access).order_by("status_modified_date")

    if not payments or not completed_works:
        return

    works_to_update = []
    completed_works_iter = iter(completed_works)
    current_work = next(completed_works_iter)

    remaining_amount = 0

    for payment in payments:
        remaining_amount += payment.amount

        while remaining_amount >= current_work.payment_accrued:
            current_work.payment_date = payment.date_paid
            works_to_update.append(current_work)
            remaining_amount -= current_work.payment_accrued

            try:
                current_work = next(completed_works_iter)
            except StopIteration:
                break
        else:
            continue

        # we've broken out of the inner while loop so all completed_works are processed.
        break

    if works_to_update:
        CompletedWork.objects.bulk_update(works_to_update, ["payment_date"])
