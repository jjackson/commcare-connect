from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Column, Div, Field, Layout
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class SolicitationResponseForm(forms.Form):
    """
    Dynamic form for responding to solicitations.
    Fields are generated based on solicitation questions from JSON data.
    """

    # Organization selection field (will be populated in __init__)
    organization_id = forms.ChoiceField(
        label="Responding Organization",
        required=True,
        help_text="Select which organization you are responding on behalf of",
        widget=forms.Select(
            attrs={
                "class": (
                    "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none "
                    "focus:ring-2 focus:ring-brand-indigo focus:border-brand-indigo"
                )
            }
        ),
    )

    def __init__(self, solicitation, user, is_draft_save=False, instance=None, data_access=None, *args, **kwargs):
        # Extract instance from kwargs since Form doesn't handle it automatically
        self.instance = instance
        super().__init__(*args, **kwargs)
        self.solicitation = solicitation
        self.user = user
        self.is_draft_save = is_draft_save
        self.data_access = data_access

        # Get existing responses for this solicitation
        existing_responses = []
        if data_access:
            existing_responses = data_access.get_responses_for_solicitation(solicitation_record=solicitation)
        existing_org_slugs = {resp.organization_id for resp in existing_responses if resp.organization_id}

        # Populate organization choices from user's OAuth data
        # Use slug as the identifier (no local database lookup needed)
        org_choices = []
        if hasattr(user, "organizations"):
            orgs = user.organizations  # Returns list of {'slug': '...', 'name': '...'}
            for org_data in orgs:
                slug = org_data.get("slug")
                name = org_data.get("name", slug)
                if slug:
                    # Indicate if this org already has a response
                    if slug in existing_org_slugs:
                        display_name = f"{name} (Already responded - will edit)"
                    else:
                        display_name = name
                    org_choices.append((slug, display_name))

        if not org_choices:
            org_choices = [("", "No organizations available")]

        self.fields["organization_id"].choices = org_choices

        # Pre-select organization if editing existing response
        if instance and hasattr(instance, "organization_id"):
            self.fields["organization_id"].initial = instance.organization_id

        # Dynamically add fields based on solicitation questions
        # For ExperimentRecord-based solicitations, questions are in JSON
        questions = solicitation.questions if hasattr(solicitation, "questions") else []

        for question in questions:
            # Support both dict (JSON) and model object access
            q_id = question.get("id") if isinstance(question, dict) else question.id
            q_text = question.get("question_text") if isinstance(question, dict) else question.question_text
            q_type = question.get("question_type") if isinstance(question, dict) else question.question_type
            q_required = question.get("is_required", True) if isinstance(question, dict) else question.is_required
            q_options = question.get("options", []) if isinstance(question, dict) else getattr(question, "options", [])

            field_name = f"question_{q_id}"

            # For drafts, never require fields. For submission, use question's requirement
            field_required = q_required and not is_draft_save

            # CSS classes for form fields
            input_classes = (
                "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none "
                "focus:ring-2 focus:ring-brand-indigo focus:border-brand-indigo"
            )

            if q_type in ["text", "short_text"]:
                field = forms.CharField(
                    label=q_text,
                    required=field_required,
                    max_length=500,
                    widget=forms.TextInput(attrs={"class": input_classes}),
                )
            elif q_type in ["textarea", "long_text"]:
                field = forms.CharField(
                    label=q_text,
                    required=field_required,
                    widget=forms.Textarea(attrs={"rows": 4, "class": input_classes}),
                )
            elif q_type == "number":
                field = forms.IntegerField(
                    label=q_text,
                    required=field_required,
                    widget=forms.NumberInput(attrs={"class": input_classes}),
                )
            elif q_type in ["file", "file_upload"]:
                # File fields are never required (as per user request)
                field = forms.FileField(
                    label=q_text,
                    required=False,
                    widget=forms.FileInput(attrs={"class": input_classes}),
                )
            elif q_type == "multiple_choice":
                choices = [("", "Select an option...")]  # Add empty choice for optional fields
                if q_options:
                    for option in q_options:
                        choices.append((option, option))
                field = forms.ChoiceField(
                    label=q_text,
                    required=field_required,
                    choices=choices,
                    widget=forms.Select(attrs={"class": input_classes}),
                )
            else:
                # Default to text field
                field = forms.CharField(
                    label=q_text,
                    required=field_required,
                    widget=forms.TextInput(attrs={"class": input_classes}),
                )

            self.fields[field_name] = field

        # Populate form fields with existing response data if available
        if self.instance and self.instance.pk and self.instance.responses:
            for question in questions:
                q_id = question.get("id") if isinstance(question, dict) else question.id
                field_name = f"question_{q_id}"
                if field_name in self.fields and field_name in self.instance.responses:
                    saved_value = self.instance.responses[field_name]
                    # Set initial value regardless of whether it's empty or not
                    self.fields[field_name].initial = saved_value or ""

        # Setup crispy forms
        self.helper = FormHelper(self)
        self.helper.form_class = "space-y-6"
        self.helper.form_method = "post"
        self.helper.form_enctype = "multipart/form-data"
        self.helper.form_tag = False  # Let template handle form tag

        # Create dynamic layout based on questions
        layout_fields = []
        for question in questions:
            q_id = question.get("id") if isinstance(question, dict) else question.id
            field_name = f"question_{q_id}"
            if field_name in self.fields:
                layout_fields.append(
                    Div(Field(field_name, wrapper_class="border border-gray-200 rounded-lg p-6"), css_class="mb-4")
                )

        if layout_fields:
            self.helper.layout = Layout(
                Div(
                    HTML(
                        '<h4 class="text-lg font-medium text-brand-deep-purple mb-4">'
                        '<i class="fa-solid fa-clipboard-question mr-2"></i>'
                        "Application Questions</h4>"
                    ),
                    *layout_fields,
                    css_class="bg-white rounded-lg p-6 space-y-6",
                )
            )

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

        # Validate organization was selected
        org_id = cleaned_data.get("organization_id")
        if not org_id or org_id == "":
            raise ValidationError(_("You must select an organization to respond on behalf of."))

        return cleaned_data


