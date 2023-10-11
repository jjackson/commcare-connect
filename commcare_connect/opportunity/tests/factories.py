from factory import CREATE_STRATEGY, DictFactory, Faker, SelfAttribute, SubFactory
from factory.django import DjangoModelFactory

from commcare_connect.opportunity.models import VisitValidationStatus
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


class DeliverUnitFactory(DjangoModelFactory):
    app = SubFactory(CommCareAppFactory)
    slug = Faker("pystr")
    name = Faker("name")

    class Meta:
        model = "opportunity.DeliverUnit"


class UserVisitFactory(DjangoModelFactory):
    opportunity = SubFactory(OpportunityFactory)
    user = SubFactory("commcare_connect.users.tests.factories.UserFactory")
    deliver_unit = SubFactory(DeliverUnitFactory)
    entity_id = Faker("uuid4")
    entity_name = Faker("name")
    status = Faker("enum", enum_cls=VisitValidationStatus)
    visit_date = Faker("date")
    form_json = Faker("pydict", value_types=[str, int, float, bool])

    class Meta:
        model = "opportunity.UserVisit"


class OpportunityAccessFactory(DjangoModelFactory):
    opportunity = SubFactory(OpportunityFactory)
    user = SubFactory("commcare_connect.users.tests.factories.UserFactory")

    class Meta:
        model = "opportunity.OpportunityAccess"


class CompletedModuleFactory(DjangoModelFactory):
    opportunity = SubFactory(OpportunityFactory)
    user = SubFactory("commcare_connect.users.tests.factories.UserFactory")
    date = Faker("date")
    module = SubFactory(LearnModuleFactory, app=SelfAttribute("..opportunity.learn_app"))
    duration = Faker("time_delta")

    class Meta:
        model = "opportunity.CompletedModule"
