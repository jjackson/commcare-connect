"""
OAuth CLI Client for CommCare Connect.

Implements the OAuth Authorization Code flow with PKCE for CLI tools.
This allows scripts to authenticate users via browser and obtain access tokens.

Usage:
    from commcare_connect.labs.oauth_cli import get_oauth_token

    token = get_oauth_token(
        client_id="your_client_id",
        production_url="https://production.com"
    )
"""

import base64
import hashlib
import secrets
import socket
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import httpx


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler that captures OAuth callback with authorization code."""

    received_code = None
    received_error = None

    def do_GET(self):
        """Handle GET request from OAuth provider redirect."""
        query = parse_qs(urlparse(self.path).query)

        # Capture authorization code or error
        OAuthCallbackHandler.received_code = query.get("code", [None])[0]
        OAuthCallbackHandler.received_error = query.get("error", [None])[0]

        # Send response to browser
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

        if OAuthCallbackHandler.received_code:
            html = """
                <html><body style="font-family: sans-serif; text-align: center; padding: 50px;">
                    <h1 style="color: #28a745;">[SUCCESS] Authorization Successful!</h1>
                    <p>You can close this window and return to your terminal.</p>
                    <script>setTimeout(() => window.close(), 2000);</script>
                </body></html>
            """
        else:
            error_msg = OAuthCallbackHandler.received_error or "Unknown error"
            html = f"""
                <html><body style="font-family: sans-serif; text-align: center; padding: 50px;">
                    <h1 style="color: #dc3545;">[ERROR] Authorization Failed</h1>
                    <p>Error: {error_msg}</p>
                    <p>Please check the terminal for details.</p>
                </body></html>
            """

        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        """Suppress HTTP server logs."""
        pass


def is_port_available(port):
    """Check if a port is available for binding."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("localhost", port))
            return True
    except OSError:
        return False


def generate_pkce_pair():
    """Generate PKCE code verifier and challenge for secure OAuth flow."""
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("utf-8").rstrip("=")
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("utf-8")).digest()).decode("utf-8").rstrip("=")
    )
    return code_verifier, code_challenge


def get_oauth_token(
    client_id: str,
    production_url: str,
    client_secret: str | None = None,
    port: int = 8765,
    scope: str = "export",
    verbose: bool = True,
) -> dict | None:
    """
    Obtain an OAuth access token via browser-based authorization.

    This implements the OAuth Authorization Code flow with PKCE. It:
    1. Starts a local HTTP server to receive the callback
    2. Opens the user's browser to the authorization page
    3. Waits for the user to authorize
    4. Exchanges the authorization code for an access token

    Args:
        client_id: OAuth client ID
        production_url: Base URL of the production CommCare Connect instance
        client_secret: OAuth client secret (optional, not needed for public clients with PKCE)
        port: Local port for OAuth callback (default: 8765)
        scope: OAuth scopes to request (default: "read write")
        verbose: Print status messages (default: True)

    Returns:
        Dict with token data including 'access_token', 'token_type', 'expires_in', etc.
        Returns None if authorization fails.

    Example:
        >>> token_data = get_oauth_token(
        ...     client_id="abc123",
        ...     production_url="https://connect.dimagi.com"
        ... )
        >>> access_token = token_data['access_token']
    """
    redirect_uri = f"http://localhost:{port}/callback"

    # Check if port is available
    if not is_port_available(port):
        if verbose:
            print(f"Error: Port {port} is already in use.")
            print("Please close the application using it or choose a different port.")
        return None

    # Generate PKCE values for security
    code_verifier, code_challenge = generate_pkce_pair()

    # Build authorization URL
    auth_params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{production_url}/o/authorize/?{urlencode(auth_params)}"

    if verbose:
        print("\n" + "=" * 70)
        print("OAuth Authorization Flow")
        print("=" * 70)
        print(f"\nOpening browser to: {production_url}")
        print("\nPlease authorize the application in your browser.")
        print("Waiting for authorization...")

    # Open browser for user authorization
    webbrowser.open(auth_url)

    # Start local server and wait for callback
    server = HTTPServer(("localhost", port), OAuthCallbackHandler)
    server.handle_request()

    # Check if we received an authorization code
    if OAuthCallbackHandler.received_error:
        if verbose:
            print(f"\n[ERROR] Authorization failed: {OAuthCallbackHandler.received_error}")
        return None

    if not OAuthCallbackHandler.received_code:
        if verbose:
            print("\n[ERROR] No authorization code received")
        return None

    if verbose:
        print("\n[OK] Authorization code received")
        print("Exchanging code for access token...")

    # Exchange authorization code for access token
    token_data = {
        "grant_type": "authorization_code",
        "code": OAuthCallbackHandler.received_code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": code_verifier,
    }

    # Include client secret if provided (for confidential clients)
    if client_secret:
        token_data["client_secret"] = client_secret

    try:
        response = httpx.post(
            f"{production_url}/o/token/",
            data=token_data,
            timeout=10,
        )
        response.raise_for_status()
        token_response = response.json()

        if verbose:
            print("\n[OK] Successfully obtained OAuth token!")
            print("=" * 70)
            print(f"\nAccess Token: {token_response['access_token'][:20]}...")
            print(f"Token Type: {token_response.get('token_type', 'Bearer')}")
            print(f"Expires In: {token_response.get('expires_in', 'Unknown')} seconds")
            if token_response.get("refresh_token"):
                print("Refresh Token: Available")
            print()

        return token_response

    except httpx.HTTPStatusError as e:
        if verbose:
            print(f"\n[ERROR] Token exchange failed: {e.response.status_code}")
            print(f"Response: {e.response.text}")
        return None
    except Exception as e:
        if verbose:
            print(f"\n[ERROR] Error exchanging token: {str(e)}")
        return None


