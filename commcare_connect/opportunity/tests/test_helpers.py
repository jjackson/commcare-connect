import pytest

from commcare_connect.opportunity.helpers import get_annotated_opportunity_access_deliver_status
from commcare_connect.opportunity.models import Opportunity
from commcare_connect.opportunity.tests.factories import CompletedWorkFactory, OpportunityAccessFactory
from commcare_connect.users.tests.factories import MobileUserFactory


@pytest.mark.django_db
def test_deliver_status_query_no_visits(opportunity: Opportunity):
    mobile_users = list(MobileUserFactory.create_batch(5))
    for mobile_user in mobile_users:
        OpportunityAccessFactory(opportunity=opportunity, user=mobile_user, accepted=True)
    access_objects = get_annotated_opportunity_access_deliver_status(opportunity)

    usernames = {user.username for user in mobile_users}
    for access in access_objects:
        assert access.user.username in usernames
        assert access.visits_approved == 0
        assert access.visits_rejected == 0
        assert access.visits_pending == 0
        assert access.visits_over_limit == 0
        assert access.visits_completed == 0
        assert access.visits_duplicate == 0


@pytest.mark.django_db
def test_deliver_status_query(opportunity: Opportunity):
    mobile_users = MobileUserFactory.create_batch(5)
    completed_work_counts = {}
    for mobile_user in mobile_users:
        access = OpportunityAccessFactory(opportunity=opportunity, user=mobile_user, accepted=True)
        completed_works = CompletedWorkFactory.create_batch(20, opportunity_access=access)
        count_by_status = dict(approved=0, pending=0, rejected=0, completed=0)
        for user_visit in completed_works:
            count_by_status[user_visit.status.value] += 1
        count_by_status["completed"] = len(completed_works)
        completed_work_counts[mobile_user.username] = count_by_status

    access_objects = get_annotated_opportunity_access_deliver_status(opportunity)
    for access in access_objects:
        username = access.user.username
        assert username in completed_work_counts
        assert completed_work_counts[username]["approved"] == access.approved
        assert completed_work_counts[username]["rejected"] == access.rejected
        assert completed_work_counts[username]["pending"] == access.pending
        assert completed_work_counts[username]["completed"] == access.completed


@pytest.mark.django_db
def test_deliver_status_query_visits_another_opportunity(opportunity: Opportunity):
    # Test user visit counts when visits are for another opportunity. Should return 0 for all counts as the user has
    # done no visits in the current opportunity.
    mobile_users = list(MobileUserFactory.create_batch(5))
    for mobile_user in mobile_users:
        OpportunityAccessFactory(opportunity=opportunity, user=mobile_user, accepted=True)
        CompletedWorkFactory.create_batch(5)
    access_objects = get_annotated_opportunity_access_deliver_status(opportunity)
    usernames = {user.username for user in mobile_users}
    for access in access_objects:
        assert access.user.username in usernames
        assert access.visits_approved == 0
        assert access.visits_rejected == 0
        assert access.visits_pending == 0
        assert access.visits_completed == 0
