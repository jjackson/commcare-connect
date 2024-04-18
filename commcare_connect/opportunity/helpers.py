from django.db.models import Case, Count, F, Max, Min, Q, Sum, When

from commcare_connect.opportunity.models import Opportunity, OpportunityAccess, UserInvite, VisitValidationStatus


def get_annotated_opportunity_access(opportunity: Opportunity):
    learn_modules_count = opportunity.learn_app.learn_modules.count()
    access_objects = (
        UserInvite.objects.filter(opportunity=opportunity)
        .select_related("opportunity_access", "opportunity_access__opportunityclaim", "opportunity_access__user")
        .annotate(
            last_visit_date_d=Max(
                "opportunity_access__user__uservisit__visit_date",
                filter=Q(opportunity_access__user__uservisit__opportunity=opportunity),
            ),
            date_deliver_started=Min(
                "opportunity_access__user__uservisit__visit_date",
                filter=Q(opportunity_access__user__uservisit__opportunity=opportunity),
            ),
            passed_assessment=Sum(
                Case(
                    When(
                        Q(
                            opportunity_access__user__assessments__opportunity=opportunity,
                            opportunity_access__user__assessments__passed=True,
                        ),
                        then=1,
                    ),
                    default=0,
                )
            ),
            completed_modules_count=Count(
                "opportunity_access__user__completed_modules",
                filter=Q(opportunity_access__user__completed_modules__opportunity=opportunity),
                distinct=True,
            ),
            job_claimed=Case(
                When(
                    Q(opportunity_access__opportunityclaim__isnull=False),
                    then="opportunity_access__opportunityclaim__date_claimed",
                )
            ),
        )
        .annotate(
            date_learn_completed=Case(
                When(
                    Q(completed_modules_count=learn_modules_count),
                    then=Max(
                        "opportunity_access__user__completed_modules__date",
                        filter=Q(opportunity_access__user__completed_modules__opportunity=opportunity),
                    ),
                )
            )
        )
        .order_by("opportunity_access__user__name")
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
            visits_duplicate=Count(
                "user__uservisit",
                filter=Q(
                    user__uservisit__opportunity=opportunity,
                    user__uservisit__status=VisitValidationStatus.duplicate,
                ),
                distinct=True,
            ),
            visits_completed=F("visits_approved")
            + F("visits_rejected")
            + F("visits_over_limit")
            + F("visits_pending")
            + F("visits_duplicate"),
        )
        .order_by("user__name")
    )
    return access_objects
