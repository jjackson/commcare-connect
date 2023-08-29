import pytest
from django.utils.timezone import now

from commcare_connect.opportunity.export import export_user_visit_data, get_flattened_dataset
from commcare_connect.opportunity.models import UserVisit
from commcare_connect.opportunity.tests.factories import DeliverFormFactory


def test_export_user_visit_data(user):
    deliver_form = DeliverFormFactory()
    date1 = now()
    date2 = now()
    UserVisit.objects.bulk_create(
        [
            UserVisit(
                opportunity=deliver_form.opportunity,
                user=user,
                visit_date=date1,
                deliver_form=deliver_form,
                form_json={"form": {"name": "test_form1"}},
            ),
            UserVisit(
                opportunity=deliver_form.opportunity,
                user=user,
                visit_date=date2,
                deliver_form=deliver_form,
                form_json={"form": {"name": "test_form2", "group": {"q": "b"}}},
            ),
        ]
    )
    exporter = export_user_visit_data(deliver_form.opportunity)
    # TODO: update with username
    assert exporter.export("csv") == (
        "Visit ID,Visit date,Status,Username,Name of User,Form Name,form.name,form.group.q\r\n"
        f",{date1.isoformat()},Pending,,{user.name},{deliver_form.name},test_form1,\r\n"
        f",{date2.isoformat()},Pending,,{user.name},{deliver_form.name},test_form2,b\r\n"
    )


@pytest.mark.parametrize(
    "data, expected",
    [
        (
            {"form": {"name": "form1"}},
            [
                (
                    "form.name",
                    "form1",
                )
            ],
        ),
        ({"form": [{"name": "form1"}, {"name": "form2"}]}, [("form.0.name", "form1"), ("form.1.name", "form2")]),
    ],
)
def test_get_flattened_dataset(data, expected):
    headers = ["header1", "header2", "header3"]
    data = [
        ["value1", "value2", data],
    ]
    dataset = get_flattened_dataset(headers, data)
    assert dataset.headers == ["header1", "header2"] + [x[0] for x in expected]
    assert dataset[0] == ("value1", "value2") + tuple(x[1] for x in expected)
