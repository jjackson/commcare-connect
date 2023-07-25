from commcare_connect.users.models import Organization


def get_organization_for_request(request, view_kwargs):
    if not request.user.is_authenticated:
        return

    org_slug = view_kwargs.get('org_slug', None)
    if org_slug:
        try:
            return Organization.objects.get(slug=org_slug, memberships__user=request.user)
        except Organization.DoesNotExist:
            return None

    membership = request.user.memberships.select_related("organization").first()
    return membership.organization if membership else None
