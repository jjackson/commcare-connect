from factory import Faker, LazyAttribute, SubFactory
from factory.django import DjangoModelFactory

from commcare_connect.opportunity.models import Currency
from commcare_connect.opportunity.tests.factories import DeliveryTypeFactory, OpportunityFactory
from commcare_connect.program.models import ManagedOpportunity, Program, ProgramApplication
from commcare_connect.users.tests.factories import OrganizationFactory


class ProgramFactory(DjangoModelFactory):
    name = Faker("name")
    description = Faker("text", max_nb_chars=200)
    delivery_type = SubFactory(DeliveryTypeFactory)
    budget = Faker("random_int", min=1000, max=100000)
    currency = Faker("currency_code")
    currency_fk = LazyAttribute(
        lambda o: Currency.objects.get_or_create(
            code=o.currency,
            defaults={"name": o.currency, "is_valid": True},
        )[0]
    )
    start_date = Faker("date_this_decade", before_today=True, after_today=False)
    end_date = Faker("date_this_decade", before_today=False, after_today=True)
    organization = SubFactory(OrganizationFactory)

    class Meta:
        model = Program


class ManagedOpportunityFactory(OpportunityFactory):
    program = SubFactory(ProgramFactory)
    org_pay_per_visit = Faker("random_int", min=500, max=1000)

    class Meta:
        model = ManagedOpportunity


class ProgramApplicationFactory(DjangoModelFactory):
    program = SubFactory(ProgramFactory)
    organization = SubFactory(OrganizationFactory)
    date_created = Faker("date_this_decade", before_today=True, after_today=False)

    class Meta:
        model = ProgramApplication
