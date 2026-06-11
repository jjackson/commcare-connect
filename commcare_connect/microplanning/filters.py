import django_filters
from django import forms
from django.utils.translation import gettext_lazy as _

from commcare_connect.microplanning.coverage_progress import CoverageDateFilter
from commcare_connect.microplanning.models import WorkArea, WorkAreaStatus
from commcare_connect.opportunity.filters import CSRFExemptForm
from commcare_connect.opportunity.models import UserVisit
from commcare_connect.users.models import User

INPUT_CSS = (
    "w-full rounded-md border border-gray-300 px-3 py-2 "
    "text-sm shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
)

# Coverage Progress date-filter modes.
RANGE_OVERALL = "overall"
RANGE_LAST_WEEK = "last_week"
RANGE_CUSTOM = "custom"
COVERAGE_RANGE_CHOICES = (
    (RANGE_OVERALL, _("Overall")),
    (RANGE_LAST_WEEK, _("Last week")),
    (RANGE_CUSTOM, _("Custom range")),
)


class CoverageProgressFilterSet(django_filters.FilterSet):
    """Date filter for the Coverage Progress Tracker page.

    The page's date window is an *aggregation parameter* (it bounds the subqueries inside
    ``CoverageProgressReport``), not a queryset ``.filter()`` — so this FilterSet is used only for
    parsing / validating / rendering the form. ``.qs`` is never evaluated; ``to_date_filter()`` maps
    the cleaned form data onto the already-defined ``CoverageDateFilter`` modes.
    """

    range = django_filters.ChoiceFilter(
        label=_("Date range"),
        choices=COVERAGE_RANGE_CHOICES,
        empty_label=None,
        method="_noop",
        # x-model binds to the page's Alpine scope, which toggles the custom date inputs.
        widget=forms.Select(attrs={"class": INPUT_CSS, "x-model": "range"}),
    )
    start = django_filters.DateFilter(
        label=_("From"),
        method="_noop",
        widget=forms.DateInput(attrs={"type": "date", "class": INPUT_CSS}),
    )
    end = django_filters.DateFilter(
        label=_("To"),
        method="_noop",
        widget=forms.DateInput(attrs={"type": "date", "class": INPUT_CSS}),
    )

    class Meta:
        model = WorkArea
        fields = []
        form = CSRFExemptForm

    def _noop(self, queryset, name, value):
        # The filters never narrow a queryset; the cleaned values are read via to_date_filter().
        return queryset

    def to_date_filter(self) -> CoverageDateFilter:
        """Resolve the submitted form to a CoverageDateFilter, falling back to overall() when the
        custom range is incomplete or reversed (the page's existing lenient behavior)."""
        if not self.form.is_valid():
            return CoverageDateFilter.overall()
        cd = self.form.cleaned_data
        if cd.get("range") == RANGE_LAST_WEEK:
            return CoverageDateFilter.last_week()
        if cd.get("range") == RANGE_CUSTOM and cd.get("start") and cd.get("end") and cd["start"] <= cd["end"]:
            return CoverageDateFilter(start=cd["start"], end=cd["end"])
        return CoverageDateFilter.overall()


class WorkAreaMapFilterSet(django_filters.FilterSet):
    status = django_filters.MultipleChoiceFilter(
        label=_("Work Area Status"),
        choices=WorkAreaStatus.choices,
        widget=forms.SelectMultiple(attrs={"data-tomselect": "1", "class": INPUT_CSS}),
    )

    assignee = django_filters.ModelMultipleChoiceFilter(
        label=_("Assignee"),
        field_name="opportunity_access__user",
        queryset=User.objects.none(),
        widget=forms.SelectMultiple(attrs={"data-tomselect": "1", "class": INPUT_CSS}),
    )

    start_date = django_filters.DateFilter(
        label=_("Start Date"),
        field_name="uservisit__visit_date",
        lookup_expr="date__gte",
        widget=forms.DateInput(attrs={"type": "date", "class": INPUT_CSS}),
    )

    end_date = django_filters.DateFilter(
        label=_("End Date"),
        field_name="uservisit__visit_date",
        lookup_expr="date__lte",
        widget=forms.DateInput(attrs={"type": "date", "class": INPUT_CSS}),
    )

    unassigned_only = django_filters.BooleanFilter(
        label=_("Show Only Unassigned"),
        method="filter_unassigned_only",
    )

    class Meta:
        model = WorkArea
        fields = []
        form = CSRFExemptForm

    @property
    def qs(self):
        return super().qs.distinct()

    def __init__(self, *args, opportunity=None, **kwargs):
        super().__init__(*args, **kwargs)
        if opportunity:
            self.filters["assignee"].queryset = (
                User.objects.filter(
                    opportunityaccess__opportunity=opportunity,
                    opportunityaccess__workarea__isnull=False,
                )
                .distinct()
                .order_by("name")
            )

        # Display "name (username)" instead of default __str__
        # which shows email or username (not useful for mobile workers)
        self.filters["assignee"].field.label_from_instance = lambda obj: obj.display_name_with_username()

    def filter_unassigned_only(self, queryset, name, value):
        if value:
            return queryset.filter(opportunity_access__isnull=True)
        return queryset


class UserVisitMapFilterSet(django_filters.FilterSet):
    status = django_filters.MultipleChoiceFilter(
        field_name="work_area__status",
        choices=WorkAreaStatus.choices,
    )

    assignee = django_filters.ModelMultipleChoiceFilter(
        field_name="user",
        queryset=User.objects.none(),
    )

    start_date = django_filters.DateFilter(
        field_name="visit_date",
        lookup_expr="date__gte",
    )

    end_date = django_filters.DateFilter(
        field_name="visit_date",
        lookup_expr="date__lte",
    )

    class Meta:
        model = UserVisit
        fields = []
        form = CSRFExemptForm

    def __init__(self, *args, opportunity=None, **kwargs):
        super().__init__(*args, **kwargs)
        if opportunity:
            self.filters["assignee"].queryset = (
                User.objects.filter(
                    opportunityaccess__opportunity=opportunity,
                    opportunityaccess__workarea__isnull=False,
                )
                .distinct()
                .order_by("name")
            )
