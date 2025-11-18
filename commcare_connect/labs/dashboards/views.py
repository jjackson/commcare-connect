"""
Labs Dashboard Prototype Views

Multiple visualization approaches for hierarchical program data:
- Program Type → Program → Opportunity → FLWs
"""
import csv
import io
import json
import logging

import httpx
from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render

logger = logging.getLogger(__name__)


def dashboard_2(request: HttpRequest) -> HttpResponse:
    """Dashboard prototype 2: Accordion/Collapsible Cards View."""
    if not request.user.is_authenticated:
        return redirect("labs:login")

    # Get programs and opportunities
    programs = request.user.programs if hasattr(request.user, "programs") else []
    opportunities = request.user.opportunities if hasattr(request.user, "opportunities") else []

    # Log for debugging
    logger.info(f"Dashboard 2 - Programs: {len(programs)}, Opportunities: {len(opportunities)}")
    if programs:
        logger.debug(f"First program: {programs[0]}")
    if opportunities:
        logger.debug(f"First opportunity: {opportunities[0]}")

    context = {
        "user": request.user,
        "connect_url": settings.CONNECT_PRODUCTION_URL,
        "programs_json": json.dumps(programs),
        "opportunities_json": json.dumps(opportunities),
    }

    return render(request, "labs/dashboard-2.html", context)


def dashboard_3(request: HttpRequest) -> HttpResponse:
    """Dashboard prototype 3: Interactive Tree/Sidebar Navigation."""
    if not request.user.is_authenticated:
        return redirect("labs:login")

    context = {
        "user": request.user,
        "connect_url": settings.CONNECT_PRODUCTION_URL,
        "programs_json": json.dumps(request.user.programs),
        "opportunities_json": json.dumps(request.user.opportunities),
    }

    return render(request, "labs/dashboard-3.html", context)


def dashboard_4(request: HttpRequest) -> HttpResponse:
    """Dashboard prototype 4: Drill-Down Table with Breadcrumbs."""
    if not request.user.is_authenticated:
        return redirect("labs:login")

    context = {
        "user": request.user,
        "connect_url": settings.CONNECT_PRODUCTION_URL,
        "programs_json": json.dumps(request.user.programs),
        "opportunities_json": json.dumps(request.user.opportunities),
    }

    return render(request, "labs/dashboard-4.html", context)


def fetch_flws(request: HttpRequest, opp_id: int) -> JsonResponse:
    """
    Fetch FLW (Field Worker) data for a specific opportunity.

    This is a server-side proxy endpoint that:
    1. Uses the OAuth token from session (not exposed to client)
    2. Calls production API to get FLW data
    3. Returns JSON to client

    Args:
        request: HTTP request with authenticated session
        opp_id: Opportunity ID to fetch FLW data for

    Returns:
        JsonResponse with FLW list or error
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    # Get OAuth token from session
    labs_oauth = request.session.get("labs_oauth")
    if not labs_oauth or "access_token" not in labs_oauth:
        return JsonResponse({"error": "No OAuth token in session"}, status=401)

    access_token = labs_oauth["access_token"]

    # Call production API
    try:
        url = f"{settings.CONNECT_PRODUCTION_URL}/export/opportunity/{opp_id}/user_data/"
        response = httpx.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
        response.raise_for_status()

        # Log response details for debugging
        content_type = response.headers.get("content-type", "")
        logger.info(
            f"Response from production API: status={response.status_code}, "
            f"content-type={content_type}, length={len(response.content)}"
        )

        # Parse CSV response (production API returns CSV, not JSON)
        if "text/csv" in content_type or "application/csv" in content_type:
            # Parse CSV and convert to list of dicts
            csv_text = response.text
            csv_reader = csv.DictReader(io.StringIO(csv_text))
            flw_data = list(csv_reader)
            logger.info(f"Fetched {len(flw_data)} FLWs for opportunity {opp_id}")
            return JsonResponse({"flws": flw_data, "opportunity_id": opp_id})
        elif "application/json" in content_type:
            # Fallback for JSON (in case API changes)
            flw_data = response.json()
            logger.info(f"Fetched {len(flw_data)} FLWs for opportunity {opp_id}")
            return JsonResponse({"flws": flw_data, "opportunity_id": opp_id})
        else:
            # Unexpected format
            logger.error(f"Unexpected content type from production API: {content_type}")
            logger.debug(f"Response body preview: {response.text[:200]}")
            return JsonResponse(
                {"error": f"Production API returned {content_type}, expected CSV or JSON"},
                status=500,
            )

    except httpx.HTTPStatusError as e:
        logger.error(f"Failed to fetch FLW data for opp {opp_id}: HTTP {e.response.status_code}", exc_info=True)
        return JsonResponse(
            {"error": f"Failed to fetch FLW data: HTTP {e.response.status_code}"},
            status=e.response.status_code,
        )
    except httpx.TimeoutException:
        logger.error(f"Timeout fetching FLW data for opp {opp_id}")
        return JsonResponse({"error": "Request timeout - production API took too long"}, status=504)
    except Exception as e:
        logger.error(f"Unexpected error fetching FLW data for opp {opp_id}: {str(e)}", exc_info=True)
        return JsonResponse({"error": f"Unexpected error: {str(e)}"}, status=500)
