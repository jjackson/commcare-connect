from crispy_forms.helper import FormHelper
from crispy_forms.layout import Field, Layout, Row, Submit
from django import forms

from commcare_connect.program.models import Program


class ProgramInitForm(forms.ModelForm):
    class Meta:
        model = Program
        fields = [
            "name",
            "description",
            "delivery_type",
        ]

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", {})
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.layout = Layout(
            Row(Field("name")),
            Row(Field("description")),
            Row(Field("delivery_type")),
            Submit("submit", "Submit"),
        )

    def save(self, commit=True):
        self.instance.created_by = self.user.email
        self.instance.modified_by = self.user.email
        return super().save(commit=commit)


class ProgramForm(forms.ModelForm):
    class Meta:
        model = Program
        fields = ["name", "description", "delivery_type"]

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.layout = Layout(
            Row(Field("name")),
            Row(Field("description")),
            Row(Field("delivery_type")),
            Submit("submit", "Submit"),
        )

    def save(self, commit=True):
        instance = super().save(commit=False)
        if not instance.pk:
            instance.created_by = self.user.email
        instance.modified_by = self.user.email
        return super().save(commit=commit)
