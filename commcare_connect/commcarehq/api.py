import dataclasses
from typing import Any, TypedDict
from urllib.parse import urlencode

import httpx
from django.db import transaction

from commcare_connect.microplanning.models import WorkArea
from commcare_connect.microplanning.serializers import WorkAreaCaseSerializer
from commcare_connect.opportunity.models import HQApiKey, OpportunityAccess
from commcare_connect.users.models import ConnectIDUserLink
from commcare_connect.utils.commcarehq_api import CommCareHQAPIException


class GetCaseDataAPIFilters(TypedDict):
    case_type: str
    case_name: str


@dataclasses.dataclass
class CommCareCase:
    domain: str
    case_id: str
    case_type: str
    case_name: str
    external_id: str | None
    owner_id: str
    date_opened: str
    last_modified: str
    server_last_modified: str
    indexed_on: str
    closed: bool
    date_closed: str | None
    properties: dict[str, str]
    indices: dict[str, Any]


def get_case_list(api_key: HQApiKey, domain: str, filters: GetCaseDataAPIFilters) -> list[CommCareCase]:
    params = urlencode(filters)
    url = f"/a/{domain}/api/case/v2/?{params}"

    cases = []
    with httpx.Client(
        base_url=api_key.hq_server.url,
        headers={"Authorization": f"ApiKey {api_key.user.email}:{api_key.api_key}"},
    ) as client:
        while url is not None:
            response = client.get(url)

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise CommCareHQAPIException(f"Failed to fetch case data for {domain}. HQ Error: {e}") from e

            data = response.json()
            cases.extend(CommCareCase(**case_data) for case_data in data.get("cases", []))
            url = data.get("next")
    return cases


def create_or_update_case_by_work_area(work_area: WorkArea) -> CommCareCase:
    if not (work_area.work_area_group and work_area.work_area_group.assigned_user):
        raise ValueError("Work Area must have an assigned user through its Work Area Group")

    opp_access = work_area.work_area_group.assigned_user
    api_key = opp_access.opportunity.api_key
    domain = opp_access.opportunity.deliver_app.cc_domain
    case_data = WorkAreaCaseSerializer(work_area).data
    if not work_area.case_id:
        user_case = get_usercase(opp_access)
        case_data["owner_id"] = user_case.case_id

    with transaction.atomic():
        # Re-fetch with a row-level lock to prevent a race condition where two
        # concurrent calls both see case_id as None
        locked_work_area = WorkArea.objects.select_for_update().get(pk=work_area.pk)
        case = create_or_update_case(api_key, domain, case_data, case_id=locked_work_area.case_id)
        if locked_work_area.case_id is None:
            locked_work_area.case_id = case.case_id
            locked_work_area.save(update_fields=["case_id"])
    return case


def create_or_update_case(
    api_key: HQApiKey,
    domain: str,
    case_data: dict[str, Any],
    case_id: str | None = None,
) -> CommCareCase:
    base_url = f"{api_key.hq_server.url}/a/{domain}/api/case/v2/"
    headers = {"Authorization": f"ApiKey {api_key.user.email}:{api_key.api_key}"}

    with httpx.Client() as client:
        if case_id:
            response = client.put(f"{base_url}{case_id}/", headers=headers, json=case_data)
            error_msg = f"Failed to update case data for {domain} with {case_id}."
        else:
            response = client.post(base_url, headers=headers, json=case_data)
            error_msg = f"Failed to create case for {domain}."

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise CommCareHQAPIException(f"{error_msg} HQ Error: {e}") from e

    data = response.json()
    return CommCareCase(**data.get("case", {}))


def update_usercase(opportunity_access: OpportunityAccess, data: dict[str, Any]) -> CommCareCase:
    domain = opportunity_access.opportunity.deliver_app.cc_domain
    api_key = opportunity_access.opportunity.api_key
    hq_server = api_key.hq_server

    link = ConnectIDUserLink.objects.get(user=opportunity_access.user, domain=domain, hq_server=hq_server)
    if link.hq_case_id is None:
        usercase = get_usercase(opportunity_access)
        link.hq_case_id = usercase.case_id
        link.save()

    return create_or_update_case(api_key, domain, data, case_id=link.hq_case_id)


def get_usercase(opportunity_access: OpportunityAccess) -> CommCareCase:
    domain = opportunity_access.opportunity.deliver_app.cc_domain
    api_key = opportunity_access.opportunity.api_key
    user = opportunity_access.user
    case_data = get_case_list(
        api_key,
        domain,
        filters={
            "case_type": "commcare-user",
            "case_name": user.username.lower(),
        },
    )
    usercase = next(iter(case_data), None)
    if usercase is None:
        raise CommCareHQAPIException(f"Failed to find usercase for {user.username.lower()} on {domain} HQ domain.")
    return usercase
