from rest_framework import parsers, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from commcare_connect.form_receiver.processor import process_xform
from commcare_connect.form_receiver.serializers import XFormSerializer


class FormReceiver(APIView):
    parser_classes = [parsers.JSONParser]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = XFormSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        xform = serializer.save()
        process_xform(xform)
        return Response(status=status.HTTP_200_OK)
