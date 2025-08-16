from django import forms
from django.core.exceptions import ValidationError
from django.forms import ModelForm
from django.utils.translation import gettext_lazy as _

from .models import SolicitationQuestion, SolicitationResponse


class SolicitationResponseForm(ModelForm):
    """
    Dynamic form for responding to solicitations
    Fields are generated based on SolicitationQuestion instances
    """

    # Remove the old single file field - we'll handle multiple files differently

    class Meta:
        model = SolicitationResponse
        fields = []  # No file fields in the main form

    def __init__(self, solicitation, user, is_draft_save=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.solicitation = solicitation
        self.user = user
        self.is_draft_save = is_draft_save

        # Dynamically add fields based on solicitation questions
        questions = SolicitationQuestion.objects.filter(solicitation=solicitation).order_by("order")

        for question in questions:
            field_name = f"question_{question.id}"

            # For drafts, never require fields. For submission, use question's requirement
            field_required = question.is_required and not is_draft_save

            if question.question_type == "text":
                field = forms.CharField(
                    label=question.question_text,
                    required=field_required,
                    max_length=500,
                    widget=forms.TextInput(
                        attrs={
                            "class": (
                                "w-full px-3 py-2 border border-gray-300 rounded-md "
                                "focus:outline-none focus:ring-2 focus:ring-brand-indigo focus:border-brand-indigo"
                            )
                        }
                    ),
                )
            elif question.question_type == "textarea":
                field = forms.CharField(
                    label=question.question_text,
                    required=field_required,
                    widget=forms.Textarea(
                        attrs={
                            "class": (
                                "w-full px-3 py-2 border border-gray-300 rounded-md "
                                "focus:outline-none focus:ring-2 focus:ring-brand-indigo focus:border-brand-indigo"
                            ),
                            "rows": 4,
                        }
                    ),
                )
            elif question.question_type == "number":
                field = forms.IntegerField(
                    label=question.question_text,
                    required=field_required,
                    widget=forms.NumberInput(
                        attrs={
                            "class": (
                                "w-full px-3 py-2 border border-gray-300 rounded-md "
                                "focus:outline-none focus:ring-2 focus:ring-brand-indigo focus:border-brand-indigo"
                            )
                        }
                    ),
                )
            elif question.question_type == "file":
                # File fields are never required (as per user request)
                field = forms.FileField(
                    label=question.question_text,
                    required=False,
                    widget=forms.FileInput(
                        attrs={
                            "class": (
                                "w-full px-3 py-2 border border-gray-300 rounded-md "
                                "focus:outline-none focus:ring-2 focus:ring-brand-indigo focus:border-brand-indigo"
                            )
                        }
                    ),
                )
            elif question.question_type == "multiple_choice":
                choices = [("", "Select an option...")]  # Add empty choice for optional fields
                if question.options:
                    for option in question.options:
                        choices.append((option, option))
                field = forms.ChoiceField(
                    label=question.question_text,
                    required=field_required,
                    choices=choices,
                    widget=forms.Select(
                        attrs={
                            "class": (
                                "w-full px-3 py-2 border border-gray-300 rounded-md "
                                "focus:outline-none focus:ring-2 focus:ring-brand-indigo focus:border-brand-indigo"
                            )
                        }
                    ),
                )
            else:
                # Default to text field
                field = forms.CharField(
                    label=question.question_text,
                    required=field_required,
                    widget=forms.TextInput(
                        attrs={
                            "class": (
                                "w-full px-3 py-2 border border-gray-300 rounded-md "
                                "focus:outline-none focus:ring-2 focus:ring-brand-indigo focus:border-brand-indigo"
                            )
                        }
                    ),
                )

            self.fields[field_name] = field

        # Populate form fields with existing draft data if available
        if self.instance and self.instance.pk and self.instance.responses:
            for question in questions:
                field_name = f"question_{question.id}"
                if field_name in self.fields and question.question_text in self.instance.responses:
                    saved_value = self.instance.responses[question.question_text]
                    # Set initial value regardless of whether it's empty or not
                    self.fields[field_name].initial = saved_value or ""

    def full_clean(self):
        """
        Override full_clean to handle draft vs submission validation differently
        """
        # Check if this is a draft save by looking at the POST data
        if hasattr(self, "data") and self.data.get("action") == "save_draft":
            # For draft saves, temporarily make all fields non-required
            original_required = {}
            for field_name, field in self.fields.items():
                if field_name.startswith("question_"):
                    original_required[field_name] = field.required
                    field.required = False

            # Perform validation with non-required fields
            super().full_clean()

            # Restore original required status for future use
            for field_name, was_required in original_required.items():
                if field_name in self.fields:
                    self.fields[field_name].required = was_required
        else:
            # Normal validation for submissions
            super().full_clean()

    def clean(self):
        cleaned_data = super().clean()

        # Validate user has organization membership
        if not self.user.memberships.exists():
            raise ValidationError(_("You must be a member of an organization to submit responses."))

        return cleaned_data

    def save(self, commit=True):
        # Create the response instance
        response = super().save(commit=False)
        response.solicitation = self.solicitation
        response.submitted_by = self.user

        # Get user's primary organization
        user_org = self.user.memberships.first().organization
        response.organization = user_org

        # Prepare the dynamic responses as JSON
        responses_data = {}
        for field_name, value in self.cleaned_data.items():
            if field_name.startswith("question_"):
                question_id = field_name.split("_")[1]
                try:
                    question = SolicitationQuestion.objects.get(id=question_id)
                    # For drafts, save all values (including empty ones to preserve user's clearing of fields)
                    # For submissions, only save non-empty values
                    if self.is_draft_save:
                        responses_data[question.question_text] = value
                    elif value:  # For submission, only save non-empty values
                        responses_data[question.question_text] = value
                except SolicitationQuestion.DoesNotExist:
                    continue

        # CRITICAL: Ensure responses is always set before any save operation
        # This prevents the IntegrityError for null values
        if not hasattr(response, "responses") or response.responses is None:
            response.responses = responses_data
        else:
            response.responses = responses_data

        if commit:
            response.save()

        return response
