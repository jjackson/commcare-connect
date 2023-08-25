from django.utils.encoding import force_str
from flatten_dict import flatten
from tablib import Dataset

from commcare_connect.opportunity.models import Opportunity, UserVisit
from commcare_connect.opportunity.tables import UserVisitTable


def export_user_visits(opportunity: Opportunity) -> Dataset:
    """Export all user visits for an opportunity."""
    user_visits = UserVisit.objects.filter(opportunity=opportunity)
    table = UserVisitTable(user_visits)
    exclude_columns = ("visit_date",)
    columns = [
        column
        for column in table.columns.iterall()
        if not (column.column.exclude_from_export or column.name in exclude_columns)
    ]
    base_data = [[row.get_cell_value(column.name) for column in columns] for row in table.rows]
    base_headers = [force_str(column.header, strings_only=True) for column in columns]
    return get_flattened_dataset(base_headers, base_data)


def get_flattened_dataset(headers: list[str], data: list[list]) -> Dataset:
    """Flatten the form json and add it to the dataset.

    :param headers: The headers for the dataset.
    :param data: The data for the dataset. It is expected that the last column in each row
        is the form JSON data.
    """
    schema = set()
    flat_data = []
    for row in data:
        form_json = row.pop()
        flat_json = flatten(form_json, reducer="dot", enumerate_types=(list,))
        flat_data.append(flat_json)
        schema.update(flat_json.keys())

    schema = sorted(schema, key=_schema_sort)
    headers = headers[:-1] + schema
    dataset = Dataset(title="Export", headers=headers)

    for row, flat_json in zip(data, flat_data):
        row.extend(flat_json.get(key, "") for key in schema)
        dataset.append([force_str(col, strings_only=True) for col in row])

    return dataset


def _schema_sort(item):
    return len(item.split(".")), item
