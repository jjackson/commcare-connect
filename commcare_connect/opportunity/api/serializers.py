from rest_framework import serializers

from commcare_connect.opportunity.models import Opportunity


class OpportunitySerializer(serializers.ModelSerializer):
    organization = serializers.SlugRelatedField(read_only=True, slug_field="slug")

    class Meta:
        model = Opportunity
        fields = ["id", "name", "description", "date_created", "date_modified", "organization"]
