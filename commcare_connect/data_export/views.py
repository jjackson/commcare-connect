from oauth2_provider.contrib.rest_framework.permissions import TokenHasScope
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView


class BaseDataExportView(APIView):
    permission_classes = [IsAuthenticated, TokenHasScope]
    required_scopes = ["export"]
