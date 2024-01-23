from django.core.management.base import BaseCommand

from commcare_connect.opportunity.models import Assessment, CompletedModule, OpportunityAccess, UserVisit
from commcare_connect.utils.log import with_progress_bar


class Command(BaseCommand):
    help = "Populates opportunity_access foriegn key on Assessment, CompletedModules and UserVisit tables."

    def handle(self, *args, **kwargs):
        access_objects = OpportunityAccess.objects.all()

        for access in with_progress_bar(access_objects):
            UserVisit.objects.filter(user=access.user, opportunity=access.opportunity).update(
                opportunity_access=access
            )
            CompletedModule.objects.filter(user=access.user, opportunity=access.opportunity).update(
                opportunity_access=access
            )
            Assessment.objects.filter(user=access.user, opportunity=access.opportunity).update(
                opportunity_access=access
            )
