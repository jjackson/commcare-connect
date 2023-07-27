from factory import CREATE_STRATEGY, DictFactory, Faker


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
