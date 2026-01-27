import waffle
from django.conf import settings
from django.shortcuts import render
from django.views.decorators.http import require_GET

from commcare_connect.flags.switch_names import MICROPLANNING
from commcare_connect.organization.decorators import org_viewer_required


@require_GET
@org_viewer_required
def microplanning_home(request, *args, **kwargs):
    if not waffle.switch_is_active(MICROPLANNING):
        return render(request, "404.html", status=404)

    return render(
        request,
        template_name="microplanning/home.html",
        context={
            "mapbox_api_key": settings.MAPBOX_API_KEY,
        },
    )
