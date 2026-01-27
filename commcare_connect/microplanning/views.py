from django.conf import settings
from django.shortcuts import render
from django.views.decorators.http import require_GET


@require_GET
def microplanning_home(request, *args, **kwargs):
    return render(
        request,
        template_name="microplanning/home.html",
        context={
            "mapbox_api_key": settings.MAPBOX_API_KEY,
        },
    )
