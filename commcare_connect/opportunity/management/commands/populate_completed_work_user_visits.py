from itertools import groupby

from django.core.management.base import BaseCommand

from commcare_connect.opportunity.models import CompletedWork, PaymentUnit, UserVisit


class Command(BaseCommand):
    help = "Populates location for user visits from form json"

    def add_arguments(self, parser, *args, **kwargs):
        parser.add_argument("--opp", type=int)

    def handle(self, *args, **options):
        opp_id = options.get("opp")
        filter_kwargs = {"opportunity": opp_id} if opp_id else {}
        payment_units = PaymentUnit.objects.filter(**filter_kwargs)
        for payment_unit in payment_units:
            filter_kwargs.update(deliver_unit__in=payment_unit.deliver_units.values_list("id", flat=True))
            user_visits = UserVisit.objects.filter(**filter_kwargs)
            for _, visits in groupby(user_visits, key=lambda x: x.entity_id):
                for visit in visits:
                    completed_work, _ = CompletedWork.objects.get_or_create(
                        payment_unit=payment_unit, entity_id=visit.entity_id, entity_name=visit.entity_name
                    )
                    visit.completed_work = completed_work
                    visit.save()
