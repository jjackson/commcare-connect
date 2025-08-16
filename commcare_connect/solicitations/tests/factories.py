from datetime import timedelta

import factory
from django.utils import timezone

from commcare_connect.program.tests.factories import ProgramFactory
from commcare_connect.solicitations.models import (
    QuestionType,
    ResponseStatus,
    Solicitation,
    SolicitationQuestion,
    SolicitationResponse,
    SolicitationStatus,
    SolicitationType,
)
from commcare_connect.users.tests.factories import OrganizationFactory, UserFactory


class SolicitationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Solicitation

    title = factory.Faker("catch_phrase")
    description = factory.Faker("text", max_nb_chars=500)
    target_population = factory.Faker("sentence", nb_words=6)
    scope_of_work = factory.Faker("text", max_nb_chars=300)
    solicitation_type = factory.Iterator([SolicitationType.EOI, SolicitationType.RFP])
    status = SolicitationStatus.ACTIVE
    is_publicly_listed = True
    program = factory.SubFactory(ProgramFactory)
    created_by = factory.SubFactory(UserFactory)
    application_deadline = factory.LazyFunction(lambda: timezone.now().date() + timedelta(days=30))
    estimated_scale = factory.Faker("sentence", nb_words=4)
    expected_start_date = factory.LazyFunction(lambda: timezone.now().date() + timedelta(days=60))
    expected_end_date = factory.LazyFunction(lambda: timezone.now().date() + timedelta(days=365))


class EOIFactory(SolicitationFactory):
    """Factory specifically for EOIs"""

    solicitation_type = SolicitationType.EOI
    title = factory.Sequence(lambda n: f"EOI: Health Initiative {n}")


class RFPFactory(SolicitationFactory):
    """Factory specifically for RFPs"""

    solicitation_type = SolicitationType.RFP
    title = factory.Sequence(lambda n: f"RFP: Implementation Proposal {n}")


class SolicitationQuestionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SolicitationQuestion

    solicitation = factory.SubFactory(SolicitationFactory)
    question_text = factory.Faker("sentence", nb_words=8)
    question_type = factory.Iterator(
        [QuestionType.TEXT, QuestionType.TEXTAREA, QuestionType.NUMBER, QuestionType.FILE]
    )
    is_required = True
    order = factory.Sequence(lambda n: n + 1)


class SolicitationResponseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SolicitationResponse

    solicitation = factory.SubFactory(SolicitationFactory)
    organization = factory.SubFactory(OrganizationFactory)
    submitted_by = factory.SubFactory(UserFactory)
    responses = factory.Dict(
        {
            "question_1": factory.Faker("text", max_nb_chars=200),
            "question_2": factory.Faker("text", max_nb_chars=200),
            "question_3": factory.Faker("random_int", min=1, max=100),
        }
    )
    status = ResponseStatus.SUBMITTED


class SolicitationWithQuestionsFactory(SolicitationFactory):
    """Factory that creates a solicitation with associated questions"""

    @factory.post_generation
    def questions(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            # If specific questions were provided
            for question_data in extracted:
                SolicitationQuestionFactory(solicitation=self, **question_data)
        else:
            # Create default questions
            default_questions = [
                {
                    "question_text": "Describe your organization's relevant experience",
                    "question_type": QuestionType.TEXTAREA,
                    "order": 1,
                },
                {"question_text": "How many staff can you deploy?", "question_type": QuestionType.NUMBER, "order": 2},
                {
                    "question_text": "Upload your organization registration",
                    "question_type": QuestionType.FILE,
                    "order": 3,
                },
            ]

            for question_data in default_questions:
                SolicitationQuestionFactory(solicitation=self, **question_data)
