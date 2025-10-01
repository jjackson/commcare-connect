from django.db.models import F
from django.http import JsonResponse
from oauth2_provider.contrib.rest_framework.permissions import TokenHasScope
from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from commcare_connect.data_export.serializer import (
    OpportunityDataExportSerializer,
    OpportunityUserDataSerializer,
    OrganizationDataExportSerializer,
    ProgramDataExportSerializer,
)
from commcare_connect.opportunity.api.serializers import BaseOpportunitySerializer
from commcare_connect.opportunity.models import Opportunity, OpportunityAccess
from commcare_connect.organization.models import Organization
from commcare_connect.program.models import Program


class BaseDataExportView(APIView):
    permission_classes = [IsAuthenticated, TokenHasScope]
    required_scopes = ["export"]


class ProgramOpportunityOrganizationDataView(BaseDataExportView):
    def get(self):
        organizations = Organization.objects.filter(memberships__user=self.request.user)
        opportunities = Opportunity.objects.filter(organization__in=organizations)
        programs = Program.objects.filter(organization__in=organizations)

        org_data = OrganizationDataExportSerializer(organizations, many=True).data
        opp_data = OpportunityDataExportSerializer(opportunities, many=True).data
        program_data = ProgramDataExportSerializer(programs, many=True).data
        return JsonResponse({"organizations": org_data, "opportunities": opp_data, "programs": program_data})


class OpportunityDataView(RetrieveAPIView, BaseDataExportView):
    serializer_class = BaseOpportunitySerializer

    def get_object(self):
        return Opportunity.objects.get(id=self.kwargs.get("opp_id"), organization__memberships__user=self.request.user)


class OpportunityUserDataView(BaseDataExportView):
    def get(self, request, opp_id):
        users = (
            OpportunityAccess.objects.filter(opportunity_id=opp_id)
            .annotate(
                username=F("user__username"),
                phone=F("user__phone_number"),
                user_invite_status=F("userinvite__status"),
                date_claimed=F("opportunityclaim__date_claimed"),
            )
            .values()
        )
        user_data = OpportunityUserDataSerializer(users, many=True).data
        return JsonResponse({"users": user_data})
