from django.db.models import Case, Count, F, Max, Min, Q, Sum, When

from commcare_connect.opportunity.models import Opportunity, OpportunityAccess, VisitValidationStatus


def get_annotated_opportunity_access(opportunity: Opportunity):
    learn_modules_count = opportunity.learn_app.learn_modules.count()
    access_objects = (
        OpportunityAccess.objects.filter(opportunity=opportunity)
        .select_related("user", "opportunityclaim")
        .annotate(
            last_visit_date_d=Max("user__uservisit__visit_date", filter=Q(user__uservisit__opportunity=opportunity)),
            date_deliver_started=Min(
                "user__uservisit__visit_date", filter=Q(user__uservisit__opportunity=opportunity)
            ),
            passed_assessment=Sum(
                Case(
                    When(Q(user__assessments__opportunity=opportunity, user__assessments__passed=True), then=1),
                    default=0,
                )
            ),
            completed_modules_count=Count(
                "user__completed_modules", filter=Q(user__completed_modules__opportunity=opportunity)
            ),
        )
        .annotate(
            date_learn_completed=Case(
                When(
                    Q(completed_modules_count=learn_modules_count),
                    then=Max("user__completed_modules__date"),
                )
            )
        )
        .order_by("user__name")
    )

    return access_objects


def get_annotated_opportunity_access_deliver_status(opportunity: Opportunity):
    access_objects = (
        OpportunityAccess.objects.filter(opportunity=opportunity)
        .select_related("user")
        .annotate(
            visits_pending=Count(
                "user__uservisit",
                filter=Q(
                    user__uservisit__opportunity=opportunity,
                    user__uservisit__status=VisitValidationStatus.pending,
                ),
                distinct=True,
            ),
            visits_approved=Count(
                "user__uservisit",
                filter=Q(
                    user__uservisit__opportunity=opportunity,
                    user__uservisit__status=VisitValidationStatus.approved,
                ),
                distinct=True,
            ),
            visits_rejected=Count(
                "user__uservisit",
                filter=Q(
                    user__uservisit__opportunity=opportunity,
                    user__uservisit__status=VisitValidationStatus.rejected,
                ),
                distinct=True,
            ),
            visits_over_limit=Count(
                "user__uservisit",
                filter=Q(
                    user__uservisit__opportunity=opportunity,
                    user__uservisit__status=VisitValidationStatus.over_limit,
                ),
                distinct=True,
            ),
            visits_completed=F("visits_approved")
            + F("visits_rejected")
            + F("visits_over_limit")
            + F("visits_pending"),
        )
    )
    return access_objects
