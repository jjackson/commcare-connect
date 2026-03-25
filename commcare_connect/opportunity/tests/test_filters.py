import pytest
from waffle.testutils import override_switch

from commcare_connect.flags.switch_names import USER_VISIT_FILTERS
from commcare_connect.opportunity.filters import TasksFilterSet, UserVisitFilterSet
from commcare_connect.opportunity.models import CompletedTaskStatus, OpportunityAccess, UserVisit
from commcare_connect.opportunity.tests.factories import (
    CompletedTaskFactory,
    CompletedWorkFactory,
    DeliverUnitFactory,
    OpportunityAccessFactory,
    OpportunityFactory,
    OpportunityVerificationFlagsFactory,
    PaymentUnitFactory,
    TaskFactory,
    UserVisitFactory,
)
from commcare_connect.utils.flags import Flags


@pytest.mark.django_db
@override_switch(USER_VISIT_FILTERS, active=True)
def test_uservisit_filterset_filters_by_flags():
    opportunity = OpportunityFactory()
    OpportunityVerificationFlagsFactory(
        opportunity=opportunity,
        duplicate=True,
        gps=False,
        location=0,
        catchment_areas=False,
    )

    access = OpportunityAccessFactory(opportunity=opportunity)
    payment_unit = PaymentUnitFactory(opportunity=opportunity)
    deliver_unit = DeliverUnitFactory(app=opportunity.deliver_app, payment_unit=payment_unit)
    completed_work_flagged = CompletedWorkFactory(opportunity_access=access, payment_unit=payment_unit)
    completed_work_clean = CompletedWorkFactory(opportunity_access=access, payment_unit=payment_unit)

    flagged_visit = UserVisitFactory(
        opportunity=opportunity,
        opportunity_access=access,
        user=access.user,
        deliver_unit=deliver_unit,
        completed_work=completed_work_flagged,
        flagged=True,
        flag_reason={"flags": [(Flags.DUPLICATE.value, "Duplicate submission")]},
    )
    clean_visit = UserVisitFactory(
        opportunity=opportunity,
        opportunity_access=access,
        user=access.user,
        deliver_unit=deliver_unit,
        completed_work=completed_work_clean,
        flagged=False,
        flag_reason=None,
    )

    filterset = UserVisitFilterSet(
        data={"flags": [Flags.DUPLICATE.value]},
        queryset=UserVisit.objects.filter(opportunity=opportunity),
        opportunity=opportunity,
    )

    assert "flags" in filterset.filters
    available_flags = dict(filterset.filters["flags"].extra["choices"])
    assert Flags.DUPLICATE.value in available_flags

    filtered_visits = set(filterset.qs.values_list("id", flat=True))
    assert flagged_visit.id in filtered_visits
    assert clean_visit.id not in filtered_visits


@pytest.mark.django_db
@override_switch(USER_VISIT_FILTERS, active=False)
def test_uservisit_filterset_user_only_when_switch_disabled():
    opportunity = OpportunityFactory()
    OpportunityAccessFactory(opportunity=opportunity)

    filterset = UserVisitFilterSet(
        data={},
        queryset=UserVisit.objects.filter(opportunity=opportunity),
        opportunity=opportunity,
    )

    assert list(filterset.filters.keys()) == ["user"]


@pytest.mark.django_db
@override_switch(USER_VISIT_FILTERS, active=False)
def test_uservisit_filterset_filters_by_user_id():
    opp = OpportunityFactory()
    access_1 = OpportunityAccessFactory(opportunity=opp)
    access_2 = OpportunityAccessFactory(opportunity=opp)

    visit_1 = UserVisitFactory(opportunity=opp, opportunity_access=access_1, user=access_1.user)
    visit_2 = UserVisitFactory(opportunity=opp, opportunity_access=access_2, user=access_2.user)

    filterset = UserVisitFilterSet(
        data={"user": str(access_1.user.user_id)},
        queryset=UserVisit.objects.filter(opportunity=opp),
        opportunity=opp,
    )

    filtered_visits = set(filterset.qs.values_list("id", flat=True))
    assert visit_1.id in filtered_visits
    assert visit_2.id not in filtered_visits


