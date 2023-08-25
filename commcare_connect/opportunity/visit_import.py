import codecs
import mimetypes
import textwrap
from dataclasses import dataclass

from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from tablib import Dataset

from commcare_connect.opportunity.models import Opportunity, UserVisit, VisitValidationStatus
from commcare_connect.utils.itertools import batched

VISIT_ID_COL = "visit id"
STATUS_COL = "status"
REQUIRED_COLS = [VISIT_ID_COL, STATUS_COL]


class ImportException(Exception):
    def __init__(self, message, rows=None):
        self.message = message
        self.rows = rows


@dataclass
class ImportStatus:
    seen_visits: set[str]
    missing_visits: set[str]

    def __len__(self):
        return len(self.seen_visits)

    def get_missing_message(self):
        joined = ", ".join(self.missing_visits)
        missing = textwrap.wrap(joined, width=115, break_long_words=False, break_on_hyphens=False)
        return f"<br>{len(self.missing_visits)} visits were not found:<br>{'<br>'.join(missing)}"


def bulk_update_visit_status(opportunity: Opportunity, file: UploadedFile) -> ImportStatus:
    if file.content_type:
        file_format = mimetypes.guess_extension(file.content_type)
        if file_format:
            file_format = file_format[1:]
    else:
        file_format = file.name.split(".")[-1].lower()
    if file_format not in ("csv", "xlsx"):
        raise ImportException("Invalid file format. Only 'CSV' and 'XLSX' are supported.")
    imported_data = get_imported_dataset(file, file_format)
    return _bulk_update_visit_status(opportunity, imported_data)


def _bulk_update_visit_status(opportunity: Opportunity, dataset: Dataset):
    status_by_visit_id = get_status_by_visit_id(dataset)
    visit_ids = list(status_by_visit_id)
    missing_visits = set()
    seen_visits = set()
    with transaction.atomic():
        for visit_batch in batched(visit_ids, 100):
            to_update = []
            for visit in UserVisit.objects.filter(xform_id__in=visit_batch, opportunity=opportunity):
                seen_visits.add(visit.xform_id)
                status = status_by_visit_id[visit.xform_id]
                if visit.status != status:
                    visit.status = status
                    to_update.append(visit)

            UserVisit.objects.bulk_update(to_update, fields=["status"])
            missing_visits |= set(visit_batch) - seen_visits

    return ImportStatus(seen_visits, missing_visits)


def get_status_by_visit_id(dataset) -> dict[int, VisitValidationStatus]:
    headers = [header.lower() for header in dataset.headers or []]
    if not headers:
        raise ImportException("The uploaded file did not contain any headers")

    visit_col_index = _get_header_index(headers, VISIT_ID_COL)
    status_col_index = _get_header_index(headers, STATUS_COL)
    status_by_visit_id = {}
    invalid_rows = []
    for row in dataset:
        row = list(row)
        visit_id = str(row[visit_col_index])
        status_raw = row[status_col_index].lower()
        try:
            status_by_visit_id[visit_id] = VisitValidationStatus[status_raw]
        except KeyError:
            invalid_rows.append((row, f"status must be one of {VisitValidationStatus.values}"))

    if invalid_rows:
        raise ImportException(f"{len(invalid_rows)} have errors", invalid_rows)
    return status_by_visit_id


def get_imported_dataset(file, file_format):
    if file_format == "csv":
        file = codecs.iterdecode(file, "utf-8")
    imported_data = Dataset().load(file, format=file_format)
    return imported_data


def _get_header_index(headers: list[str], col_name: str) -> int:
    try:
        return headers.index(col_name)
    except ValueError:
        raise ImportException(f"Missing required column(s): '{col_name}'")
