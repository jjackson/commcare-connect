from functools import wraps

from django.http import HttpResponseForbidden


def block_when_automatic_verification(view_func):
    """
    Reject requests for opportunities with automatic_visit_verification=True.

    Must be applied after @opportunity_required so request.opportunity is set.
    Returns 403 with an HX-Trigger: reload_table header so HTMX clients refresh
    after a guard hit instead of showing a stale UI.
    """

    @wraps(view_func)
    def _inner(request, *args, **kwargs):
        if getattr(request, "opportunity", None) and request.opportunity.automatic_visit_verification:
            response = HttpResponseForbidden()
            response["HX-Trigger"] = "reload_table"
            return response
        return view_func(request, *args, **kwargs)

    return _inner
