from datetime import datetime, timedelta

from commcare_connect.form_receiver.serializers import XFormSerializer
from commcare_connect.form_receiver.tests.xforms import get_form_json


def test_xform_serializer():
    received_on = "2023-06-07T12:34:12.153323Z"
    time_start = "2023-06-07T12:33:10.178000Z"
    time_end = "2023-06-07T12:34:10.718000Z"

    form_json = get_form_json(
        **{
            "domain": "ccc-test",
            "id": "23456",
            "app_id": "7890",
            "build_id": "app build id",
            "received_on": received_on,
        }
    )
    form_json["metadata"]["app_build_version"] = "abcd"
    form_json["metadata"]["timeStart"] = time_start
    form_json["metadata"]["timeEnd"] = time_end
    serializer = XFormSerializer(data=form_json)
    serializer.is_valid(raise_exception=True)
    xform = serializer.save()
    assert xform.domain == "ccc-test"
    assert xform.id == "23456"
    assert xform.app_id == "7890"
    assert xform.build_id == "app build id"
    assert xform.received_on == datetime.fromisoformat(received_on)
    assert xform.metadata.timeStart == datetime.fromisoformat(time_start)
    assert xform.metadata.timeEnd == datetime.fromisoformat(time_end)
    assert xform.metadata.duration == timedelta(seconds=60, microseconds=540000)
    assert xform.metadata.app_build_version == "abcd"
    assert xform.form == form_json["form"]


def test_xform_serializer_null_build():
    form_json = get_form_json(
        **{
            "build_id": None,
        }
    )
    form_json["metadata"]["app_build_version"] = None
    serializer = XFormSerializer(data=form_json)
    serializer.is_valid(raise_exception=True)
    xform = serializer.save()
    assert xform.build_id is None
    assert xform.metadata.app_build_version is None
