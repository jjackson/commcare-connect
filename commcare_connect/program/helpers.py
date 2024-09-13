from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, OuterRef, Q, Subquery

from commcare_connect.opportunity.models import UserVisit, VisitValidationStatus
from commcare_connect.program.models import ManagedOpportunity, Program


def get_annotated_managed_opportunity(program: Program):
    filter_for_valid__visit_date = ~Q(
        opportunityaccess__uservisit__status__in=[
            VisitValidationStatus.over_limit,
            VisitValidationStatus.trial,
        ]
    )

    earliest_visits = (
        UserVisit.objects.filter(
            opportunity_access=OuterRef("opportunityaccess"),
        )
        .exclude(status__in=[VisitValidationStatus.over_limit, VisitValidationStatus.trial])
        .order_by("visit_date")
        .values("visit_date")[:1]
    )

    managed_opportunities = (
        ManagedOpportunity.objects.filter(program=program)
        .order_by("start_date")
        .annotate(
            workers_invited=Count("opportunityaccess"),
            workers_passing_assessment=Count(
                "opportunityaccess__assessment",
                filter=Q(
                    opportunityaccess__assessment__passed=True,
                    opportunityaccess__assessment__opportunity=F("opportunityaccess__opportunity"),
                ),
            ),
            workers_starting_delivery=Count(
                "opportunityaccess__uservisit__user",
                filter=filter_for_valid__visit_date,
                distinct=True,
            ),
            percentage_conversion=F("workers_starting_delivery") / F("workers_invited") * 100,
            average_time_to_convert=Avg(
                ExpressionWrapper(
                    Subquery(earliest_visits) - F("opportunityaccess__invited_date"), output_field=DurationField()
                ),
                filter=filter_for_valid__visit_date,
            ),
        )
        .prefetch_related(
            "opportunityaccess_set",
            "opportunityaccess_set__uservisit_set",
            "opportunityaccess_set__assessment_set",
        )
    )

    return managed_opportunities


def get_annotated_managed_opportunity_nm(program: Program, start_date=None, end_date=None):
    managed_opportunities = (
        ManagedOpportunity.objects.filter(program=program, start_date__gte=start_date)
        .order_by("start_date")
        .annotate()
        .prefetch_related(
            "opportunityaccess_set",
            "opportunityaccess_set__uservisit_set",
            "opportunityaccess_set__assessment_set",
        )
    )

    return managed_opportunities
