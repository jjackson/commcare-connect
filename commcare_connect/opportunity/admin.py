from django.contrib import admin

from commcare_connect.opportunity.models import CommCareApp, Opportunity

# Register your models here.


admin.site.register(Opportunity)
admin.site.register(CommCareApp)
