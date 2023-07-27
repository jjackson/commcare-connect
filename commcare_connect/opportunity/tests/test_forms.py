import datetime
import random

from factory.fuzzy import FuzzyDate, FuzzyText

from commcare_connect.opportunity.forms import OpportunityCreationForm
from commcare_connect.opportunity.tests.factories import ApplicationFactory


class TestOpportunityCreationForm:
    learn_app = ApplicationFactory()
    deliver_app = ApplicationFactory()
    applications = [learn_app, deliver_app]

    def _get_opportunity(self):
        deliver_form = self.deliver_app["forms"][0]
        return {
            "name": "Test opportunity",
            "description": FuzzyText(length=150).fuzz(),
            "end_date": FuzzyDate(start_date=datetime.date.today()).fuzz(),
            "max_visits_per_user": 100,
            "daily_max_visits_per_user": 10,
            "total_budget": 100,
            "budget_per_visit": 10,
            "learn_app": self.learn_app["id"],
            "learn_app_description": FuzzyText(length=150).fuzz(),
            "learn_app_passing_score": random.randint(30, 100),
            "deliver_app": self.deliver_app["id"],
            "deliver_form": deliver_form["id"],
        }

    def test_with_correct_data(self):
        opportunity = self._get_opportunity()
        form = OpportunityCreationForm(
            opportunity,
            applications=self.applications,
        )

        assert form.is_valid()
        assert len(form.errors) == 0

    def test_incorrect_end_date(self):
        opportunity = self._get_opportunity()
        opportunity.update(
            end_date=FuzzyDate(start_date=(datetime.date.today() - datetime.timedelta(days=20))).fuzz(),
        )

        form = OpportunityCreationForm(
            opportunity,
            applications=self.applications,
        )

        assert not form.is_valid()
        assert len(form.errors) == 1
        assert "end_date" in form.errors

    def test_same_learn_deliver_apps(self):
        opportunity = self._get_opportunity()
        opportunity.update(
            deliver_app=self.learn_app["id"],
            deliver_form=self.learn_app["forms"][0]["id"],
        )

        form = OpportunityCreationForm(
            opportunity,
            applications=self.applications,
        )

        assert not form.is_valid()
        assert len(form.errors) == 2
        assert "learn_app" in form.errors
        assert "deliver_app" in form.errors

    def test_daily_max_visits_greater_than_max_visits(self):
        opportunity = self._get_opportunity()
        opportunity.update(
            daily_max_visits_per_user=1000,
            max_visits_per_user=100,
        )

        form = OpportunityCreationForm(
            opportunity,
            applications=self.applications,
        )

        assert not form.is_valid()
        assert len(form.errors) == 1
        assert "daily_max_visits_per_user" in form.errors

    def test_budget_per_visit_greater_than_total_budget(self):
        opportunity = self._get_opportunity()
        opportunity.update(
            budget_per_visit=1000,
            total_budget=100,
        )

        form = OpportunityCreationForm(
            opportunity,
            applications=self.applications,
        )

        assert not form.is_valid()
        assert len(form.errors) == 1
        assert "budget_per_visit" in form.errors
