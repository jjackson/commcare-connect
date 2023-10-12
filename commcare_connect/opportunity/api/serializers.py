from rest_framework import serializers

from commcare_connect.cache import quickcache
from commcare_connect.opportunity.models import (
    Assessment,
    CommCareApp,
    CompletedModule,
    LearnModule,
    Opportunity,
    OpportunityAccess,
    OpportunityClaim,
    Payment,
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
        fields = ["cc_domain", "cc_app_id", "name", "description", "organization", "learn_modules", "passing_score"]


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
    deliver_progress = serializers.SerializerMethodField()

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
            "deliver_progress",
        ]

    def get_claim(self, obj):
        opp_access = _get_opp_access(self.context.get("request").user, obj)
        claim = OpportunityClaim.objects.filter(opportunity_access=opp_access)
        if claim.exists():
            return OpportunityClaimSerializer(claim.first()).data
        return None

    def get_learn_progress(self, obj):
        opp_access = _get_opp_access(self.context.get("request").user, obj)
        total_modules = LearnModule.objects.filter(app=opp_access.opportunity.learn_app)
        completed_modules = CompletedModule.objects.filter(opportunity=opp_access.opportunity)
        return {"total_modules": total_modules.count(), "completed_modules": completed_modules.count()}

    def get_deliver_progress(self, obj):
        opp_access = _get_opp_access(self.context.get("request").user, obj)
        return opp_access.visit_count


@quickcache(vary_on=["user.pk", "opportunity.pk"], timeout=60 * 60)
def _get_opp_access(user, opportunity):
    return OpportunityAccess.objects.filter(user=user, opportunity=opportunity).first()


class CompletedModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompletedModule
        fields = ["module", "date", "duration"]


class AssessmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Assessment
        fields = ["date", "score", "passing_score", "passed"]


class UserLearnProgressSerializer(serializers.Serializer):
    completed_modules = serializers.SerializerMethodField()
    assessments = serializers.SerializerMethodField()

    def get_completed_modules(self, obj: dict):
        return CompletedModuleSerializer(obj.get("completed_modules"), many=True).data

    def get_assessments(self, obj: dict):
        return AssessmentSerializer(obj.get("assessments"), many=True).data


class UserVisitSerializer(serializers.ModelSerializer):
    deliver_unit_name = serializers.CharField(source="deliver_unit.name")
    deliver_unit_slug = serializers.CharField(source="deliver_unit.slug")

    class Meta:
        model = UserVisit
        fields = ["id", "status", "visit_date", "deliver_unit_name", "deliver_unit_slug"]


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["amount", "date_paid"]


class DeliveryProgressSerializer(serializers.Serializer):
    deliveries = serializers.SerializerMethodField()
    payments = serializers.SerializerMethodField()

    def get_payments(self, obj):
        return PaymentSerializer(obj.payment_set.all(), many=True).data

    def get_deliveries(self, obj):
        deliveries = UserVisit.objects.filter(opportunity=obj.opportunity, user=obj.user)
        return UserVisitSerializer(deliveries, many=True).data
