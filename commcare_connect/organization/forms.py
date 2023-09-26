from crispy_forms import helper, layout
from django import forms
from django.utils.translation import gettext

from commcare_connect.organization.models import Organization, UserOrganizationMembership


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


class MembershipForm(forms.ModelForm):
    class Meta:
        model = UserOrganizationMembership
        fields = ("user", "role")
        labels = {"user": "", "role": ""}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = helper.FormHelper(self)
        self.helper.layout = layout.Layout(
            layout.Row(
                layout.HTML("<h4>Add new member</h4>"),
                layout.Field("user", wrapper_class="col-md-5"),
                layout.Field("role", wrapper_class="col-md-5"),
                layout.Div(layout.Submit("submit", gettext("Submit")), css_class="col-md-2"),
            ),
        )
