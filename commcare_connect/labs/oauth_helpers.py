"""
Labs OAuth Helper Functions

Shared OAuth utilities for both web and CLI authentication flows.
"""
import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


def fetch_user_organization_data(access_token: str) -> dict | None:
    """
    Fetch user's organizations, programs, and opportunities from production.

    Uses the /export/opp_org_program_list/ API endpoint.

    Args:
        access_token: OAuth Bearer token for Connect production

    Returns:
        Dict with 'organizations', 'programs', 'opportunities' keys, or None if fails.
    """
    try:
        response = httpx.get(
            f"{settings.CONNECT_PRODUCTION_URL}/export/opp_org_program_list/",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Failed to fetch organization data: {str(e)}", exc_info=True)
        return None


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
