from crispy_forms.helper import FormHelper
from crispy_forms.layout import Field, Layout, Row, Submit
from django import forms

from commcare_connect.program.models import Program

HALF_WIDTH_FIELD = "form-group col-md-6 mb-0"
DATE_INPUT = forms.DateInput(attrs={"type": "date", "class": "form-control"})


class ProgramForm(forms.ModelForm):
    class Meta:
        model = Program
        fields = ["name", "description", "delivery_type", "budget", "currency", "start_date", "end_date"]
        widgets = {"start_date": DATE_INPUT, "end_date": DATE_INPUT}

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.layout = Layout(
            Row(Field("name")),
            Row(Field("description")),
            Row(Field("delivery_type")),
            Row(
                Field("budget", wrapper_class=HALF_WIDTH_FIELD),
                Field("currency", wrapper_class=HALF_WIDTH_FIELD),
            ),
            Row(
                Field("start_date", wrapper_class=HALF_WIDTH_FIELD),
                Field("end_date", wrapper_class=HALF_WIDTH_FIELD),
            ),
            Submit("submit", "Submit"),
        )

    def save(self, commit=True):
        instance = super().save(commit=False)
        if not instance.pk:
            instance.created_by = self.user.email
        instance.modified_by = self.user.email
        return super().save(commit=commit)
