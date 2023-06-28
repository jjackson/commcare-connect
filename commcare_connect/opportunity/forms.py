from django import forms

from commcare_connect.opportunity.models import CommCareApp, Opportunity
from commcare_connect.users.models import Organization


class OpportunityChangeForm(forms.ModelForm):
    class Meta:
        model = Opportunity
        fields = ["name", "description", "active"]


class OpportunityCreationForm(forms.ModelForm):
    class Meta:
        model = Opportunity
        fields = ["name", "description"]

    learn_app_select = forms.ChoiceField()
    deliver_app_select = forms.ChoiceField()

    def __init__(self, *args, **kwargs):
        self.applications = kwargs.pop("applications", [])
        self.user = kwargs.pop("user", {})
        self.org_slug = kwargs.pop("org_slug", "")
        super().__init__(*args, **kwargs)

        choices = [(app["id"], app["name"]) for app in self.applications]
        self.fields["learn_app_select"] = forms.ChoiceField(choices=choices)
        self.fields["deliver_app_select"] = forms.ChoiceField(choices=choices)

    def save(self, commit=True):
        for app in self.applications:
            if app["id"] == self.cleaned_data["learn_app_select"]:
                self.instance.learn_app, _ = CommCareApp.objects.get_or_create(
                    cc_app_id=app["id"],
                    name=app["name"],
                    cc_domain=app["domain"],
                    defaults={"created_by": self.user.email, "modified_by": self.user.email},
                )

            if app["id"] == self.cleaned_data["deliver_app_select"]:
                self.instance.deliver_app, _ = CommCareApp.objects.get_or_create(
                    cc_app_id=app["id"],
                    name=app["name"],
                    cc_domain=app["domain"],
                    defaults={"created_by": self.user.email, "modified_by": self.user.email},
                )

        self.instance.created_by = self.user.email
        self.instance.modified_by = self.user.email
        self.instance.organization = Organization.objects.filter(slug=self.org_slug).first()
        return super().save(commit=commit)
