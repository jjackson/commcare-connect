from django.core.management import BaseCommand

from commcare_connect.opportunity.models import Opportunity, OpportunityAccess
from commcare_connect.opportunity.visit_import import update_payment_accrued


class Command(BaseCommand):
    help = "Run auto-approval logic over opportunity"

    def add_arguments(self, parser):
        parser.add_argument(
            "--opp", type=int, required=True, help="ID of the opportunity to run auto-approval logic on"
        )

    def handle(self, *args, **options):
        opp_id = options["opp"]
        try:
            opportunity = Opportunity.objects.get(id=opp_id)
            access_records = OpportunityAccess.objects.filter(opportunity=opportunity)
            users = [access.user for access in access_records]

            update_payment_accrued(opportunity=opportunity, users=users)

            self.stdout.write(self.style.SUCCESS(f"Successfully processed opportunity with id {opp_id}"))

        except Opportunity.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Opportunity with id {opp_id} does not exist."))
