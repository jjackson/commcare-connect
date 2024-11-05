from crispy_forms import helper, layout
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import gettext

from commcare_connect.organization.models import Organization, UserOrganizationMembership
from commcare_connect.users.models import User


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
    email_or_username = forms.CharField(
        max_length=254,
        required=True,
        label="",
        widget=forms.TextInput(attrs={"placeholder": "Enter email or username"}),
    )

    class Meta:
        model = UserOrganizationMembership
        fields = ("role",)
        labels = {"role": ""}

    def __init__(self, *args, **kwargs):
        self.organization = kwargs.pop("organization")
        super().__init__(*args, **kwargs)

        self.helper = helper.FormHelper(self)
        self.helper.layout = layout.Layout(
            layout.Row(
                layout.HTML("<h4>Add new member</h4>"),
                layout.Field("email_or_username", wrapper_class="col-md-5"),
                layout.Field("role", wrapper_class="col-md-5"),
                layout.Div(layout.Submit("submit", gettext("Submit")), css_class="col-md-2"),
            ),
        )

    def clean_email_or_username(self):
        email_or_username = self.cleaned_data["email_or_username"]
        user = (
            User.objects.filter(
                Q(email=email_or_username) | Q(username=email_or_username),
                email__isnull=False,
            )
            .exclude(memberships__organization=self.organization)
            .first()
        )

        if not user:
            raise ValidationError("User with this email/username does not exist or is already a member")

        self.instance.user = user
        return email_or_username


class AddCredentialForm(forms.Form):
    credential = forms.CharField(widget=forms.Select)
    users = forms.CharField(
        widget=forms.Textarea(
            attrs=dict(
                placeholder="Enter the phone numbers of the users you want to add the "
                "credential to, one on each line.",
            )
        ),
    )

    def __init__(self, *args, **kwargs):
        credentials = kwargs.pop("credentials", [])
        super().__init__(*args, **kwargs)

        self.fields["credential"].widget.choices = [(c.name, c.name) for c in credentials]

        self.helper = helper.FormHelper(self)
        self.helper.layout = layout.Layout(
            layout.Row(layout.Field("credential")),
            layout.Row(layout.Field("users")),
            layout.Row(layout.Div(layout.Submit("submit", gettext("Submit")))),
        )

    def clean_users(self):
        user_data = self.cleaned_data["users"]
        split_users = [line.strip() for line in user_data.splitlines() if line.strip()]
        return split_users


OrganizationCreationForm = forms.modelform_factory(
    Organization,
    fields=("name",),
    labels={"name": "Organization Name"},
    help_texts={
        "name": (
            "This would be used to create the Organization URL,"
            " and you will not be able to change the URL in future."
        )
    },
)
