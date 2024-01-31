import dataclasses
from datetime import datetime

from rest_framework import serializers


@dataclasses.dataclass
class XFormMetadata:
    timeStart: datetime
    timeEnd: datetime
    app_build_version: str
    username: str
    location: str

    @property
    def duration(self):
        return self.timeEnd - self.timeStart


@dataclasses.dataclass
class XForm:
    domain: str
    id: str
    app_id: str
    build_id: str
    received_on: datetime
    form: dict
    metadata: XFormMetadata
    raw_form: dict

    @property
    def xmlns(self):
        return self.form.get("@xmlns")


class XFormMetadataSerializer(serializers.Serializer):
    timeStart = serializers.DateTimeField(required=True)
    timeEnd = serializers.DateTimeField(required=True)
    app_build_version = serializers.CharField(allow_null=True)
    username = serializers.CharField()
    location = serializers.CharField()


class XFormSerializer(serializers.Serializer):
    domain = serializers.CharField(required=True)
    id = serializers.CharField(required=True)
    app_id = serializers.CharField(required=True)
    build_id = serializers.CharField(allow_null=True)
    received_on = serializers.DateTimeField(required=True)
    form = serializers.DictField(required=True)
    metadata = XFormMetadataSerializer(required=True)

    def create(self, validated_data):
        metadata = XFormMetadata(**validated_data.pop("metadata"))
        return XForm(metadata=metadata, raw_form=self.initial_data, **validated_data)
