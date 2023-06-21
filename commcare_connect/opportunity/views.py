from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, ListView, UpdateView

from commcare_connect.opportunity.forms import OpportunityChangeForm, OpportunityCreationForm
from commcare_connect.opportunity.models import Opportunity
from commcare_connect.users.models import Organization


@method_decorator(login_required, name="dispatch")
class OpportunityList(ListView):
    model = Opportunity
    paginate_by = 10

    def get_context_data(self, *args, object_list=None, **kwargs):
        context_data = super().get_context_data(*args, **kwargs)
        context_data["org_slug"] = self.kwargs["org_slug"]
        return context_data

    def get_queryset(self):
        return Opportunity.objects.filter(organization__slug=self.kwargs["org_slug"])


@method_decorator(login_required, name="dispatch")
class OpportunityCreate(CreateView):
    template_name = "opportunity/opportunity_create.html"
    form_class = OpportunityCreationForm

    def get_success_url(self):
        return reverse("opportunity:opportunity_list", args=(self.kwargs.get("org_slug"),))

    def form_valid(self, form):
        form.instance.created_by = self.request.user.email
        form.instance.modified_by = self.request.user.email
        form.instance.organization = Organization.objects.filter(slug=self.kwargs["org_slug"]).first()
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Create new opportunity"
        return context


@method_decorator(login_required, name="dispatch")
class OpportunityEdit(UpdateView):
    model = Opportunity
    template_name = "opportunity/opportunity_create.html"
    form_class = OpportunityChangeForm

    def get_success_url(self):
        return reverse("opportunity:opportunity_list", args=(self.kwargs.get("org_slug"),))

    def form_valid(self, form):
        form.instance.modified_by = self.request.user.email
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edit opportunity"
        return context
