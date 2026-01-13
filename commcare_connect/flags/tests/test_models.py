import pytest
from django.core.cache import cache

from commcare_connect.flags.tests.factories import FlagFactory
from commcare_connect.opportunity.tests.factories import OpportunityFactory
from commcare_connect.program.tests.factories import ProgramFactory


@pytest.fixture
def flag():
    return FlagFactory()


@pytest.fixture
def program():
    return ProgramFactory()


@pytest.mark.django_db
class TestFlagModel:
    def setup_method(self):
        cache.clear()

    def test_flag_enabled(self, flag, organization, opportunity, program):
        flag.organizations.add(organization)
        assert flag.is_active_for(organization) is True

        flag.opportunities.add(opportunity)
        assert flag.is_active_for(opportunity) is True

        flag.programs.add(program)
        assert flag.is_active_for(program) is True

    def test_flag_not_enabled(self, flag, opportunity):
        flag.opportunities.add(opportunity)
        another_opp = OpportunityFactory()
        assert flag.is_active_for(another_opp) is False

    def test_invalid_object(self, flag):
        invalid_obj = {"name": "test"}
        assert flag.is_active_for(invalid_obj) is False
