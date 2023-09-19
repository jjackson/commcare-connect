from rest_framework import serializers

from commcare_connect.opportunity.models import (
    CommCareApp,
    CompletedModule,
    LearnModule,
    Opportunity,
    OpportunityClaim,
    UserVisit,
)


class LearnModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = LearnModule
        fields = ["slug", "name", "description", "time_estimate"]


class CommCareAppSerializer(serializers.ModelSerializer):
    organization = serializers.SlugRelatedField(read_only=True, slug_field="slug")
    learn_modules = LearnModuleSerializer(many=True)

    class Meta:
        model = CommCareApp
        fields = ["cc_domain", "cc_app_id", "name", "description", "organization", "learn_modules"]


class OpportunityClaimSerializer(serializers.ModelSerializer):
    class Meta:
        model = OpportunityClaim
        fields = ["max_payments", "end_date", "date_claimed"]


class OpportunitySerializer(serializers.ModelSerializer):
    organization = serializers.SlugRelatedField(read_only=True, slug_field="slug")
    learn_app = CommCareAppSerializer()
    deliver_app = CommCareAppSerializer()
    claim = serializers.SerializerMethodField()
    learn_progress = serializers.SerializerMethodField()

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
            "claim",
            "learn_progress",
        ]

    def get_claim(self, obj):
        opp_access = self._get_opp_access(obj)
        claim = OpportunityClaim.objects.filter(opportunity_access=opp_access)
        if claim.exists():
            return OpportunityClaimSerializer(claim.first()).data
        return None

    def get_learn_progress(self, obj):
        opp_access = self._get_opp_access(obj)
        total_modules = LearnModule.objects.filter(app=opp_access.opportunity.learn_app)
        completed_modules = CompletedModule.objects.filter(opportunity=opp_access.opportunity)
        return {"total_modules": total_modules.count(), "completed_modules": completed_modules.count()}

    def _get_opp_access(self, obj):
        opp_access_qs = self.context.get("opportunity_access")
        opp_access = opp_access_qs.filter(opportunity=obj).first()
        return opp_access


class UserLearnProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompletedModule
        fields = ["module", "date", "duration"]


class UserVisitSerializer(serializers.ModelSerializer):
    deliver_form_name = serializers.CharField(source="deliver_form.name")
    deliver_form_xmlns = serializers.CharField(source="deliver_form.xmlns")

    class Meta:
        model = UserVisit
        fields = ["id", "status", "visit_date", "deliver_form_name", "deliver_form_xmlns"]
