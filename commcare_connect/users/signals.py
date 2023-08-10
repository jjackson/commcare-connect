from allauth.account.signals import user_signed_up
from django.dispatch import receiver

from commcare_connect.organization.models import Organization, UserOrganizationMembership
from commcare_connect.users.models import User


@receiver(user_signed_up)
def create_org_for_user(request, user, **kwargs):
    if not user.members.exists():
        _create_default_org_for_user(user)


def _create_default_org_for_user(user: User):
    organization = Organization.objects.create(name=user.email.split("@")[0])
    organization.members.add(user, through_defaults={"role": UserOrganizationMembership.Role.ADMIN})
    organization.save()
    return organization
