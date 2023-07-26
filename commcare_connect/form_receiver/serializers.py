from rest_framework import serializers


class XFormSerializer(serializers.Serializer):
    domain = serializers.CharField(required=True)
    app_id = serializers.CharField(required=True)
    form = serializers.DictField(required=True)
