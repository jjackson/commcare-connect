import django_filters
from crispy_forms.helper import FormHelper
from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from waffle import switch_is_active

from commcare_connect.flags.switch_names import USER_VISIT_FILTERS
from commcare_connect.opportunity.models import (
    CompletedTaskStatus,
    DeliverUnitFlagRules,
    OpportunityAccess,
    OpportunityVerificationFlags,
    Task,
    UserVisit,
    VisitValidationStatus,
)
from commcare_connect.program.models import Program
from commcare_connect.users.models import User
from commcare_connect.utils.flags import FlagLabels, Flags


class FilterMixin:
    """
    Usage:
        - Define a filter using django_filters.FilterSet
        - Mixin this on a view and set filter_class to the above filter
        - Use get_filter_form() to use it in the template
        - Use get_filter_values() to get filter values in the template
    """

    filter_class = None

    def _get_filter_class(self):
        return self.filter_class

    def get_filter_kwargs(self):
        """
        Override this in subclasses to pass extra kwargs to the filterset.
        Always include `queryset`.
        """
        return {
            "queryset": OpportunityAccess.objects.none(),
            "request": self.request,
        }

    def _get_filter(self):
        if not hasattr(self, "_filter_instance"):
            filter_class = self._get_filter_class()
            if filter_class:
                self._filter_instance = filter_class(self.request.GET, **self.get_filter_kwargs())
            else:
                self._filter_instance = None
        return self._filter_instance

    def get_filter_form(self):
        f = self._get_filter()
        if f:
            return f.form
        return None

    def get_filter_values(self):
        f = self._get_filter()
        if f and f.form.is_valid():
            return {name: f.form.cleaned_data.get(name) for name in f.filters.keys()}
        return {}

    def get_filter_usage_data(self):
        values = self.get_filter_values()
        applied = [k for k, v in values.items() if v not in (None, "", [])]
        if not applied:
            return None

        return {
            "filters": applied,
            "filter_count": len(applied),
            "page_path": self.request.path,
        }

    def filters_applied_count(self):
        return len([v for v in self.get_filter_values().values() if v not in (None, "", [])])

    def get_filter_context(self):
        return {
            "filter_form": self.get_filter_form(),
            "filters_applied_count": self.filters_applied_count(),
            "filter_usage_data": self.get_filter_usage_data(),
        }


class CSRFExemptForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.disable_csrf = True


class YesNoFilter(django_filters.BooleanFilter):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault(
            "widget",
            forms.Select(
                choices=[
                    ("", "---------"),
                    (True, "Yes"),
                    (False, "No"),
                ]
            ),
        )
        super().__init__(*args, **kwargs)


class DeliverFilterSet(django_filters.FilterSet):
    last_active = django_filters.ChoiceFilter(
        label="Last Active",
        choices=(
            (1, "1 day ago"),
            (3, "3 days ago"),
            (7, "7 days ago"),
        ),
        empty_label="Any time",
    )
    has_duplicates = YesNoFilter(
        label="Has Duplicate Deliveries",
    )
    has_flags = YesNoFilter(
        label="Deliveries with flags",
    )
    has_overlimit = YesNoFilter(
        label="Has Overlimit Deliveries",
    )
    review_pending = YesNoFilter(
        label="Deliveries with Pending Review",
    )

    class Meta:
        form = CSRFExemptForm


class OpportunityListFilterSet(django_filters.FilterSet):
    is_test = YesNoFilter(label="Is Test")
    status = django_filters.MultipleChoiceFilter(
        label="Status",
        choices=[(0, "Active"), (1, "Ended"), (2, "Inactive")],
        widget=forms.SelectMultiple(attrs={"data-tomselect": "1"}),
    )
    program = django_filters.MultipleChoiceFilter(
        label="Program", choices=[], widget=forms.SelectMultiple(attrs={"data-tomselect": "1"})
    )

    class Meta:
        form = CSRFExemptForm

    def __init__(self, *args, **kwargs):
        request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        if request:
            user_programs = Program.objects.filter(organization=request.org)
            if user_programs.exists():
                self.filters["program"].extra["choices"] = [(p.slug, p.name) for p in user_programs]
            else:
                del self.filters["program"]


