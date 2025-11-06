from django.core.management import BaseCommand
from django.db.models import Case, Count, DateTimeField, IntegerField, Max, Min, Q, Sum, Value, When
from django.db.models.lookups import GreaterThanOrEqual

from commcare_connect.opportunity.models import CompletedWorkStatus, OpportunityAccess
from commcare_connect.reports.models import UserAnalyticsData
from commcare_connect.users.models import User


class Command(BaseCommand):
    help = "Backfills User Analytics Data"

    def handle(self, *args, **options):
        users = User.objects.filter(username__isnull=False, email__isnull=True)
        access_objects = (
            OpportunityAccess.objects.filter(user__in=users)
            .annotate(
                max_total=Sum("opportunity__paymentunit__max_total"),
                max_total_done=Count("completedwork__id", Q(completedwork__status=CompletedWorkStatus.approved.value)),
            )
            .values("user_id")
            .annotate(
                total=Count("id", distinct=True),
                accepted_count=Count("id", Q(accepted=True), distinct=True),
                completed_count=Sum(
                    Case(
                        When(Q(GreaterThanOrEqual("max_total_done", "max_total"), accepted=True), then=Value(1)),
                        default=Value(0),
                        output_field=IntegerField(),
                    )
                ),
            )
            .annotate(
                has_opp_invite=Max("invited_date"),
                has_accepted_opp=Max("invited_date", filter=Q(accepted=True)),
                has_started_learning=Max("date_learn_started"),
                has_completed_learning=Max("completed_learn_date"),
                has_completed_assessment=Max("assessment__date", filter=Q(assessment__passed=True)),
                has_claimed_job=Max("opportunityclaim__date_claimed"),
                has_started_job=Min("completedwork__date_created"),
                has_paid=Max("payment__date_paid"),
                has_completed_opp=Case(
                    When(
                        GreaterThanOrEqual("max_total_done", "max_total"),
                        then=Max("completedwork__status_modified_date"),
                    ),
                    default=None,
                    output_field=DateTimeField(),
                ),
                has_offered_multiple_opps=Case(
                    When(Q(total__gt=1), then=Max("invited_date")),
                    default=None,
                    output_field=DateTimeField(),
                ),
                has_accepted_multiple_opps=Case(
                    When(Q(accepted_count__gt=1), then=Max("invited_date")),
                    default=None,
                    output_field=DateTimeField(),
                ),
                has_completed_multiple_opps=Case(
                    When(
                        Q(completed_count__gt=1),
                        then=Max("completedwork__status_modified_date"),
                    ),
                    default=None,
                    output_field=DateTimeField(),
                ),
            )
            .values(
                "user_id",
                "has_opp_invite",
                "has_accepted_opp",
                "has_started_learning",
                "has_completed_learning",
                "has_completed_assessment",
                "has_claimed_job",
                "has_started_job",
                "has_paid",
                "has_completed_opp",
                "has_completed_multiple_opps",
                "has_offered_multiple_opps",
                "has_accepted_multiple_opps",
            )
        )

        UserAnalyticsData.objects.bulk_create(
            [UserAnalyticsData(**data) for data in access_objects],
            update_conflicts=True,
            update_fields=[
                "has_opp_invite",
                "has_accepted_opp",
                "has_started_learning",
                "has_completed_learning",
                "has_completed_assessment",
                "has_claimed_job",
                "has_started_job",
                "has_paid",
                "has_completed_opp",
                "has_completed_multiple_opps",
                "has_offered_multiple_opps",
                "has_accepted_multiple_opps",
            ],
            unique_fields=["user_id"],
        )
