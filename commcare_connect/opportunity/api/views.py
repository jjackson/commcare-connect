import datetime

from rest_framework import viewsets
from rest_framework.generics import ListAPIView, get_object_or_404
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
    Opportunity,
    OpportunityAccess,
    OpportunityClaim,
    UserVisit,
)
from commcare_connect.users.helpers import create_hq_user
from commcare_connect.users.models import ConnectIDUserLink


class OpportunityViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OpportunitySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Opportunity.objects.filter(opportunityaccess__user=self.request.user)


class UserLearnProgressView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserLearnProgressSerializer

    def get_queryset(self):
        opportunity_access = get_object_or_404(
            OpportunityAccess, user=self.request.user, opportunity=self.kwargs.get("pk")
        )
        return CompletedModule.objects.filter(user=self.request.user, opportunity=opportunity_access.opportunity)


class UserVisitViewSet(viewsets.GenericViewSet, viewsets.mixins.ListModelMixin):
    serializer_class = UserVisitSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserVisit.objects.filter(opportunity=self.kwargs.get("opportunity_id"), user=self.request.user)


class ClaimOpportunityView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, *args, **kwargs):
        opportunity_access = get_object_or_404(OpportunityAccess, user=self.request.user, opportunity=kwargs.get("pk"))
        opportunity = opportunity_access.opportunity

        if opportunity.remaining_budget <= 0:
            return Response(status=200, data="Opportunity cannot be claimed. (Budget Exhausted)")
        if opportunity.end_date < datetime.date.today():
            return Response(status=200, data="Opportunity cannot be claimed. (End date reached)")

        max_payments = min(opportunity.remaining_budget, opportunity.daily_max_visits_per_user)
        claim, created = OpportunityClaim.objects.get_or_create(
            opportunity_access=opportunity_access,
            defaults={
                "max_payments": max_payments,
                "end_date": opportunity.end_date,
            },
        )
        if not created:
            return Response(status=200, data="Opportunity is already claimed")

        domain = opportunity.deliver_app.cc_domain
        if not ConnectIDUserLink.objects.filter(user=self.request.user, domain=domain).exists():
            user_created = create_hq_user(self.request.user, domain, opportunity.api_key)
            if not user_created:
                return Response("Failed to create user", status=400)
            ConnectIDUserLink.objects.create(
                commcare_username=self.request.user.username, user=self.request.user, domain=domain
            )
        return Response(status=201)
