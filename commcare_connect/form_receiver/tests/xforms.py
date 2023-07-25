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


def get_form(xmlns=DEFAULT_XMLNS, form_block=None):
    form = MOCK_FORM.copy()
    form["form"]["@xmlns"] = xmlns
    if form_block:
        form["form"].update(form_block)
    return form
