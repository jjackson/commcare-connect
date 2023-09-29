import pytest
from django.utils.timezone import now

from commcare_connect.opportunity.export import export_user_visit_data, get_flattened_dataset
from commcare_connect.opportunity.forms import DateRanges
from commcare_connect.opportunity.models import UserVisit
from commcare_connect.opportunity.tests.factories import DeliverUnitFactory, OpportunityFactory


def test_export_user_visit_data(mobile_user_with_connect_link):
    deliver_unit = DeliverUnitFactory()
    opportunity = OpportunityFactory()
    date1 = now()
    date2 = now()
    UserVisit.objects.bulk_create(
        [
            UserVisit(
                opportunity=opportunity,
                user=mobile_user_with_connect_link,
                visit_date=date1,
                deliver_unit=deliver_unit,
                form_json={"form": {"name": "test_form1"}},
            ),
            UserVisit(
                opportunity=opportunity,
                user=mobile_user_with_connect_link,
                visit_date=date2,
                deliver_unit=deliver_unit,
                form_json={"form": {"name": "test_form2", "group": {"q": "b"}}},
            ),
        ]
    )
    exporter = export_user_visit_data(opportunity, DateRanges.LAST_30_DAYS, [])
    username = mobile_user_with_connect_link.username
    name = mobile_user_with_connect_link.name

    assert exporter.export("csv") == (
        "Visit ID,Visit date,Status,Username,Name of User,Unit Name,form.name,form.group.q\r\n"
        f",{date1.isoformat()},Pending,{username},{name},{deliver_unit.name},test_form1,\r\n"
        f",{date2.isoformat()},Pending,{username},{name},{deliver_unit.name},test_form2,b\r\n"
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
