from crispy_forms.helper import FormHelper
from crispy_forms.layout import Field, Layout
from django import forms
from django.utils.translation import gettext_lazy as _

from commcare_connect.microplanning.models import WorkArea, WorkAreaGroup


class WorkAreaModelForm(forms.ModelForm):
    reason = forms.CharField(
        required=False,
        label=_("Reason for change (Optional)"),
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": _("Enter reason...")}),
    )

    class Meta:
        model = WorkArea
        fields = ["expected_visit_count", "work_area_group"]
        widgets = {
            "work_area_group": forms.Select(attrs={"data-tomselect": "1", "data-tomselect:no-remove-button": "1"})
        }
        labels = {
            "expected_visit_count": _("Expected Visit Count"),
            "work_area_group": _("Work Area Group"),
        }

    def __init__(self, *args, **kwargs):
        opportunity = kwargs.pop("opportunity", None)
        super().__init__(*args, **kwargs)
        if opportunity:
            self.fields["work_area_group"].queryset = WorkAreaGroup.objects.filter(opportunity=opportunity)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field("expected_visit_count"),
            Field("work_area_group"),
            Field("reason"),
        )
