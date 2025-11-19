"""
Labs OAuth Helper Functions

Shared OAuth utilities for both web and CLI authentication flows.
"""
import csv
import io
import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


def fetch_user_organization_data(access_token: str) -> dict | None:
    """
    Fetch user's organizations, programs, and opportunities from production.

    This function now properly fetches ALL opportunities the user has access to:
    1. Direct opportunities (owned by user's organizations)
    2. Managed opportunities (in programs managed by user's organizations)

    Args:
        access_token: OAuth Bearer token for Connect production

    Returns:
        Dict with 'organizations', 'programs', 'opportunities' keys, or None if fails.
    """
    try:
        # Get base data (orgs, programs, direct opportunities)
        response = httpx.get(
            f"{settings.CONNECT_PRODUCTION_URL}/export/opp_org_program_list/",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        # Now fetch managed opportunities for each program
        programs = data.get("programs", [])
        direct_opportunities = data.get("opportunities", [])

        # Track opportunity IDs we've already seen to avoid duplicates
        seen_opp_ids = {opp["id"] for opp in direct_opportunities}
        all_opportunities = list(direct_opportunities)

        logger.info(f"Fetching managed opportunities for {len(programs)} programs")

        for program in programs:
            program_id = program["id"]
            try:
                managed_opps = _fetch_program_opportunities(access_token, program_id)
                # Add only new opportunities we haven't seen
                for opp in managed_opps:
                    if opp["id"] not in seen_opp_ids:
                        all_opportunities.append(opp)
                        seen_opp_ids.add(opp["id"])
                logger.debug(f"Program {program_id} ({program['name']}): added {len(managed_opps)} opportunities")
            except Exception as e:
                logger.warning(f"Failed to fetch opportunities for program {program_id}: {e}")
                continue

        logger.info(
            f"Total opportunities: {len(all_opportunities)} "
            f"(direct: {len(direct_opportunities)}, managed: {len(all_opportunities) - len(direct_opportunities)})"
        )

        # Return complete dataset
        data["opportunities"] = all_opportunities
        return data

    except Exception as e:
        logger.error(f"Failed to fetch organization data: {str(e)}", exc_info=True)
        return None


def _fetch_program_opportunities(access_token: str, program_id: int) -> list[dict]:
    """
    Fetch all ManagedOpportunities for a specific program.

    Calls /export/program/<program_id>/opportunity/ which returns CSV format.
    Parses the CSV and returns list of opportunity dicts.

    Args:
        access_token: OAuth Bearer token
        program_id: ID of the program to fetch opportunities for

    Returns:
        List of opportunity dicts (may be empty if none found or error)
    """
    try:
        response = httpx.get(
            f"{settings.CONNECT_PRODUCTION_URL}/export/program/{program_id}/opportunity/",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        response.raise_for_status()

        # Parse CSV response
        csv_text = response.text
        csv_reader = csv.DictReader(io.StringIO(csv_text))

        opportunities = []
        for row in csv_reader:
            # Convert CSV row to opportunity dict matching OpportunityDataExportSerializer format
            # The CSV uses OpportunitySerializer (different fields)
            # Map to match the format from /export/opp_org_program_list/
            opp = {
                "id": int(row.get("id", 0)),
                "name": row.get("name", ""),
                "date_created": row.get("date_created"),
                "organization": row.get("organization"),  # slug
                "end_date": row.get("end_date"),
                "is_active": row.get("is_active", "").lower() == "true",
                "program": program_id,  # ManagedOpportunity belongs to this program
                "visit_count": 0,  # CSV doesn't include visit_count, will be 0
            }
            opportunities.append(opp)

        return opportunities

    except Exception as e:
        logger.error(f"Failed to fetch opportunities for program {program_id}: {str(e)}", exc_info=True)
        return []


def introspect_token(access_token: str, client_id: str, client_secret: str, production_url: str) -> dict | None:
    """
    Introspect OAuth token to get user profile information.

    Calls the OAuth introspection endpoint to validate token and retrieve
    user information including ID, username, and email.

    Args:
        access_token: OAuth Bearer token to introspect
        client_id: OAuth client ID
        client_secret: OAuth client secret (required for introspection)
        production_url: Base URL of production Connect instance

    Returns:
        Dict with user profile {'id', 'username', 'email', 'first_name', 'last_name'}
        or None if introspection fails or token is invalid.

    Example:
        >>> profile = introspect_token(
        ...     access_token="abc123",
        ...     client_id="my_client",
        ...     client_secret="secret",
        ...     production_url="https://connect.dimagi.com"
        ... )
        >>> if profile:
        ...     print(f"User: {profile['username']}")
    """
    try:
        introspect_response = httpx.post(
            f"{production_url}/o/introspect/",
            data={"token": access_token},
            auth=(client_id, client_secret),
            timeout=10,
        )

        if introspect_response.status_code != 200:
            logger.warning(f"Token introspection failed with status {introspect_response.status_code}")
            return None

        introspect_data = introspect_response.json()

        if not introspect_data.get("active"):
            logger.warning("Token is not active")
            return None

        # Extract user profile from introspection response
        # Note: introspection doesn't return user_id, only username
        # We use 0 as placeholder since we don't use ID for anything critical
        profile_data = {
            "id": introspect_data.get("user_id") or introspect_data.get("sub") or 0,
            "username": introspect_data.get("username"),
            "email": introspect_data.get("email", ""),
            "first_name": introspect_data.get("given_name", ""),
            "last_name": introspect_data.get("family_name", ""),
        }

        logger.debug(f"Token introspection successful for user: {profile_data.get('username')}")
        logger.debug(f"Introspection data fields: {list(introspect_data.keys())}")
        return profile_data

    except httpx.HTTPError as e:
        logger.error(f"HTTP error during token introspection: {str(e)}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Failed to introspect token: {str(e)}", exc_info=True)
        return None