def get_labs_user_from_token(
    token_manager=None,
    client_id: str | None = None,
    client_secret: str | None = None,
    production_url: str | None = None,
):
    """
    Create LabsUser instance by introspecting saved CLI token at runtime.

    This is the recommended way for CLI scripts to get a LabsUser object.
    It loads the token saved by `python manage.py get_cli_token` and
    introspects it to get fresh user profile data.

    Args:
        token_manager: Optional TokenManager instance (defaults to new TokenManager())
        client_id: OAuth client ID for introspection (defaults to settings.CONNECT_OAUTH_CLIENT_ID)
        client_secret: OAuth client secret for introspection (defaults to settings.CONNECT_OAUTH_CLIENT_SECRET)
        production_url: Production URL (defaults to settings.CONNECT_PRODUCTION_URL)

    Returns:
        LabsUser instance or None if token invalid/expired or introspection fails

    Example:
        >>> from commcare_connect.labs.oauth_cli import get_labs_user_from_token
        >>> user = get_labs_user_from_token()
        >>> if user:
        >>>     print(f"Authenticated as: {user.username}")
    """
    from django.conf import settings

    from commcare_connect.labs.models import LabsUser
    from commcare_connect.labs.oauth_cli.token_manager import TokenManager
    from commcare_connect.labs.oauth_helpers import introspect_token

    # Load token
    if token_manager is None:
        token_manager = TokenManager()

    access_token = token_manager.get_valid_token()
    if not access_token:
        return None

    # Get OAuth credentials from settings if not provided
    # Note: We use the WEB OAuth credentials for introspection (confidential client)
    # because the CLI app is public and cannot introspect tokens
    if client_id is None:
        client_id = getattr(settings, "CONNECT_OAUTH_CLIENT_ID", None)
    if client_secret is None:
        client_secret = getattr(settings, "CONNECT_OAUTH_CLIENT_SECRET", None)
    if production_url is None:
        production_url = getattr(settings, "CONNECT_PRODUCTION_URL", None)

    if not client_id or not client_secret or not production_url:
        return None

    # Introspect token at runtime to get fresh user profile
    user_profile = introspect_token(
        access_token=access_token,
        client_id=client_id,
        client_secret=client_secret,
        production_url=production_url,
    )

    if not user_profile:
        return None

    # Create LabsUser from profile data
    session_data = {
        "user_profile": user_profile,
        "organization_data": {},
    }
    return LabsUser(session_data)
