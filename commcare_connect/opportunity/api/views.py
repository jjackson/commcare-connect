from oauth2_provider.contrib.rest_framework import OAuth2Authentication, TokenHasReadWriteScope
from rest_framework import viewsets
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from commcare_connect.opportunity.api.serializers import (
    OpportunitySerializer,
    UserLearnProgressSerializer,
    UserVisitSerializer,
)
from commcare_connect.opportunity.models import (
    CompletedModule,
    LearnModule,
    Opportunity,
    OpportunityAccess,
    OpportunityClaim,
    UserVisit,
)
from commcare_connect.users.helpers import create_hq_user


class OpportunityViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OpportunitySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Opportunity.objects.filter(opportunityaccess__user=self.request.user)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        opportunity_access = OpportunityAccess.objects.filter(user=self.request.user)
        context.update({"opportunity_access": opportunity_access})
        return context


class UserLearnProgressView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserLearnProgressSerializer

    def get(self, *args, **kwargs):
        opportunity_access = get_object_or_404(OpportunityAccess, user=self.request.user, opportunity=kwargs.get("pk"))
        completed_modules = CompletedModule.objects.filter(
            user=self.request.user, opportunity=opportunity_access.opportunity
        )
        total_modules = LearnModule.objects.filter(app=opportunity_access.opportunity.learn_app)
        ret = {
            "completed_modules": completed_modules.count(),
            "total_modules": total_modules.count(),
        }
        return Response(UserLearnProgressSerializer(ret).data)


class UserVisitViewSet(viewsets.GenericViewSet, viewsets.mixins.ListModelMixin):
    serializer_class = UserVisitSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserVisit.objects.filter(opportunity=self.kwargs.get("opportunity_id"), user=self.request.user)


class ClaimOpportunityView(APIView):
    authentication_classes = [OAuth2Authentication]
    permission_classes = [TokenHasReadWriteScope]

    def post(self, *args, **kwargs):
        opportunity_access = get_object_or_404(OpportunityAccess, user=self.request.user, opportunity=kwargs.get("pk"))
        opportunity = opportunity_access.opportunity

        claim, created = OpportunityClaim.objects.get_or_create(
            opportunity_access=opportunity_access,
            defaults={
                "max_payments": opportunity.daily_max_visits_per_user,
                "end_date": opportunity.end_date,
            },
        )

        if not created:
            return Response(status=200, data="Opportunity is already claimed")

        if opportunity.learn_app.cc_domain != opportunity.deliver_app.cc_domain:
            create_hq_user(self.request.user, opportunity.deliver_app.cc_domain, opportunity.api_key)

        return Response(status=201)
