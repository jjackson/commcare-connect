from rest_framework import serializers

from commcare_connect.organization.models import Organization
from commcare_connect.program.models import Program


class ProgramCreateSerializer(serializers.ModelSerializer):
    organization = serializers.SlugRelatedField(slug_field="slug", queryset=Organization.objects.all())

    class Meta:
        model = Program
        fields = [
            "name",
            "description",
            "delivery_type",
            "budget",
            "currency",
            "country",
            "start_date",
            "end_date",
            "organization",
        ]

    def validate(self, data):
        if data.get("end_date") and data.get("start_date") and data["end_date"] <= data["start_date"]:
            raise serializers.ValidationError({"end_date": "End date must be after the start date."})
        return data

    def create(self, validated_data):
        user = self.context["request"].user
        validated_data["created_by"] = user.email
        validated_data["modified_by"] = user.email
        return super().create(validated_data)


class ProgramReadSerializer(serializers.ModelSerializer):
    organization = serializers.SlugRelatedField(slug_field="slug", read_only=True)

    class Meta:
        model = Program
        fields = [
            "id",
            "program_id",
            "name",
            "slug",
            "description",
            "delivery_type",
            "budget",
            "currency",
            "country",
            "start_date",
            "end_date",
            "organization",
            "date_created",
            "date_modified",
        ]
