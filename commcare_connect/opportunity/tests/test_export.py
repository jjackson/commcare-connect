from django.utils.timezone import now

from commcare_connect.opportunity.export import export_user_visits
from commcare_connect.opportunity.models import UserVisit
from commcare_connect.opportunity.tests.factories import DeliverFormFactory


def test_export_user_visits(user):
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
                form_json={"form": {"name": "test_form2"}},
            ),
        ]
    )
    exporter = export_user_visits(deliver_form.opportunity, "csv")
    # TODO: update with username
    assert exporter.export() == (
        "Visit date,Username,Name of User,Form Name,Status,Form JSON\r\n"
        f"{date1.isoformat()},,{user.name},{deliver_form.name},Pending,"
        "{'form': {'name': 'test_form1'}}\r\n"
        f"{date2.isoformat()},,{user.name},{deliver_form.name},Pending,"
        "{'form': {'name': 'test_form2'}}\r\n"
    )
