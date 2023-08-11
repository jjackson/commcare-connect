from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpResponse
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from commcare_connect.opportunity.forms import OpportunityChangeForm, OpportunityCreationForm
from commcare_connect.opportunity.models import CompletedModule, Opportunity, OpportunityAccess
from commcare_connect.opportunity.tasks import create_learn_modules_assessments
from commcare_connect.utils.commcarehq_api import get_applications_for_user


class OrganizationUserMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.org_membership is not None


class OpportunityList(OrganizationUserMixin, ListView):
    model = Opportunity
    paginate_by = 10

    def get_context_data(self, *args, object_list=None, **kwargs):
        context_data = super().get_context_data(*args, **kwargs)
        context_data["org_slug"] = self.kwargs["org_slug"]
        return context_data

    def get_queryset(self):
        return Opportunity.objects.filter(organization__slug=self.kwargs["org_slug"])


class OpportunityCreate(OrganizationUserMixin, CreateView):
    template_name = "opportunity/opportunity_create.html"
    form_class = OpportunityCreationForm

    def get_success_url(self):
        return reverse("opportunity:list", args=(self.kwargs.get("org_slug"),))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Create new opportunity"
        context["applications"] = get_applications_for_user(self.request.user)
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["applications"] = get_applications_for_user(self.request.user)
        kwargs["user"] = self.request.user
        kwargs["org_slug"] = self.kwargs.get("org_slug")
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
        return reverse("opportunity:list", args=(self.kwargs.get("org_slug"),))

    def form_valid(self, form):
        form.instance.modified_by = self.request.user.email
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edit opportunity"
        return context


class OpportunityDetail(OrganizationUserMixin, DetailView):
    model = Opportunity
    template_name = "opportunity/opportunity_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["org_slug"] = self.kwargs["org_slug"]
        return context


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
