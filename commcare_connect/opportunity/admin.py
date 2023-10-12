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
    PaymentUnit,
    UserVisit,
)

# Register your models here.


admin.site.register(Opportunity)
admin.site.register(CommCareApp)
admin.site.register(DeliverUnit)
admin.site.register(LearnModule)
admin.site.register(CompletedModule)
admin.site.register(Assessment)
admin.site.register(UserVisit)
admin.site.register(OpportunityClaim)
admin.site.register(PaymentUnit)


@admin.register(OpportunityAccess)
class OpportunityAccessAdmin(admin.ModelAdmin):
    form = OpportunityAccessCreationForm
    list_display = ["get_opp_name", "get_username"]

    @admin.display(description="Opportunity Name")
    def get_opp_name(self, obj):
        return obj.opportunity.name

    @admin.display(description="Username")
    def get_username(self, obj):
        return obj.user.username
