from oauth2_provider.contrib.rest_framework.permissions import TokenHasScope
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from commcare_connect.opportunity.api.permissions import IsOrgProgramManagerAdmin
from commcare_connect.program.api.serializers import ProgramCreateSerializer, ProgramReadSerializer
from commcare_connect.program.models import Program


class ProgramViewSet(viewsets.ModelViewSet):
    serializer_class = ProgramReadSerializer
    permission_classes = [IsAuthenticated, TokenHasScope]
    required_scopes = ["create"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_permissions(self):
        if self.action in ("create", "partial_update"):
            return [IsAuthenticated(), TokenHasScope(), IsOrgProgramManagerAdmin()]
        return [IsAuthenticated(), TokenHasScope()]

    def get_serializer_class(self):
        if self.action in ("create", "partial_update"):
            return ProgramCreateSerializer
        return ProgramReadSerializer

    def get_queryset(self):
        qs = Program.objects.all()
        org_slug = self.request.query_params.get("organization")
        if org_slug:
            qs = qs.filter(organization__slug=org_slug)
        return qs.order_by("-start_date")
