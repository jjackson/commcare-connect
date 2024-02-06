from django.core.management.base import BaseCommand

from commcare_connect.opportunity.models import UserVisit


class Command(BaseCommand):
    help = "Populates location for user visits from form json"

    def add_arguments(self, parser, *args, **kwargs):
        parser.add_argument("--opp", type=int)

    def handle(self, *args, **options):
        opp_id = options.get("opp")
        filter_kwargs = {"opportunity": opp_id} if opp_id else {}
        user_visits = UserVisit.objects.filter(**filter_kwargs)
        for visit in user_visits:
            visit.location = visit.form_json.get("metadata", {}).get("location")
            visit.save()
