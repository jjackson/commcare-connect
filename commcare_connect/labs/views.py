from django.http import HttpResponseRedirect
from django.views.decorators.http import require_http_methods

from commcare_connect.labs.context import clear_context_from_session


@require_http_methods(["POST"])
def clear_context(request):
    """Clear the labs context from session and redirect back."""
    clear_context_from_session(request)

    # Redirect to the referrer or home
    redirect_url = request.headers.get("referer", "/tasks/")

    # Remove any context params from the redirect URL
    from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

    parsed = urlparse(redirect_url)
    query_params = parse_qs(parsed.query)

    # Remove context parameters
    query_params.pop("organization_id", None)
    query_params.pop("program_id", None)
    query_params.pop("opportunity_id", None)
    query_params.pop("clear_context", None)

    # Rebuild URL
    new_query = urlencode(query_params, doseq=True)
    new_parsed = parsed._replace(query=new_query)
    redirect_url = urlunparse(new_parsed)

    return HttpResponseRedirect(redirect_url)
