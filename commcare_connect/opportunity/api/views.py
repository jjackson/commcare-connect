from rest_framework import viewsets
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from commcare_connect.opportunity.api.serializers import OpportunitySerializer, UserLearnProgressSerializer
from commcare_connect.opportunity.models import CompletedModule, LearnModule, Opportunity, OpportunityAccess


class OpportunityViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OpportunitySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Opportunity.objects.filter(opportunityaccess__user=self.request.user)


class UserLearnProgressView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, *args, **kwargs):
        qs = OpportunityAccess.objects.all()
        opportunity_access = get_object_or_404(qs, user=self.request.user, opportunity=kwargs.get("pk"))
        completed_modules = CompletedModule.objects.filter(
            user=self.request.user, opportunity=opportunity_access.opportunity
        )
        total_modules = LearnModule.objects.filter(app=opportunity_access.opportunity.learn_app)
        ret = {
            "completed_modules": completed_modules.count(),
            "total_modules": total_modules.count(),
        }
        return Response(UserLearnProgressSerializer(ret).data)
