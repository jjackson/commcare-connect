from django.contrib import messages
from django.http import HttpResponseRedirect
from django.views.decorators.http import require_http_methods

from commcare_connect.labs.context import clear_context_from_session
from commcare_connect.labs.integrations.connect.oauth import fetch_user_organization_data


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


@require_http_methods(["POST"])
def refresh_org_data(request):
    """Refresh organization data from Connect API."""
    if not request.user.is_authenticated:
        messages.error(request, "You must be logged in to refresh organization data.")
        return HttpResponseRedirect(request.headers.get("referer", "/"))

    # Get OAuth token from session
    labs_oauth = request.session.get("labs_oauth")
    if not labs_oauth or "access_token" not in labs_oauth:
        messages.error(request, "No OAuth token found. Please log in again.")
        return HttpResponseRedirect("/labs/login/")

    access_token = labs_oauth["access_token"]

    # Fetch fresh organization data
    org_data = fetch_user_organization_data(access_token)

    if org_data:
        # Update session with fresh data
        labs_oauth["organization_data"] = org_data
        request.session["labs_oauth"] = labs_oauth
        request.session.modified = True

        messages.success(
            request,
            f"Successfully refreshed organization data: "
            f"{len(org_data.get('organizations', []))} orgs, "
            f"{len(org_data.get('programs', []))} programs, "
            f"{len(org_data.get('opportunities', []))} opportunities.",
        )
    else:
        messages.error(
            request,
            "Failed to refresh organization data. The Connect API may be slow or unavailable. "
            "Please try again in a moment.",
        )

    # Redirect back to referrer
    return HttpResponseRedirect(request.headers.get("referer", "/"))
