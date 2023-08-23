from factory import CREATE_STRATEGY, DictFactory, Faker, RelatedFactory, SelfAttribute, SubFactory
from factory.django import DjangoModelFactory

from commcare_connect.users.tests.factories import OrganizationFactory


class ApplicationFormsFactory(DictFactory):
    id = Faker("pystr")
    name = Faker("name")
    xmlns = Faker("url")
    module = Faker("pystr")


class ApplicationFactory(DictFactory):
    id = Faker("pystr")
    name = Faker("name")
    domain = Faker("name")
    forms = ApplicationFormsFactory.generate_batch(CREATE_STRATEGY, 5)


class CommCareAppFactory(DjangoModelFactory):
    organization = SubFactory(OrganizationFactory)
    cc_domain = Faker("name")
    cc_app_id = Faker("uuid4")
    name = Faker("name")
    description = Faker("text")
    passing_score = Faker("pyint", min_value=50, max_value=100, step=5)

    class Meta:
        model = "opportunity.CommCareApp"


class OpportunityFactory(DjangoModelFactory):
    organization = SubFactory(OrganizationFactory)
    name = Faker("name")
    description = Faker("text")
    active = True
    learn_app = SubFactory(CommCareAppFactory, organization=SelfAttribute("..organization"))
    deliver_app = SubFactory(CommCareAppFactory, organization=SelfAttribute("..organization"))
    max_visits_per_user = Faker("pyint", min_value=1, max_value=100)
    daily_max_visits_per_user = Faker("pyint", min_value=1, max_value=SelfAttribute("..max_visits_per_user"))
    end_date = Faker("date")
    budget_per_visit = Faker("pyint", min_value=100, max_value=1000)
    total_budget = Faker("pyint", min_value=1000, max_value=10000)

    deliver_form = RelatedFactory(
        "commcare_connect.opportunity.tests.factories.DeliverFormFactory",
        factory_related_name="opportunity",
        app=SelfAttribute("..deliver_app"),
    )

    class Meta:
        model = "opportunity.Opportunity"


class LearnModuleFactory(DjangoModelFactory):
    app = SubFactory(CommCareAppFactory)
    slug = Faker("pystr")
    name = Faker("name")
    description = Faker("text")
    time_estimate = Faker("pyint", min_value=1, max_value=10)

    class Meta:
        model = "opportunity.LearnModule"


class DeliverFormFactory(DjangoModelFactory):
    app = SubFactory(CommCareAppFactory)
    opportunity = SubFactory(
        OpportunityFactory,
        deliver_app=SelfAttribute("..app"),
        organization=SelfAttribute("..app.organization"),
        deliver_form=None,
    )
    name = Faker("name")
    xmlns = Faker("url")

    class Meta:
        model = "opportunity.DeliverForm"
