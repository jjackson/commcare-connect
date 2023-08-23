from django.contrib import messages
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext

from commcare_connect.organization.decorators import org_admin_required
from commcare_connect.organization.forms import OrganizationChangeForm
from commcare_connect.organization.models import Organization


@org_admin_required
def organization_home(request, org_slug):
    org = get_object_or_404(Organization, slug=org_slug)

    form = None
    if request.method == "POST":
        form = OrganizationChangeForm(request.POST, instance=org)
        if form.is_valid():
            messages.success(request, gettext("Organization details saved!"))
            form.save()

    if not form:
        form = OrganizationChangeForm(instance=org)

    return render(
        request,
        "organization/organization_home.html",
        {
            "organization": org,
            "form": form,
        },
    )
