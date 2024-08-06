from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse
from django.views.generic import ListView, UpdateView

from commcare_connect.opportunity.views import OpportunityInit
from commcare_connect.program.forms import ManagedOpportunityInitForm, ProgramForm
from commcare_connect.program.models import ManagedOpportunity, Program


class SuperUserMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser


ALLOWED_ORDERINGS = {
    "name": "name",
    "-name": "-name",
    "start_date": "start_date",
    "-start_date": "-start_date",
    "end_date": "end_date",
    "-end_date": "-end_date",
}


class ProgramList(SuperUserMixin, ListView):
    model = Program
    paginate_by = 10
    default_ordering = "name"

    def get_queryset(self):
        ordering = self.request.GET.get("sort", self.default_ordering)
        ordering = ALLOWED_ORDERINGS.get(ordering, self.default_ordering)
        return Program.objects.all().order_by(ordering)


class ProgramCreateOrUpdate(SuperUserMixin, UpdateView):
    model = Program
    form_class = ProgramForm

    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk")
        if pk:
            return super().get_object(queryset)
        return None

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        is_edit = self.object is not None
        response = super().form_valid(form)
        status = ("created", "updated")[is_edit]
        message = f"Program '{self.object.name}' {status} successfully."
        messages.success(self.request, message)
        return response

    def get_success_url(self):
        return reverse("program:list", kwargs={"org_slug": self.request.org.slug})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_edit"] = self.object is not None
        return context

    def get_template_names(self):
        view = ("add", "edit")[self.object is not None]
        template = f"program/program_{view}.html"
        return template


class ManagedOpportunityList(SuperUserMixin, ListView):
    model = ManagedOpportunity
    paginate_by = 10
    default_ordering = "name"
    template_name = "opportunity/opportunity_list.html"

    def get_queryset(self):
        ordering = self.request.GET.get("sort", self.default_ordering)
        ordering = ALLOWED_ORDERINGS.get(ordering, self.default_ordering)
        program_id = self.kwargs.get("pk")
        return ManagedOpportunity.objects.filter(program_id=program_id).order_by(ordering)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["program_id"] = self.kwargs.get("pk")
        context["add_opp_url"] = reverse(
            "program:opportunity_init", kwargs={"org_slug": self.request.org.slug, "pk": self.kwargs.get("pk")}
        )
        return context


class ManagedOpportunityInit(SuperUserMixin, OpportunityInit):
    form_class = ManagedOpportunityInitForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["program_id"] = self.kwargs.get("pk")
        return kwargs
