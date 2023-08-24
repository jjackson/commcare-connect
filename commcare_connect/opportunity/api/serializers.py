from rest_framework import serializers

from commcare_connect.opportunity.models import CommCareApp, Opportunity, UserVisit


class CommCareAppSerializer(serializers.ModelSerializer):
    organization = serializers.SlugRelatedField(read_only=True, slug_field="slug")

    class Meta:
        model = CommCareApp
        fields = ["cc_domain", "cc_app_id", "name", "description", "organization"]


class OpportunitySerializer(serializers.ModelSerializer):
    organization = serializers.SlugRelatedField(read_only=True, slug_field="slug")
    learn_app = CommCareAppSerializer()
    deliver_app = CommCareAppSerializer()

    class Meta:
        model = Opportunity
        fields = [
            "id",
            "name",
            "description",
            "date_created",
            "date_modified",
            "organization",
            "learn_app",
            "deliver_app",
            "end_date",
            "max_visits_per_user",
            "daily_max_visits_per_user",
            "budget_per_visit",
            "total_budget",
        ]


class UserLearnProgressSerializer(serializers.Serializer):
    completed_modules = serializers.IntegerField()
    total_modules = serializers.IntegerField()


class UserVisitSerializer(serializers.ModelSerializer):
    deliver_form_name = serializers.CharField(source="deliver_form.name")

    class Meta:
        model = UserVisit
        fields = ["id", "status", "visit_date", "deliver_form_name"]
