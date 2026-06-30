import pytest

from commcare_connect.audit.tables import AuditReportTable
from commcare_connect.opportunity.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "name,username,expected",
    [
        ("Jane Auditor", "jane", "Jane Auditor"),
        ("", "jane", "jane"),
    ],
)
def test_render_reviewer_falls_back_to_username(name, username, expected):
    user = UserFactory.build(name=name, username=username)
    assert AuditReportTable([]).render_reviewer(user) == expected


def test_reviewer_column_default_for_no_reviewer():
    assert AuditReportTable([]).base_columns["reviewer"].default == "—"
