from django.db.models import BooleanField, Case, Count, DateTimeField, Max, Min, Q, When

from commcare_connect.opportunity.models import Opportunity, OpportunityAccess


def get_annotated_opportunity_access(opportunity: Opportunity):
    access_objects = (
        OpportunityAccess.objects.filter(opportunity=opportunity)
        .select_related("user", "opportunityclaim")
        .annotate(
            last_visit_date_d=Max("user__uservisit__visit_date", filter=Q(user__uservisit__opportunity=opportunity)),
            learn_progress_d=(Count("user__completed_modules") / Count("opportunity__learn_app__learn_modules")) * 100,
            date_deliver_started=Min(
                "user__uservisit__visit_date", filter=Q(user__uservisit__opportunity=opportunity)
            ),
            passed_assessment=Case(
                When(Q(user__assessments__opportunity=opportunity), then=True),
                default=False,
                output_field=BooleanField(),
            ),
        )
        .annotate(
            date_learn_completed=Case(
                When(learn_progress_d=100, then=Max("user__completed_modules__date")),
                default=None,
                output_field=DateTimeField(),
            ),
        )
        .order_by("user__name")
    )
    return access_objects
