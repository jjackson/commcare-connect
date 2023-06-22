from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from commcare_connect.opportunity.api.serializers import OpportunitySerializer
from commcare_connect.opportunity.models import Opportunity


class OpportunityViewSet(viewsets.ReadOnlyModelViewSet):
    # TODO: Add filtering for CID users
    queryset = Opportunity.objects.all()
    serializer_class = OpportunitySerializer
    # TODO: Add permission for CID users
    permission_classes = [IsAuthenticated]
