from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, OuterRef, Q, Subquery

from commcare_connect.opportunity.models import UserVisit, VisitValidationStatus
from commcare_connect.program.models import ManagedOpportunity, Program

FILTER_FOR_VALID_VISIT_DATE = ~Q(
    opportunityaccess__uservisit__status__in=[
        VisitValidationStatus.over_limit,
        VisitValidationStatus.trial,
    ]
)


def get_annotated_managed_opportunity(program: Program):
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
                filter=FILTER_FOR_VALID_VISIT_DATE,
                distinct=True,
            ),
            percentage_conversion=F("workers_starting_delivery") / F("workers_invited") * 100,
            average_time_to_convert=Avg(
                ExpressionWrapper(
                    Subquery(earliest_visits) - F("opportunityaccess__invited_date"), output_field=DurationField()
                ),
                filter=FILTER_FOR_VALID_VISIT_DATE,
            ),
        )
        .prefetch_related(
            "opportunityaccess_set",
            "opportunityaccess_set__uservisit_set",
            "opportunityaccess_set__assessment_set",
        )
    )

    return managed_opportunities


def get_delivery_performance_report(program: Program, start_date, end_date):
    date_filter = Q()

    if start_date:
        date_filter &= Q(opportunityaccess__uservisit__visit_date__gte=start_date)

    if end_date:
        date_filter &= Q(opportunityaccess__uservisit__visit_date__lte=end_date)

    active_workers_filter = Q(FILTER_FOR_VALID_VISIT_DATE, date_filter)

    managed_opportunities = (
        ManagedOpportunity.objects.filter(program=program)
        .order_by("start_date")
        .prefetch_related(
            "opportunityaccess_set",
            "opportunityaccess_set__uservisit_set",
            "opportunityaccess_set__completedwork_set",
        )
        .annotate(
            total_workers_starting_delivery=Count(
                "opportunityaccess__uservisit__user",
                filter=FILTER_FOR_VALID_VISIT_DATE,
                distinct=True,
            ),
            active_workers=Count(
                "opportunityaccess__uservisit__user",
                filter=active_workers_filter,
                distinct=True,
            ),
            total_payment_units=Count("opportunityaccess__completedwork", distinct=True),
            total_payement_since_start_date=Count("opportunityaccess__completedwork", distinct=True),
            deliveries_per_day=F("total_payement_since_start_date") / F("active_workers"),
            records_flagged_percentage=F("total_payment_units") / F("total_payement_since_start_date"),
        )
    )

    return managed_opportunities
