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

    learn_app = forms.ChoiceField()
    deliver_app = forms.ChoiceField()

    def __init__(self, *args, **kwargs):
        self.applications = kwargs.pop("applications", [])
        self.user = kwargs.pop("user", {})
        self.org_slug = kwargs.pop("org_slug", "")
        super().__init__(*args, **kwargs)

        choices = [(app["id"], app["name"]) for app in self.applications]
        self.fields["learn_app"] = forms.ChoiceField(choices=choices)
        self.fields["deliver_app"] = forms.ChoiceField(choices=choices)

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data["learn_app"] == cleaned_data["deliver_app"]:
            self.add_error("learn_app", "Learn app and Deliver app cannot be same")
            self.add_error("deliver_app", "Learn app and Deliver app cannot be same")

    def save(self, commit=True):
        organization = Organization.objects.filter(slug=self.org_slug).first()
        for app in self.applications:
            if app["id"] == self.cleaned_data["learn_app"]:
                self.instance.learn_app, _ = CommCareApp.objects.get_or_create(
                    cc_app_id=app["id"],
                    name=app["name"],
                    cc_domain=app["domain"],
                    organization=organization,
                    defaults={
                        "created_by": self.user.email,
                        "modified_by": self.user.email,
                    },
                )

            if app["id"] == self.cleaned_data["deliver_app"]:
                self.instance.deliver_app, _ = CommCareApp.objects.get_or_create(
                    cc_app_id=app["id"],
                    name=app["name"],
                    cc_domain=app["domain"],
                    organization=organization,
                    defaults={
                        "created_by": self.user.email,
                        "modified_by": self.user.email,
                    },
                )

        self.instance.created_by = self.user.email
        self.instance.modified_by = self.user.email
        self.instance.organization = organization
        return super().save(commit=commit)
