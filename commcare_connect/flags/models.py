from django.db import models
from waffle.models import AbstractUserFlag

from commcare_connect.opportunity.models import Opportunity
from commcare_connect.organization.models import Organization
from commcare_connect.program.models import Program


# See https://waffle.readthedocs.io/en/stable/types/flag.html#custom-flag-models
class Flag(AbstractUserFlag):
    organizations = models.ManyToManyField(
        Organization,
        blank=True,
        help_text="Activate this flag for these organizations.",
    )
    opportunities = models.ManyToManyField(
        Opportunity,
        blank=True,
        help_text="Activate this flag for these opportunities.",
    )
    programs = models.ManyToManyField(
        Program,
        blank=True,
        help_text="Activate this flag for these programs.",
    )
