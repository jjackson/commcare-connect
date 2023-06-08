from django import forms

from commcare_connect.opportunity.models import Opportunity


class OpportunityChangeForm(forms.ModelForm):
    class Meta:
        model = Opportunity
        fields = ["name", "description", "active"]


class OpportunityCreationForm(forms.ModelForm):
    class Meta:
        model = Opportunity
        fields = ["name", "description"]
