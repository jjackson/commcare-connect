from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView, UpdateView
from django_tables2 import SingleTableView

from commcare_connect.opportunity.forms import OpportunityChangeForm, OpportunityCreationForm
from commcare_connect.opportunity.models import CompletedModule, Opportunity, OpportunityAccess, UserVisit
from commcare_connect.opportunity.tables import OpportunityAccessTable, UserVisitTable
from commcare_connect.opportunity.tasks import create_learn_modules_assessments
from commcare_connect.utils.commcarehq_api import get_applications_for_user


class OrganizationUserMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.org_membership is not None


class OpportunityList(OrganizationUserMixin, ListView):
    model = Opportunity
    paginate_by = 10

    def get_queryset(self):
        return Opportunity.objects.filter(organization__slug=self.request.org)


class OpportunityCreate(OrganizationUserMixin, CreateView):
    template_name = "opportunity/opportunity_create.html"
    form_class = OpportunityCreationForm

    def get_success_url(self):
        return reverse("opportunity:list", args=(self.request.org,))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["applications"] = get_applications_for_user(self.request.user)
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["applications"] = get_applications_for_user(self.request.user)
        kwargs["user"] = self.request.user
        kwargs["org_slug"] = self.request.org
        return kwargs

    def form_valid(self, form: OpportunityCreationForm) -> HttpResponse:
        response = super().form_valid(form)
        create_learn_modules_assessments.delay(self.object.id)
        return response


class OpportunityEdit(OrganizationUserMixin, UpdateView):
    model = Opportunity
    template_name = "opportunity/opportunity_create.html"
    form_class = OpportunityChangeForm

    def get_success_url(self):
        return reverse("opportunity:list", args=(self.request.org,))

    def form_valid(self, form):
        form.instance.modified_by = self.request.user.email
        return super().form_valid(form)


class OpportunityDetail(OrganizationUserMixin, DetailView):
    model = Opportunity
    template_name = "opportunity/opportunity_detail.html"


class OpportunityUserTableView(OrganizationUserMixin, SingleTableView):
    model = OpportunityAccess
    paginate_by = 25
    table_class = OpportunityAccessTable
    template_name = "tables/single_table.html"

    def get_queryset(self):
        opportunity_id = self.kwargs["pk"]
        opportunity = get_object_or_404(Opportunity, organization=self.request.org, id=opportunity_id)
        return OpportunityAccess.objects.filter(opportunity=opportunity)


class OpportunityUserVisitTableView(OrganizationUserMixin, SingleTableView):
    model = UserVisit
    paginate_by = 25
    table_class = UserVisitTable
    template_name = "tables/single_table.html"

    def get_queryset(self):
        opportunity_id = self.kwargs["pk"]
        opportunity = get_object_or_404(Opportunity, organization=self.request.org, id=opportunity_id)
        return UserVisit.objects.filter(opportunity=opportunity)


class OpportunityUserLearnProgress(DetailView):
    template_name = "opportunity/user_learn_progress.html"

    def get_queryset(self):
        return OpportunityAccess.objects.filter(opportunity_id=self.kwargs.get("opp_id"))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["completed_modules"] = CompletedModule.objects.filter(
            user=self.object.user,
            opportunity_id=self.kwargs.get("opp_id"),
        )
        return context
