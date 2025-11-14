"""
OAuth CLI Package for CommCare Connect.

Provides CLI-friendly OAuth authentication following the Authorization Code + PKCE flow.
Tokens are stored in the user's home directory (~/.commcare-connect/token.json).

Quick Start:
    # Get a token via browser authentication
    from commcare_connect.labs.oauth_cli import get_oauth_token

    token_data = get_oauth_token(
        client_id="your_client_id",
        production_url="https://connect.dimagi.com"
    )
    access_token = token_data['access_token']

    # Or use the token manager for automatic caching
    from commcare_connect.labs.oauth_cli import get_or_refresh_token

    access_token = get_or_refresh_token(
        client_id="your_client_id",
        production_url="https://connect.dimagi.com"
    )
"""

from .client import get_labs_user_from_token, get_oauth_token
from .token_manager import TokenManager, get_or_refresh_token

__all__ = [
    "get_oauth_token",
    "get_labs_user_from_token",
    "TokenManager",
    "get_or_refresh_token",
]