@pytest.mark.django_db
def test_tasks_filterset_worker_name():
    opp = OpportunityFactory()
    access_alice = OpportunityAccessFactory(opportunity=opp, accepted=True, user__name="Alice Smith")
    access_bob = OpportunityAccessFactory(opportunity=opp, accepted=True, user__name="Bob Jones")
    task = TaskFactory(opportunity=opp, app=opp.deliver_app, is_active=True)
    CompletedTaskFactory(opportunity_access=access_alice, task=task)
    CompletedTaskFactory(opportunity_access=access_bob, task=task)

    qs = OpportunityAccess.objects.filter(opportunity=opp, accepted=True)
    filterset = TasksFilterSet(data={"worker_name": [str(access_alice.user.pk)]}, queryset=qs, opportunity=opp)

    assert filterset.form.is_valid()
    choices = dict(filterset.form.fields["worker_name"].choices)
    assert str(access_alice.user.pk) in choices
    assert str(access_bob.user.pk) in choices


@pytest.mark.django_db
def test_tasks_filterset_task_status_single():
    opp = OpportunityFactory()
    access = OpportunityAccessFactory(opportunity=opp, accepted=True)
    task = TaskFactory(opportunity=opp, app=opp.deliver_app, is_active=True)
    CompletedTaskFactory(opportunity_access=access, task=task, status=CompletedTaskStatus.ASSIGNED)
    CompletedTaskFactory(opportunity_access=access, task=task, status=CompletedTaskStatus.COMPLETED)

    qs = OpportunityAccess.objects.filter(opportunity=opp, accepted=True)
    filterset = TasksFilterSet(data={"task_status": [CompletedTaskStatus.COMPLETED]}, queryset=qs, opportunity=opp)

    assert filterset.form.is_valid()


@pytest.mark.django_db
def test_tasks_filterset_task_type():
    opp = OpportunityFactory()
    access = OpportunityAccessFactory(opportunity=opp, accepted=True)
    task_a = TaskFactory(opportunity=opp, app=opp.deliver_app, is_active=True, name="Survey")
    task_b = TaskFactory(opportunity=opp, app=opp.deliver_app, is_active=True, name="Follow-up")
    CompletedTaskFactory(opportunity_access=access, task=task_a)
    CompletedTaskFactory(opportunity_access=access, task=task_b)

    qs = OpportunityAccess.objects.filter(opportunity=opp, accepted=True)
    filterset = TasksFilterSet(data={"task_type": [str(task_a.pk)]}, queryset=qs, opportunity=opp)

    assert filterset.form.is_valid()
    choices = dict(filterset.form.fields["task_type"].choices)
    assert str(task_a.pk) in choices
    assert str(task_b.pk) in choices


@pytest.mark.django_db
def test_tasks_filterset_task_type_excludes_inactive():
    opp = OpportunityFactory()
    active_task = TaskFactory(opportunity=opp, app=opp.deliver_app, is_active=True, name="Active")
    inactive_task = TaskFactory(opportunity=opp, app=opp.deliver_app, is_active=False, name="Inactive")

    qs = OpportunityAccess.objects.filter(opportunity=opp, accepted=True)
    filterset = TasksFilterSet(data={}, queryset=qs, opportunity=opp)

    choices = dict(filterset.form.fields["task_type"].choices)
    assert str(active_task.pk) in choices
    assert str(inactive_task.pk) not in choices


@pytest.mark.django_db
def test_tasks_filterset_no_tasks_status():
    """The 'no_tasks' status option should be available."""
    opp = OpportunityFactory()
    qs = OpportunityAccess.objects.filter(opportunity=opp, accepted=True)
    filterset = TasksFilterSet(data={"task_status": ["no_tasks"]}, queryset=qs, opportunity=opp)

    assert filterset.form.is_valid()