class SolicitationForm(forms.Form):
    """
    Form for creating/editing solicitations - works with ExperimentRecord JSON storage
    Program context is now provided via labs_context instead of a form field.
    """

    # Delivery type field - choices populated dynamically in __init__
    delivery_type = forms.ChoiceField(
        required=True,
        label="Program Type",
        help_text="Select the type of program this solicitation is for",
        widget=forms.Select(
            attrs={
                "class": (
                    "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none "
                    "focus:ring-2 focus:ring-brand-indigo focus:border-brand-indigo"
                )
            }
        ),
    )

    # Define all fields
    title = forms.CharField(
        max_length=255,
        required=True,
        label="Solicitation Title",
        widget=forms.TextInput(
            attrs={
                "class": (
                    "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none "
                    "focus:ring-2 focus:ring-brand-indigo focus:border-brand-indigo"
                ),
                "placeholder": "Enter solicitation title...",
            }
        ),
    )

    description = forms.CharField(
        required=True,
        label="Description",
        widget=forms.Textarea(
            attrs={
                "class": (
                    "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none "
                    "focus:ring-2 focus:ring-brand-indigo focus:border-brand-indigo"
                ),
                "rows": 6,
                "placeholder": "Describe the solicitation, its objectives, and requirements...",
            }
        ),
        help_text="Provide a detailed description of the solicitation",
    )

    solicitation_type = forms.ChoiceField(
        choices=[("eoi", "Expression of Interest (EOI)"), ("rfp", "Request for Proposal (RFP)")],
        required=True,
        label="Type",
        widget=forms.Select(
            attrs={
                "class": (
                    "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none "
                    "focus:ring-2 focus:ring-brand-indigo focus:border-brand-indigo"
                )
            }
        ),
    )

    status = forms.ChoiceField(
        choices=[("draft", "Draft"), ("active", "Active"), ("closed", "Closed")],
        required=True,
        label="Status",
        widget=forms.Select(
            attrs={
                "class": (
                    "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none "
                    "focus:ring-2 focus:ring-brand-indigo focus:border-brand-indigo"
                )
            }
        ),
    )

    is_publicly_listed = forms.BooleanField(
        required=False,
        label="Publicly Listed",
        widget=forms.CheckboxInput(attrs={"class": "simple-checkbox"}),
        help_text="Check to make this solicitation visible in public listings",
    )

    application_deadline = forms.DateField(
        required=True,
        label="Application Deadline",
        widget=forms.DateInput(
            attrs={
                "class": (
                    "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none "
                    "focus:ring-2 focus:ring-brand-indigo focus:border-brand-indigo"
                ),
                "type": "date",
            }
        ),
    )

    expected_start_date = forms.DateField(
        required=False,
        label="Expected Start Date",
        widget=forms.DateInput(
            attrs={
                "class": (
                    "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none "
                    "focus:ring-2 focus:ring-brand-indigo focus:border-brand-indigo"
                ),
                "type": "date",
            }
        ),
    )

    expected_end_date = forms.DateField(
        required=False,
        label="Expected End Date",
        widget=forms.DateInput(
            attrs={
                "class": (
                    "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none "
                    "focus:ring-2 focus:ring-brand-indigo focus:border-brand-indigo"
                ),
                "type": "date",
            }
        ),
    )

    def __init__(self, user=None, data_access=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Populate delivery type choices from API
        delivery_type_choices = [("", "-- Select Program Type --")]
        if data_access:
            try:
                delivery_types = data_access.get_delivery_types(active_only=True)
                for dt in delivery_types:
                    delivery_type_choices.append((dt.slug, dt.name))
            except Exception:
                # If API fails, show empty choices
                pass

        self.fields["delivery_type"].choices = delivery_type_choices

        # Setup crispy forms
        self.helper = FormHelper(self)
        self.helper.form_class = "space-y-8"
        self.helper.form_id = "solicitation-form"
        self.helper.form_method = "post"
        self.helper.form_tag = False  # Template handles form tag

        self.helper.layout = Layout(
            # Hidden field for questions data (Alpine.js will populate this)
            HTML('<input type="hidden" name="questions_data" id="questions-data" value="">'),
            # Basic Information Section
            Div(
                HTML(
                    '<h2 class="text-xl font-semibold text-brand-deep-purple mb-6 pb-2 border-b border-gray-200">'
                    '<i class="fa-solid fa-info-circle mr-2"></i>Basic Information</h2>'
                ),
                Div(
                    # Title (full width)
                    Field("title", wrapper_class="mb-6"),
                    # Row 2: Type, Status, Delivery Type, and Visibility
                    Div(
                        Column(Field("solicitation_type"), css_class="flex-1"),
                        Column(Field("delivery_type"), css_class="flex-1"),
                        Column(Field("status"), css_class="flex-1"),
                        Column(Field("is_publicly_listed"), css_class="flex-1"),
                        css_class="flex flex-col md:flex-row gap-6 mb-6",
                    ),
                    # Description
                    Field("description", wrapper_class="mb-6"),
                    # Timeline Fields Row
                    Div(
                        Column(Field("application_deadline"), css_class="flex-1"),
                        Column(Field("expected_start_date"), css_class="flex-1"),
                        Column(Field("expected_end_date"), css_class="flex-1"),
                        css_class="flex flex-col md:flex-row gap-4 mb-6",
                    ),
                    css_class="space-y-6",
                ),
                css_class="bg-white rounded-xl shadow-sm p-8 mb-8",
            ),
        )

    def clean(self):
        cleaned_data = super().clean()

        # Validate date ranges
        start_date = cleaned_data.get("expected_start_date")
        end_date = cleaned_data.get("expected_end_date")
        deadline = cleaned_data.get("application_deadline")

        if start_date and end_date and start_date >= end_date:
            raise ValidationError("Expected end date must be after the start date.")

        if deadline and start_date and deadline >= start_date:
            raise ValidationError("Application deadline must be before the expected start date.")

        return cleaned_data


class SolicitationReviewForm(forms.Form):
    """
    Form for reviewing solicitation responses - works with ExperimentRecord JSON storage
    """

    score = forms.IntegerField(
        label="Score (1-100)",
        min_value=1,
        max_value=100,
        required=False,
        widget=forms.NumberInput(attrs={"placeholder": "Enter score 1-100"}),
    )

    notes = forms.CharField(
        label="Review Notes",
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Add your review notes..."}),
        required=False,
        help_text="Provide detailed feedback about this response",
    )

    tags = forms.CharField(
        label="Tags",
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "e.g., strong-technical, needs-clarification"}),
        help_text="Add comma-separated tags to categorize this response",
    )

    recommendation = forms.ChoiceField(
        label="Recommendation",
        choices=[
            ("", "-- Select --"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("needs_revision", "Needs Revision"),
            ("under_review", "Under Review"),
        ],
        required=False,
        help_text="Your overall recommendation for this response",
    )

    def __init__(self, *args, **kwargs):
        # Extract instance from kwargs since Form doesn't handle it
        instance = kwargs.pop("instance", None)
        super().__init__(*args, **kwargs)

        # Populate fields from instance if editing existing review
        if instance and hasattr(instance, "data"):
            self.fields["score"].initial = instance.data.get("score")
            self.fields["notes"].initial = instance.data.get("notes")
            self.fields["tags"].initial = instance.data.get("tags", "")
            self.fields["recommendation"].initial = instance.data.get("recommendation")

        # Setup crispy forms
        self.helper = FormHelper(self)
        self.helper.form_method = "post"
        self.helper.form_tag = False  # Let template handle form tag
        self.helper.form_class = "space-y-6"

        self.helper.layout = Layout(
            Div(
                HTML('<h2 class="text-xl font-semibold text-brand-deep-purple mb-6">Your Review</h2>'),
                # First row - Review Notes (full width)
                Field("notes", wrapper_class="mb-6"),
                # Second row - Score, Recommendation, and Tags (three columns)
                Div(
                    Column(Field("score"), css_class="flex-1"),
                    Column(Field("recommendation"), css_class="flex-1"),
                    Column(Field("tags"), css_class="flex-1"),
                    css_class="flex flex-col md:flex-row gap-4 mb-6",
                ),
                css_class="bg-white rounded-xl shadow-sm p-8",
            )
        )
