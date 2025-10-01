from rest_framework import serializers

from commcare_connect.opportunity.api.serializers import OpportunityClaimLimitSerializer
from commcare_connect.opportunity.models import Opportunity, OpportunityClaimLimit
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


class OpportunityUserDataSerializer(serializers.Serializer):
    username = serializers.CharField()
    phone = serializers.CharField()
    date_learn_started = serializers.DateTimeField()
    user_invite_status = serializers.CharField()
    payment_accrued = serializers.IntegerField()
    suspended = serializers.BooleanField()
    suspension_date = serializers.DateTimeField()
    suspension_reason = serializers.CharField()
    invited_date = serializers.DateTimeField()
    completed_learn_date = serializers.DateTimeField()
    last_active = serializers.DateTimeField()
    date_claimed = serializers.DateField()
    claim_limits = serializers.SerializerMethodField()

    def get_claim_limits(self, obj):
        access_id = obj.get("id")
        claim_limits = OpportunityClaimLimit.objects.filter(opportunity_claim__opportunity_access_id=access_id)
        return OpportunityClaimLimitSerializer(claim_limits, many=True).data
