from rest_framework import parsers, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from commcare_connect.form_receiver.serializers import XFormSerializer


class FormReceiver(APIView):
    parser_classes = [parsers.JSONParser]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = XFormSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(status=status.HTTP_200_OK)
