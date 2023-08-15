from crispy_forms import helper, layout
from django import forms
from django.utils.translation import gettext

from commcare_connect.organization.models import Organization


class OrganizationChangeForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = ("name",)
        labels = {
            "name": gettext("Organization Name"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = helper.FormHelper(self)
        self.helper.layout = layout.Layout(
            layout.Row(layout.Field("name")),
            layout.Submit("submit", gettext("Update")),
        )
