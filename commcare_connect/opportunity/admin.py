from django.contrib import admin

from commcare_connect.opportunity.models import (
    Assessment,
    CommCareApp,
    CompletedModule,
    DeliverForm,
    LearnModule,
    Opportunity,
    OpportunityAccess,
)

# Register your models here.


admin.site.register(Opportunity)
admin.site.register(CommCareApp)
admin.site.register(DeliverForm)
admin.site.register(LearnModule)
admin.site.register(CompletedModule)
admin.site.register(Assessment)
admin.site.register(OpportunityAccess)
