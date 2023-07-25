from jsonpath_ng.ext import parse

from commcare_connect.form_receiver.const import CCC_LEARN_XMLNS

LEARN_MODULE_JSONPATH = parse("module where @xmlns")


def process_xform(domain: str, app_id: str, form: dict):
    modules = [match.value for match in LEARN_MODULE_JSONPATH.find(form) if match.value["@xmlns"] == CCC_LEARN_XMLNS]
    if modules:
        process_learn_modules(domain, app_id, modules)


def process_learn_modules(domain, app_id, modules):
    pass
