"""
Token Manager for OAuth CLI tokens.

Handles secure storage, loading, and validation of OAuth tokens for CLI usage.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path


class TokenManager:
    """
    Manages OAuth token storage and retrieval for CLI tools.

    Tokens are stored in JSON format with expiration tracking.
    """

    def __init__(self, token_file: str = None):
        """
        Initialize token manager.

        Args:
            token_file: Path to token file. Defaults to ~/.commcare-connect/token.json
        """
        if token_file:
            self.token_file = Path(token_file)
        else:
            # Default: Store in user's home directory
            config_dir = Path.home() / ".commcare-connect"
            config_dir.mkdir(exist_ok=True)
            self.token_file = config_dir / "token.json"

    def save_token(self, token_data: dict) -> bool:
        """
        Save OAuth token to file with expiration timestamp.

        Args:
            token_data: Token response from OAuth provider

        Returns:
            True if successful, False otherwise
        """
        try:
            # Calculate expiration time if expires_in is provided
            if "expires_in" in token_data:
                expires_at = (datetime.now() + timedelta(seconds=token_data["expires_in"])).isoformat()
                token_data["expires_at"] = expires_at

            # Add saved timestamp
            token_data["saved_at"] = datetime.now().isoformat()

            # Ensure parent directory exists
            self.token_file.parent.mkdir(parents=True, exist_ok=True)

            # Write token to file
            with open(self.token_file, "w") as f:
                json.dump(token_data, f, indent=2)

            # Set restrictive permissions (owner read/write only)
            os.chmod(self.token_file, 0o600)

            return True
        except Exception as e:
            print(f"Failed to save token: {e}")
            return False

    def load_token(self) -> dict | None:
        """
        Load OAuth token from file.

        Returns:
            Token data dict or None if file doesn't exist or is invalid
        """
        try:
            if not self.token_file.exists():
                return None

            with open(self.token_file) as f:
                return json.load(f)
        except Exception:
            return None

    def get_valid_token(self) -> str | None:
        """
        Get a valid access token, checking expiration.

        Returns:
            Access token string if valid, None if expired or not found
        """
        token_data = self.load_token()

        if not token_data:
            return None

        # Check if token has expired
        if "expires_at" in token_data:
            expires_at = datetime.fromisoformat(token_data["expires_at"])
            # Add 5 minute buffer before expiration
            if datetime.now() >= (expires_at - timedelta(minutes=5)):
                return None

        return token_data.get("access_token")

    def is_expired(self) -> bool:
        """
        Check if the stored token is expired.

        Returns:
            True if expired or no token, False if still valid
        """
        return self.get_valid_token() is None

    def clear_token(self) -> bool:
        """
        Delete the stored token file.

        Returns:
            True if successful, False otherwise
        """
        try:
            if self.token_file.exists():
                self.token_file.unlink()
            return True
        except Exception:
            return False

    def get_token_info(self) -> dict | None:
        """
        Get information about the stored token without returning the token itself.

        Returns:
            Dict with token metadata or None if no token
        """
        token_data = self.load_token()

        if not token_data:
            return None

        info = {
            "saved_at": token_data.get("saved_at"),
            "expires_at": token_data.get("expires_at"),
            "token_type": token_data.get("token_type", "Bearer"),
            "has_refresh_token": "refresh_token" in token_data,
            "is_valid": self.get_valid_token() is not None,
        }

        # Calculate time remaining
        if "expires_at" in token_data:
            expires_at = datetime.fromisoformat(token_data["expires_at"])
            now = datetime.now()
            if now < expires_at:
                time_remaining = expires_at - now
                info["expires_in_seconds"] = int(time_remaining.total_seconds())
            else:
                info["expires_in_seconds"] = 0

        return info


def get_or_refresh_token(
    client_id: str,
    production_url: str,
    token_file: str = None,
    verbose: bool = True,
) -> str | None:
    """
    Get a valid token, fetching a new one if needed.

    This is a convenience function that:
    1. Checks for existing valid token
    2. Returns it if valid
    3. Fetches new token via OAuth flow if expired/missing

    Args:
        client_id: OAuth client ID
        production_url: Production URL
        token_file: Optional custom token file path
        verbose: Print status messages

    Returns:
        Valid access token or None if failed
    """
    from commcare_connect.labs.oauth_cli.client import get_oauth_token

    manager = TokenManager(token_file)

    # Try to get existing valid token
    token = manager.get_valid_token()

    if token:
        if verbose:
            info = manager.get_token_info()
            if info and "expires_in_seconds" in info:
                minutes = info["expires_in_seconds"] // 60
                print(f"Using cached token (expires in {minutes} minutes)")
        return token

    # Need new token
    if verbose:
        print("No valid token found. Starting OAuth flow...")

    token_data = get_oauth_token(
        client_id=client_id,
        production_url=production_url,
        verbose=verbose,
    )

    if not token_data:
        return None

    # Save for future use
    manager.save_token(token_data)

    if verbose:
        print(f"Token saved to: {manager.token_file}")

    return token_data.get("access_token")
