from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext
from rest_framework.decorators import api_view

from commcare_connect.organization.decorators import org_admin_required
from commcare_connect.organization.forms import MembershipForm, OrganizationChangeForm
from commcare_connect.organization.models import Organization, UserOrganizationMembership
from commcare_connect.organization.tasks import send_org_invite


@org_admin_required
def organization_home(request, org_slug):
    org = get_object_or_404(Organization, slug=org_slug)

    form = None
    membership_form = MembershipForm(organization=org)
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
        {"organization": org, "form": form, "membership_form": membership_form},
    )


@api_view(["POST"])
@login_required
def add_members_form(request, org_slug):
    org = get_object_or_404(Organization, slug=org_slug)
    form = MembershipForm(request.POST or None, organization=org)

    if form.is_valid():
        form.instance.organization = org
        form.save()
        send_org_invite.delay(membership_id=form.instance.pk, host_user_id=request.user.pk)

    return redirect("organization:home", org_slug)


@login_required
def accept_invite(request, org_slug, invite_id):
    membership = get_object_or_404(UserOrganizationMembership, invite_id=invite_id)
    organization = membership.organization

    if membership.accepted:
        return redirect("organization:home", org_slug)

    membership.accepted = True
    membership.save()
    messages.success(request, message=f"Accepted invite for joining {organization.slug} organization.")
    return redirect("organization:home", org_slug)
