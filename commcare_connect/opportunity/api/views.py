from datetime import datetime

from rest_framework import viewsets
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from commcare_connect.opportunity.api.serializers import (
    OpportunitySerializer,
    UserLearnProgressSerializer,
    UserVisitVerificationStatusSerializer,
)
from commcare_connect.opportunity.models import (
    CompletedModule,
    LearnModule,
    Opportunity,
    OpportunityAccess,
    UserVisit,
    VisitValidationStatus,
)


class OpportunityViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OpportunitySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Opportunity.objects.filter(opportunityaccess__user=self.request.user)


class UserLearnProgressView(APIView):
    permission_classes = [IsAuthenticated]

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


class UserVisitVerificationStatus(APIView):
    serializer_class = UserVisitVerificationStatusSerializer
    permission_classes = [IsAuthenticated]

    def get(self, *args, **kwargs):
        user_visits = UserVisit.objects.filter(user=self.request.user, opportunity=kwargs.get("pk"))
        total_visits = user_visits.count()
        daily_visits = user_visits.filter(visit_date=datetime.today()).count()
        approved = user_visits.filter(status=VisitValidationStatus.approved).count()
        pending = user_visits.filter(status=VisitValidationStatus.pending).count()
        rejected = user_visits.filter(status=VisitValidationStatus.rejected).count()
        ret = {
            "approved": approved,
            "pending": pending,
            "rejected": rejected,
            "total_visits": total_visits,
            "daily_visits": daily_visits,
        }
        return Response(UserVisitVerificationStatusSerializer(ret).data)
