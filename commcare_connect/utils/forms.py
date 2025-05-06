from django import forms

DATE_INPUT = forms.DateInput(format="%Y-%m-%d", attrs={"type": "date", "class": "form-control"})
INPUT_CLASS = "base-input"
TEXTAREA_CLASS = "base-textarea"
SELECT_CLASS = "base-dropdown"
CHECKBOX_CLASS = "simple-toggle"
