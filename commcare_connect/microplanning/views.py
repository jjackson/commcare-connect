from django.conf import settings
from django.shortcuts import render
from django.views.decorators.http import require_GET

from commcare_connect.flags.decorators import require_flag_for_org
from commcare_connect.flags.flag_names import MICROPLANNING
from commcare_connect.organization.decorators import org_admin_required


@require_GET
@org_admin_required
@require_flag_for_org(MICROPLANNING)
def microplanning_home(request, *args, **kwargs):
    return render(
        request,
        template_name="microplanning/home.html",
        context={
            "mapbox_api_key": settings.MAPBOX_TOKEN,
        },
    )
