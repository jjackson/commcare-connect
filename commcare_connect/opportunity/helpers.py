from django.db.models import Case, Count, F, Max, Min, Q, Sum, Value, When

from commcare_connect.opportunity.models import CompletedWorkStatus, Opportunity, OpportunityAccess


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
                "user__completed_modules",
                filter=Q(user__completed_modules__opportunity=opportunity),
                distinct=True,
            ),
            job_claimed=Case(When(Q(opportunityclaim__isnull=False), then="opportunityclaim__date_claimed")),
        )
        .annotate(
            date_learn_completed=Case(
                When(
                    Q(completed_modules_count=learn_modules_count),
                    then=Max(
                        "user__completed_modules__date", filter=Q(user__completed_modules__opportunity=opportunity)
                    ),
                )
            )
        )
        .order_by("user__name")
    )

    return access_objects


def get_annotated_opportunity_access_deliver_status(opportunity: Opportunity):
    access_objects = []
    for payment_unit in opportunity.paymentunit_set.all():
        access_objects += (
            OpportunityAccess.objects.filter(opportunity=opportunity)
            .select_related("user")
            .annotate(
                payment_unit=Value(payment_unit.name),
                pending=Count(
                    "completedwork",
                    filter=Q(
                        completedwork__opportunity_access_id=F("pk"),
                        completedwork__payment_unit=payment_unit,
                        completedwork__status=CompletedWorkStatus.pending,
                    ),
                    distinct=True,
                ),
                approved=Count(
                    "completedwork",
                    filter=Q(
                        completedwork__opportunity_access_id=F("pk"),
                        completedwork__payment_unit=payment_unit,
                        completedwork__status=CompletedWorkStatus.approved,
                    ),
                    distinct=True,
                ),
                rejected=Count(
                    "completedwork",
                    filter=Q(
                        completedwork__opportunity_access_id=F("pk"),
                        completedwork__payment_unit=payment_unit,
                        completedwork__status=CompletedWorkStatus.rejected,
                    ),
                    distinct=True,
                ),
                over_limit=Count(
                    "completedwork",
                    filter=Q(
                        completedwork__opportunity_access_id=F("pk"),
                        completedwork__payment_unit=payment_unit,
                        completedwork__status=CompletedWorkStatus.over_limit,
                    ),
                    distinct=True,
                ),
                completed=F("approved") + F("rejected") + F("pending") + F("over_limit"),
            )
            .order_by("user__name")
        )
    access_objects.sort(key=lambda a: a.user.name)
    return access_objects
