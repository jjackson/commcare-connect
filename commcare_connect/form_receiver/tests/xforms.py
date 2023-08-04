from copy import deepcopy

from xml2json import xml2json

from commcare_connect.form_receiver.const import CCC_LEARN_XMLNS
from commcare_connect.form_receiver.serializers import XFormSerializer

DEFAULT_XMLNS = "http://openrosa.org/formdesigner/67D08BE6-BBEE-452D-AE73-34DCC3A742C1"
FORM_META = {
    "@xmlns": "http://openrosa.org/jr/xforms",
    "appVersion": "Formplayer Version: 2.53",
    "app_build_version": 53,
    "commcare_version": None,
    "deviceID": "Formplayer",
    "instanceID": "f469597c-7587-4029-ba9d-215ce7660674",
    "timeEnd": "2023-06-07T12:34:11.718000Z",
    "timeStart": "2023-06-07T12:34:10.178000Z",
    "userID": "66da891a459b2781c28bf2e0c50cbe67",
    "username": "test",
}

MOCK_FORM = {
    "app_id": "0c0a8beabdc4b83bc84fd457f2b047a2",
    "archived": False,
    "build_id": "2614cb25dbf44ed29527164281e8b7dd",
    "domain": "ccc-test",
    "form": {"#type": "data", "@name": "Form Name", "@uiVersion": "1", "@version": "53", "meta": FORM_META},
    "id": "f469597c-7587-4029-ba9d-215ce7660674",
    "metadata": FORM_META,
    "received_on": "2023-06-07T12:34:12.153323Z",
    "server_modified_on": "2023-06-07T12:34:12.509392Z",
}

MODULE_XML_TEMPLATE = (
    """<data>
<module xmlns="%s" id="{id}">
    <name>{name}</name>
    <description>{description}</description>
    <time_estimate>{time_estimate}</time_estimate>
</module>
</data>
"""
    % CCC_LEARN_XMLNS
)

ASSESSMENT_XML_TEMPLATE = (
    """<data>
<assessment xmlns="%s" id="{id}">
    <user_score>{score}</user_score>
</assessment>
</data>"""
    % CCC_LEARN_XMLNS
)


def get_form_json(xmlns=DEFAULT_XMLNS, form_block=None, **kwargs):
    form = deepcopy(MOCK_FORM)
    form["form"]["@xmlns"] = xmlns
    if form_block:
        form["form"].update(form_block)
    form.update(kwargs)
    return form


def get_form_model(xmlns=DEFAULT_XMLNS, form_block=None):
    form_json = get_form_json(xmlns, form_block)
    serializer = XFormSerializer(data=form_json)
    serializer.is_valid(raise_exception=True)
    return serializer.save()


def get_learn_module(
    module_id: str = "module1",
    name: str = "Test Module",
    description: str = "Test Description",
    time_estimate: int = 2,
):
    xml = MODULE_XML_TEMPLATE.format(id=module_id, name=name, description=description, time_estimate=time_estimate)
    _, module = xml2json(xml)
    return module


def get_assessment(
    assessment_id: str = "assessment1",
    score: int = 75,
):
    xml = ASSESSMENT_XML_TEMPLATE.format(id=assessment_id, score=score)
    _, module = xml2json(xml)
    return module
