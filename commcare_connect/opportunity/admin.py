from django.contrib import admin

from commcare_connect.opportunity.models import CommCareApp, DeliverForm, Opportunity

# Register your models here.


admin.site.register(Opportunity)
admin.site.register(CommCareApp)
admin.site.register(DeliverForm)
