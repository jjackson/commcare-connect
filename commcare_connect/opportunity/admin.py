from django.contrib import admin

from commcare_connect.opportunity.forms import OpportunityChangeForm, OpportunityCreationForm
from commcare_connect.opportunity.models import Opportunity

# Register your models here.


@admin.register(Opportunity)
class OpportunityAdmin(admin.ModelAdmin):
    form = OpportunityChangeForm
    add_form = OpportunityCreationForm

    def get_form(self, request, obj=None, **kwargs):
        defaults = {}
        if obj is None:
            defaults["form"] = self.add_form
        defaults.update(kwargs)
        return super().get_form(request, obj, **defaults)
