from rest_framework import serializers

from commcare_connect.opportunity.models import Opportunity
from commcare_connect.organization.models import Organization
from commcare_connect.program.models import Program


class OpportunityDataExportSerializer(serializers.ModelSerializer):
    organization = serializers.SlugRelatedField(read_only=True, slug_field="slug")
    program = serializers.SerializerMethodField()

    class Meta:
        model = Opportunity
        fields = ["id", "name", "date_created", "organization", "end_date", "is_active", "program"]

    def get_program(self, obj):
        return obj.managedopportunity.program_id if obj.managed else None


class OrganizationDataExportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["slug", "name"]


class ProgramDataExportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Program
        fields = ["id", "name"]
