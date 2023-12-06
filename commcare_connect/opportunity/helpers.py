from django.db.models import Case, Count, Max, Min, Q, Sum, When

from commcare_connect.opportunity.models import Opportunity, OpportunityAccess


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