class UserVisitFilterSet(django_filters.FilterSet):
    user = django_filters.ChoiceFilter(
        label="Worker",
        choices=[],
        empty_label="All",
        widget=forms.Select(attrs={"data-tomselect": "1"}),
        method="filter_user",
    )
    visit_date = django_filters.DateFilter(
        label="Visit Date",
        field_name="visit_date",
        lookup_expr="date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    status = django_filters.MultipleChoiceFilter(
        label="Visit Status",
        choices=[
            (c.value, c.label)
            for c in [VisitValidationStatus.over_limit, VisitValidationStatus.duplicate, VisitValidationStatus.trial]
        ],
        widget=forms.SelectMultiple(attrs={"data-tomselect": "1"}),
    )
    flagged = YesNoFilter(label="Flagged")
    flags = django_filters.MultipleChoiceFilter(
        label="Flags",
        choices=[],
        widget=forms.SelectMultiple(attrs={"data-tomselect": "1"}),
        method="filter_flags",
    )

    class Meta:
        model = UserVisit
        fields = ["user", "visit_date", "status", "flagged", "flags"]
        form = CSRFExemptForm

    def __init__(self, *args, **kwargs):
        opportunity = kwargs.pop("opportunity", None)
        super().__init__(*args, **kwargs)

        if not switch_is_active(USER_VISIT_FILTERS):
            self._restrict_to_user_filter()

        if opportunity and "user" in self.filters:
            user_filter = self.filters["user"]
            user_queryset = (
                User.objects.filter(opportunityaccess__opportunity=opportunity).distinct().order_by("name", "username")
            )
            user_choices = [(str(user.user_id), user.display_name_with_username()) for user in user_queryset]
            user_filter.extra["choices"] = user_choices

        if opportunity and "flags" in self.filters:
            flag_choices = self._get_flag_choices(opportunity)
            if flag_choices:
                self.filters["flags"].extra["choices"] = flag_choices
            else:
                del self.filters["flags"]

    def filter_flags(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.with_any_flags(value)

    def filter_user(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(user__user_id=value)

    def _restrict_to_user_filter(self):
        for filter_name in list(self.filters.keys()):
            if filter_name != "user":
                del self.filters[filter_name]

    def _get_flag_choices(self, opportunity):
        verification_flags = OpportunityVerificationFlags.objects.filter(opportunity=opportunity).first()
        if not verification_flags:
            return []

        enabled_flags = []
        if verification_flags.duplicate:
            enabled_flags.append(Flags.DUPLICATE.value)
        if verification_flags.gps:
            enabled_flags.append(Flags.GPS.value)
        if verification_flags.location and verification_flags.location > 0:
            enabled_flags.append(Flags.LOCATION.value)
        if verification_flags.catchment_areas:
            enabled_flags.append(Flags.CATCHMENT.value)
        if verification_flags.form_submission_start or verification_flags.form_submission_end:
            enabled_flags.append(Flags.FORM_SUBMISSION_PERIOD.value)

        deliver_unit_flag_rules = DeliverUnitFlagRules.objects.filter(opportunity=opportunity).all()
        for rule in deliver_unit_flag_rules:
            if rule.duration > 0:
                enabled_flags.append(Flags.DURATION.value)
            if rule.check_attachments:
                enabled_flags.append(Flags.ATTACHMENT_MISSING.value)
        return [(flag, FlagLabels.get_label(flag)) for flag in set(enabled_flags)]


NO_TASKS_FILTER_VALUE = "no_tasks"

TASK_STATUS_CHOICES = [
    (CompletedTaskStatus.ASSIGNED, _("To Do")),
    (CompletedTaskStatus.COMPLETED, _("Completed")),
    (NO_TASKS_FILTER_VALUE, _("No Tasks")),
]


class TasksFilterSet(django_filters.FilterSet):
    worker_name = django_filters.MultipleChoiceFilter(
        label="Worker Name",
        choices=[],
        widget=forms.SelectMultiple(attrs={"data-tomselect": "1"}),
        method="filter_worker_name",
    )
    task_status = django_filters.MultipleChoiceFilter(
        label="Task Status",
        choices=TASK_STATUS_CHOICES,
        widget=forms.SelectMultiple(attrs={"data-tomselect": "1"}),
        method="filter_task_status",
    )
    task_type = django_filters.MultipleChoiceFilter(
        label="Task Type",
        choices=[],
        widget=forms.SelectMultiple(attrs={"data-tomselect": "1"}),
        method="filter_task_type",
    )
    date_assigned_after = django_filters.DateFilter(
        label="Date Assigned From",
        widget=forms.DateInput(attrs={"type": "date"}),
        method="filter_date_assigned_after",
    )
    date_assigned_before = django_filters.DateFilter(
        label="Date Assigned To",
        widget=forms.DateInput(attrs={"type": "date"}),
        method="filter_date_assigned_before",
    )
    due_date_after = django_filters.DateFilter(
        label="Due Date From",
        widget=forms.DateInput(attrs={"type": "date"}),
        method="filter_due_date_after",
    )
    due_date_before = django_filters.DateFilter(
        label="Due Date To",
        widget=forms.DateInput(attrs={"type": "date"}),
        method="filter_due_date_before",
    )

    class Meta:
        form = CSRFExemptForm

    def __init__(self, *args, **kwargs):
        self.opportunity = kwargs.pop("opportunity", None)
        super().__init__(*args, **kwargs)
        if self.opportunity:
            active_tasks = Task.objects.filter(opportunity=self.opportunity, is_active=True)
            self.filters["task_type"].extra["choices"] = [(str(t.pk), t.name) for t in active_tasks]

            worker_queryset = (
                User.objects.filter(
                    opportunityaccess__opportunity=self.opportunity,
                    opportunityaccess__accepted=True,
                )
                .distinct()
                .order_by("name", "username")
            )
            self.filters["worker_name"].extra["choices"] = [
                (str(user.pk), user.display_name_with_username()) for user in worker_queryset
            ]

    def filter_worker_name(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(user__pk__in=[int(pk) for pk in value])

    def filter_task_status(self, queryset, name, value):
        if not value:
            return queryset
        status_q = Q()
        real_statuses = [s for s in value if s != NO_TASKS_FILTER_VALUE]
        if real_statuses:
            status_q |= Q(task_status__in=real_statuses)
        if NO_TASKS_FILTER_VALUE in value:
            status_q |= Q(task_status__isnull=True)
        return queryset.filter(status_q)

    def filter_task_type(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(task_id__in=[int(t) for t in value])

    def filter_date_assigned_after(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(date_assigned__date__gte=value)

    def filter_date_assigned_before(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(date_assigned__date__lte=value)

    def filter_due_date_after(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(task_due_date__gte=value)

    def filter_due_date_before(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(task_due_date__lte=value)
