from django.contrib import admin

from commcare_connect.opportunity.forms import OpportunityAccessCreationForm
from commcare_connect.opportunity.models import (
    Assessment,
    CommCareApp,
    CompletedModule,
    DeliverUnit,
    LearnModule,
    Opportunity,
    OpportunityAccess,
    OpportunityClaim,
    Payment,
    PaymentUnit,
    UserVisit,
)

# Register your models here.


admin.site.register(Opportunity)
admin.site.register(CommCareApp)
admin.site.register(PaymentUnit)


@admin.register(OpportunityAccess)
class OpportunityAccessAdmin(admin.ModelAdmin):
    form = OpportunityAccessCreationForm
    list_display = ["get_opp_name", "get_username"]
    actions = ["clear_user_progress"]

    @admin.display(description="Opportunity Name")
    def get_opp_name(self, obj):
        return obj.opportunity.name

    @admin.display(description="Username")
    def get_username(self, obj):
        return obj.user.username

    @admin.action(description="Clear User Progress")
    def clear_user_progress(self, request, queryset):
        for access in queryset:
            UserVisit.objects.filter(user=access.user).delete()
            Payment.objects.filter(opportunity_access=access).delete()
            OpportunityClaim.objects.filter(opportunity_access=access).delete()
            CompletedModule.objects.filter(user=access.user).delete()
            Assessment.objects.filter(user=access.user).delete()


@admin.register(LearnModule)
@admin.register(DeliverUnit)
class LearnModuleAndDeliverUnitAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "app"]
    search_fields = ["name"]


@admin.register(OpportunityClaim)
class OpportunityClaimAdmin(admin.ModelAdmin):
    list_display = ["get_username", "get_opp_name", "opportunity_access"]

    @admin.display(description="Opportunity Name")
    def get_opp_name(self, obj):
        return obj.opportunity_access.opportunity.name

    @admin.display(description="Username")
    def get_username(self, obj):
        return obj.opportunity_access.user.username


@admin.register(CompletedModule)
class CompletedModuleAdmin(admin.ModelAdmin):
    list_display = ["module", "user", "opportunity", "date"]


@admin.register(UserVisit)
class UserVisitAdmin(admin.ModelAdmin):
    list_display = ["deliver_unit", "user", "opportunity", "status"]


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = ["app", "user", "opportunity", "date", "passed"]
