from django.conf import settings

from commcare_connect.utils.tables import DEFAULT_PAGE_SIZE, PAGE_SIZE_OPTIONS


def page_settings(request):
    """Expose global page size settings to templates."""
    return {"PAGE_SIZE_OPTIONS": PAGE_SIZE_OPTIONS, "DEFAULT_PAGE_SIZE": DEFAULT_PAGE_SIZE}


def gtm_context(request):
    """Provide Google Tag Manager context variables to templates."""
    return {
        "GTM_VARS_JSON": {
            "isDimagi": request.user.is_authenticated and request.user.email.endswith("@dimagi.com"),
            "gtmID": settings.GTM_ID,
        }
    }
