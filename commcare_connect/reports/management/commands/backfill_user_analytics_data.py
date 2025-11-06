from django.core.management import BaseCommand
from django.db.models import Case, Count, DateTimeField, F, Max, Min, Q, Sum, When
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
            .order_by("invited_date")
            .values("user_id")
            .annotate(
                max_total=Sum("opportunity__paymentunit__max_total"),
                max_total_done=Count("completedwork__id", Q(completedwork__status=CompletedWorkStatus.approved.value)),
            )
            .annotate(
                has_accepted_opp=Max("invited_date"),
                has_started_learning=Max("date_learn_started"),
                has_completed_learning=Max("completed_learn_date"),
                has_completed_assessment=Max("assessment__date", filter=Q(assessment__passed=True)),
                has_claimed_job=F("opportunityclaim__date_claimed"),
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
            )
            .values(
                "user_id",
                "has_accepted_opp",
                "has_started_learning",
                "has_completed_learning",
                "has_completed_assessment",
                "has_claimed_job",
                "has_started_job",
                "has_paid",
                "has_completed_opp",
            )
        )
        multiple_opp_calculation_qs = (
            OpportunityAccess.objects.filter(user__in=users)
            .values("user_id")
            .annotate(total=Count("*"), invited_date_d=Max("invited_date"))
            .filter(total__gt=1)
            .order_by("invited_date")
            .annotate(
                has_completed_multiple_opps=F("invited_date_d"),
                has_offered_multiple_opps=F("invited_date_d"),
                has_accepted_multiple_opps=F("invited_date_d"),
            )
            .values(
                "user_id", "has_completed_multiple_opps", "has_offered_multiple_opps", "has_accepted_multiple_opps"
            )
        )

        user_map = {}
        for access in access_objects:
            user_id = access.pop("user_id")
            if user_id is not None:
                user_map[user_id] = {**access, "user_id": user_id}

        for data in multiple_opp_calculation_qs:
            user_id = data.pop("user_id")
            if user_id is not None:
                user_map[user_id] = {**data, "user_id": user_id}

        to_create = []
        for user_data in user_map.values():
            to_create.append(UserAnalyticsData(**user_data))

        UserAnalyticsData.objects.bulk_create(
            to_create,
            update_conflicts=True,
            update_fields=[
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
