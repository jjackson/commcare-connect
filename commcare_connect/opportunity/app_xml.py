import itertools
import re
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass

import httpx
from django.conf import settings

XMLNS = "http://commcareconnect.com/data/v1/learn"
XMLNS_PREFIX = "{%s}" % XMLNS


@dataclass
class Module:
    id: str
    name: str
    description: str
    time_estimate: int


@dataclass
class Assessment:
    id: str


def get_connect_blocks_for_app(domain: str, app_id: str) -> list[str]:
    form_xmls = get_form_xml_for_app(domain, app_id)
    return list(itertools.chain.from_iterable(extract_connect_blocks(form_xml) for form_xml in form_xmls))


def get_form_xml_for_app(domain: str, app_id: str) -> list[str]:
    """Download the CCZ for the given app and return the XML for each form."""
    ccz_url = f"{settings.COMMCARE_HQ_URL}/a/{domain}/apps/api/download_ccz/"
    params = {
        "app_id": app_id,
        "latest": "release",
    }
    response = httpx.get(ccz_url, params=params)
    response.raise_for_status()

    form_xml = []
    with tempfile.NamedTemporaryFile() as file:
        file.write(response.content)
        file.seek(0)

        form_re = re.compile(r"modules-\d+/forms-\d+\.xml")
        with zipfile.ZipFile(file, "r") as zip_ref:
            for file in zip_ref.namelist():
                if form_re.match(file):
                    with zip_ref.open(file) as xml_file:
                        form_xml.append(xml_file.read().decode())
    return form_xml


def extract_connect_blocks(form_xml):
    xml = ET.fromstring(form_xml)
    yield from extract_modules(xml)
    yield from extract_assessments(xml)


def extract_assessments(xml: ET.ElementTree) -> list[str]:
    for block in xml.findall(f".//{XMLNS_PREFIX}assessment"):
        yield Assessment(block.get("id"))


def extract_modules(xml: ET.ElementTree):
    for block in xml.findall(f".//{XMLNS_PREFIX}module"):
        slug = block.get("id")
        name = get_element_text(block, "name")
        description = get_element_text(block, "description")
        time_estimate = get_element_text(block, "time_estimate")
        yield Module(slug, name, description, int(time_estimate) if time_estimate is not None else None)


def get_element_text(parent, name) -> str | None:
    element = parent.find(f"{XMLNS_PREFIX}{name}")
    return element.text if element is not None else None
