import pytest

from commcare_connect.opportunity.filters import TasksFilterSet
from commcare_connect.opportunity.helpers import get_worker_tasks_base_queryset
from commcare_connect.opportunity.models import AssignedTaskStatus
from commcare_connect.opportunity.tests.factories import (
    AssignedTaskFactory,
    OpportunityAccessFactory,
    OpportunityFactory,
    TaskTypeFactory,
)


@pytest.mark.django_db
def test_tasks_filterset_worker_name():
    opp = OpportunityFactory()
    access_alice = OpportunityAccessFactory(opportunity=opp, accepted=True, user__name="Alice Smith")
    access_bob = OpportunityAccessFactory(opportunity=opp, accepted=True, user__name="Bob Jones")
    task_type = TaskTypeFactory(opportunity=opp, app=opp.deliver_app, is_active=True)
    AssignedTaskFactory(opportunity_access=access_alice, task_type=task_type)
    AssignedTaskFactory(opportunity_access=access_bob, task_type=task_type)

    qs = get_worker_tasks_base_queryset(opp)
    filterset = TasksFilterSet(data={"worker_name": [str(access_alice.user.pk)]}, queryset=qs, opportunity=opp)

    assert filterset.form.is_valid()
    choices = dict(filterset.form.fields["worker_name"].choices)
    assert str(access_alice.user.pk) in choices
    assert str(access_bob.user.pk) in choices
    result = list(filterset.qs)
    assert len(result) == 1
    assert result[0].user == access_alice.user


@pytest.mark.django_db
def test_tasks_filterset_task_status_single():
    opp = OpportunityFactory()
    access = OpportunityAccessFactory(opportunity=opp, accepted=True)
    task_type = TaskTypeFactory(opportunity=opp, app=opp.deliver_app, is_active=True)
    AssignedTaskFactory(opportunity_access=access, task_type=task_type, status=AssignedTaskStatus.ASSIGNED)
    AssignedTaskFactory(opportunity_access=access, task_type=task_type, status=AssignedTaskStatus.COMPLETED)

    qs = get_worker_tasks_base_queryset(opp)
    filterset = TasksFilterSet(data={"task_status": [AssignedTaskStatus.COMPLETED]}, queryset=qs, opportunity=opp)

    assert filterset.form.is_valid()
    result = list(filterset.qs)
    assert len(result) == 1
    assert result[0].task_status == AssignedTaskStatus.COMPLETED


@pytest.mark.django_db
def test_tasks_filterset_task_type():
    opp = OpportunityFactory()
    access = OpportunityAccessFactory(opportunity=opp, accepted=True)
    task_a = TaskTypeFactory(opportunity=opp, app=opp.deliver_app, is_active=True, name="Survey")
    task_b = TaskTypeFactory(opportunity=opp, app=opp.deliver_app, is_active=True, name="Follow-up")
    AssignedTaskFactory(opportunity_access=access, task_type=task_a)
    AssignedTaskFactory(opportunity_access=access, task_type=task_b)

    qs = get_worker_tasks_base_queryset(opp)
    filterset = TasksFilterSet(data={"task_type": [str(task_a.pk)]}, queryset=qs, opportunity=opp)

    assert filterset.form.is_valid()
    choices = dict(filterset.form.fields["task_type"].choices)
    assert str(task_a.pk) in choices
    assert str(task_b.pk) in choices
    result = list(filterset.qs)
    assert len(result) == 1
    assert result[0].task_name == task_a.name


@pytest.mark.django_db
def test_tasks_filterset_task_type_excludes_inactive():
    opp = OpportunityFactory()
    active_task = TaskTypeFactory(opportunity=opp, app=opp.deliver_app, is_active=True, name="Active")
    inactive_task = TaskTypeFactory(opportunity=opp, app=opp.deliver_app, is_active=False, name="Inactive")

    qs = get_worker_tasks_base_queryset(opp)
    filterset = TasksFilterSet(data={}, queryset=qs, opportunity=opp)

    choices = dict(filterset.form.fields["task_type"].choices)
    assert str(active_task.pk) in choices
    assert str(inactive_task.pk) not in choices
