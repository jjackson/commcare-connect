from jsonpath_ng import JSONPathError
from jsonpath_ng.ext import parse

from commcare_connect.form_receiver.const import CCC_LEARN_XMLNS
from commcare_connect.form_receiver.exceptions import ProcessingError

LEARN_MODULE_JSONPATH = parse("module where @xmlns")
ASSESSMENT_JSONPATH = parse("assessment where @xmlns")


def process_xform(domain: str, app_id: str, form: dict):
    processors = [
        (LEARN_MODULE_JSONPATH, process_learn_modules),
        (ASSESSMENT_JSONPATH, process_assessments),
    ]
    for jsonpath, processor in processors:
        try:
            matches = [match.value for match in jsonpath.find(form) if match.value["@xmlns"] == CCC_LEARN_XMLNS]
            if matches:
                processor(domain, app_id, matches)
        except JSONPathError as e:
            raise ProcessingError from e


def process_learn_modules(domain, app_id, modules):
    pass


def process_assessments(domain, app_id, assessments):
    pass
