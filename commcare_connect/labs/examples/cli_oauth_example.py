#!/usr/bin/env python
"""
Example script demonstrating OAuth CLI authentication.

This shows how to use the labs OAuth CLI library to authenticate
and make API calls to production CommCare Connect.

Usage:
    python cli_oauth_example.py
"""

import os
import sys

import httpx

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from commcare_connect.labs.oauth_cli import get_oauth_token, load_token_from_file, save_token_to_file  # noqa: E402


def main():
    """Demonstrate OAuth CLI flow and API usage."""
    # Configuration
    CLIENT_ID = os.getenv("CLI_OAUTH_CLIENT_ID", "w0nBrVuHhxFzJdpK6sKlauPLGr")
    PRODUCTION_URL = os.getenv("CONNECT_PRODUCTION_URL", "https://connect.dimagi.com")
    TOKEN_FILE = ".oauth_token"

    print("=" * 70)
    print("CommCare Connect CLI OAuth Example")
    print("=" * 70)

    # Try to load existing token
    token_data = load_token_from_file(TOKEN_FILE)

    if token_data:
        print(f"\n✓ Loaded existing token from {TOKEN_FILE}")
        access_token = token_data["access_token"]
    else:
        print("\nNo existing token found. Starting OAuth flow...")

        # Get new token via browser authentication
        token_data = get_oauth_token(
            client_id=CLIENT_ID,
            production_url=PRODUCTION_URL,
            port=8765,
            scope="read write",
        )

        if not token_data:
            print("\n✗ Failed to obtain token")
            return

        access_token = token_data["access_token"]

        # Save token for future use
        if save_token_to_file(token_data, TOKEN_FILE):
            print(f"\n✓ Token saved to {TOKEN_FILE}")

    # Example API call: Fetch user's organizations
    print("\n" + "=" * 70)
    print("Making API Call: Fetching Organizations")
    print("=" * 70)

    try:
        response = httpx.get(
            f"{PRODUCTION_URL}/export/opp_org_program_list/",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        print("\n✓ Successfully fetched data!")
        print(f"\nOrganizations: {len(data.get('organizations', []))}")
        print(f"Programs: {len(data.get('programs', []))}")
        print(f"Opportunities: {len(data.get('opportunities', []))}")

        # Print first organization as example
        if data.get("organizations"):
            org = data["organizations"][0]
            print("\nExample Organization:")
            print(f"  Name: {org.get('name')}")
            print(f"  Slug: {org.get('slug')}")
            print(f"  ID: {org.get('id')}")

    except httpx.HTTPStatusError as e:
        print(f"\n✗ API call failed: {e.response.status_code}")
        if e.response.status_code == 401:
            print("Token may be expired. Delete .oauth_token and try again.")
        print(f"Response: {e.response.text}")
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")

    print("\n" + "=" * 70)
    print("Done!")
    print("=" * 70)


if __name__ == "__main__":
    main()
