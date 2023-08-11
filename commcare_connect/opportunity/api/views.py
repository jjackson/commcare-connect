from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from commcare_connect.opportunity.api.serializers import OpportunitySerializer
from commcare_connect.opportunity.models import Opportunity


class OpportunityViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OpportunitySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Opportunity.objects.filter(opportunityaccess__user=self.request.user)
