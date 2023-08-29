from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.text import slugify
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView
from django_tables2 import SingleTableView
from django_tables2.export import TableExport

from commcare_connect.opportunity.export import export_user_visit_data
from commcare_connect.opportunity.forms import OpportunityChangeForm, OpportunityCreationForm
from commcare_connect.opportunity.models import CompletedModule, Opportunity, OpportunityAccess, UserVisit
from commcare_connect.opportunity.tables import OpportunityAccessTable, UserVisitTable
from commcare_connect.opportunity.tasks import add_connect_users, create_learn_modules_assessments
from commcare_connect.opportunity.visit_import import ImportException, bulk_update_visit_status
from commcare_connect.organization.decorators import org_member_required
from commcare_connect.utils.commcarehq_api import get_applications_for_user


class OrganizationUserMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.org_membership is not None


class OpportunityList(OrganizationUserMixin, ListView):
    model = Opportunity
    paginate_by = 10

    def get_queryset(self):
        return Opportunity.objects.filter(organization=self.request.org)


class OpportunityCreate(OrganizationUserMixin, CreateView):
    template_name = "opportunity/opportunity_create.html"
    form_class = OpportunityCreationForm

    def get_success_url(self):
        return reverse("opportunity:list", args=(self.request.org.slug,))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["applications"] = get_applications_for_user(self.request.user)
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["applications"] = get_applications_for_user(self.request.user)
        kwargs["user"] = self.request.user
        kwargs["org_slug"] = self.request.org.slug
        return kwargs

    def form_valid(self, form: OpportunityCreationForm) -> HttpResponse:
        response = super().form_valid(form)
        create_learn_modules_assessments.delay(self.object.id)
        return response


class OpportunityEdit(OrganizationUserMixin, UpdateView):
    model = Opportunity
    template_name = "opportunity/opportunity_edit.html"
    form_class = OpportunityChangeForm

    def get_success_url(self):
        return reverse("opportunity:list", args=(self.request.org.slug,))

    def form_valid(self, form):
        form.instance.modified_by = self.request.user.email
        response = super().form_valid(form)
        add_connect_users.delay(form.cleaned_data["users"], form.instance.id)
        return response


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
        return OpportunityAccess.objects.filter(opportunity=opportunity).order_by("user__name")


class OpportunityUserVisitTableView(OrganizationUserMixin, SingleTableView):
    model = UserVisit
    paginate_by = 25
    table_class = UserVisitTable
    template_name = "tables/single_table.html"

    def get_queryset(self):
        opportunity_id = self.kwargs["pk"]
        opportunity = get_object_or_404(Opportunity, organization=self.request.org, id=opportunity_id)
        return UserVisit.objects.filter(opportunity=opportunity).order_by("visit_date")


class OpportunityUserLearnProgress(OrganizationUserMixin, DetailView):
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


@org_member_required
def export_user_visits(request, **kwargs):
    opportunity_id = kwargs["pk"]
    opportunity = get_object_or_404(Opportunity, organization=request.org, id=opportunity_id)
    export_format = request.GET.get("_export", None)
    if not TableExport.is_valid_format(export_format):
        messages.error(request, f"Invalid export format: {export_format}")
        return redirect("opportunity:detail", request.org.slug, opportunity_id)

    dataset = export_user_visit_data(opportunity)
    response = HttpResponse(content_type=TableExport.FORMATS[export_format])
    op_slug = slugify(opportunity.name)
    filename = f"{request.org.slug}-{op_slug}-user_visit_data.{export_format}"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write(dataset.export(export_format))
    return response


@org_member_required
@require_POST
def update_visit_status_import(request, org_slug=None, pk=None):
    opportunity = get_object_or_404(Opportunity, organization=request.org, id=pk)
    file = request.FILES.get("visits")
    try:
        status = bulk_update_visit_status(opportunity, file)
    except ImportException as e:
        messages.error(request, e.message)
    else:
        message = f"Visit status updated successfully for {len(status)} visits."
        if status.missing_visits:
            message += status.get_missing_message()
        messages.success(request, mark_safe(message))
    return redirect("opportunity:detail", org_slug, pk)
