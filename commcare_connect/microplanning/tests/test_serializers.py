import pytest

from commcare_connect.microplanning.serializers import (
    WORK_AREA_CASE_TYPE,
    WorkAreaCaseSerializer,
    _coords_to_lat_lon_string,
)
from commcare_connect.microplanning.tests.factories import WorkAreaFactory, WorkAreaGroupFactory


@pytest.mark.django_db
def test_work_area_case_serializer():
    group = WorkAreaGroupFactory(name="group-a")
    work_area = WorkAreaFactory(
        slug="my-area",
        ward="ward-x",
        work_area_group=group,
        building_count=5,
        expected_visit_count=10,
        case_properties={
            "max_wag": "3",
            "wag_serial_number": "WAG123",
            "lga": "LGA1",
            "state": "State1",
        },
    )

    data = WorkAreaCaseSerializer(work_area).data

    centroid = _coords_to_lat_lon_string(work_area.centroid.coords)
    bounding_box = ""
    if work_area.boundary:
        lat_lon = [_coords_to_lat_lon_string(coords) for coords in list(work_area.boundary.shell.coords)]
        bounding_box = " ".join(lat_lon)

    assert data == {
        "case_name": "my-area",
        "case_type": WORK_AREA_CASE_TYPE,
        "external_id": str(work_area.id),
        "owner_id": None,
        "properties": {
            "bounding_box": bounding_box,
            "bounding_box_wkt": str(work_area.boundary),
            "building_count": "5",
            "centroid": centroid,
            "centroid_wkt": str(work_area.centroid),
            "expected_visit_count": "10",
            "wa_status": work_area.status,
            "ward": "ward-x",
            "work_area_group": "group-a",
            "work_area_group_id": str(group.id),
            "max_wag": "3",
            "wag_serial_number": "WAG123",
            "lga": "LGA1",
            "state": "State1",
        },
    }
