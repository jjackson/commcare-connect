from contextlib import ExitStack, contextmanager
from unittest import mock

from commcare_connect.form_receiver.processor import process_learn_form
from commcare_connect.form_receiver.tests.xforms import AssessmentStubFactory, LearnModuleJsonFactory, get_form_model
from commcare_connect.users.models import User

LEARN_PROCESSOR_PATCHES = [
    "commcare_connect.form_receiver.processor.process_learn_modules",
    "commcare_connect.form_receiver.processor.process_assessments",
]


def test_process_learn_form_no_matching_blocks(user: User):
    with mock.patch("commcare_connect.form_receiver.processor.process_learn_modules") as process_learn_modules:
        process_learn_form(user, get_form_model(), None, None)
    assert process_learn_modules.call_count == 0


def test_process_learn_module(user: User):
    learn_module = LearnModuleJsonFactory().json
    xform = get_form_model(form_block=learn_module)
    with patch_multiple(*LEARN_PROCESSOR_PATCHES) as [process_learn_module, process_assessment]:
        process_learn_form(user, xform, None, None)
    assert process_learn_module.call_count == 1
    assert process_assessment.call_count == 0


def test_process_assessment(user: User):
    assessment = AssessmentStubFactory().json
    xform = get_form_model(form_block=assessment)
    with patch_multiple(*LEARN_PROCESSOR_PATCHES) as [process_learn_module, process_assessment]:
        process_learn_form(user, xform, None, None)
    assert process_learn_module.call_count == 0
    assert process_assessment.call_count == 1


@contextmanager
def patch_multiple(*args):
    with ExitStack() as stack:
        patches = [stack.enter_context(mock.patch(arg)) for arg in args]
        yield patches
