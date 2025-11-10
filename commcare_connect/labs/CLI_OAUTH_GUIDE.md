# CLI OAuth Guide

This guide explains how to use the OAuth CLI library to authenticate CLI tools and scripts with CommCare Connect production.

## Overview

The OAuth CLI library implements the OAuth Authorization Code flow with PKCE, allowing command-line tools to obtain access tokens via browser-based authorization. This is the same pattern used by AWS CLI, GitHub CLI, and other modern CLI tools.

## Setup

### 1. Register OAuth Application

Register a **Public** OAuth application at your production CommCare Connect instance:

1. Go to your production admin panel
2. Navigate to OAuth Applications
3. Create new application with:
   - **Name**: "CLI Tools" (or similar)
   - **Client type**: Public
   - **Authorization grant type**: Authorization code
   - **Redirect URIs**: `http://localhost:8765/callback`
   - **Algorithm**: No OIDC support

### 2. Configure Environment

Add to your `.env` file:

```bash
CLI_OAUTH_CLIENT_ID="your_client_id_here"
CONNECT_PRODUCTION_URL="https://your-production-url.com"
```

Note: `CLI_OAUTH_CLIENT_SECRET` is not needed for public clients.

## Usage

### Method 1: Django Management Command

The simplest way to get a token:

```bash
# Basic usage
python manage.py get_cli_token

# Save token to file
python manage.py get_cli_token --save-to .oauth_token

# Get just the token (for piping)
python manage.py get_cli_token --quiet

# Use in shell script
export OAUTH_TOKEN=$(python manage.py get_cli_token --quiet)
```

### Method 2: Python Library

Use in your own scripts:

```python
from commcare_connect.labs.oauth_cli import get_oauth_token

# Get token
token_data = get_oauth_token(
    client_id="your_client_id",
    production_url="https://connect.dimagi.com",
    port=8765,  # Optional, defaults to 8765
    scope="read write",  # Optional
)

if token_data:
    access_token = token_data['access_token']
    # Use token for API calls...
```

### Method 3: Example Script

Run the included example:

```bash
cd commcare_connect/labs/examples
python cli_oauth_example.py
```

## How It Works

1. **Local Server**: Script starts a temporary HTTP server on `localhost:8765`
2. **Browser Opens**: Your default browser opens to the production OAuth authorization page
3. **User Authorizes**: You click "Authorize" on the webpage
4. **Callback**: Production redirects to `localhost:8765/callback` with authorization code
5. **Token Exchange**: Script exchanges the code for an access token
6. **Done**: Token is returned and optionally saved to file

## Token Management

### Saving Tokens

```python
from commcare_connect.labs.oauth_cli import save_token_to_file

save_token_to_file(token_data, ".oauth_token")
```

### Loading Tokens

```python
from commcare_connect.labs.oauth_cli import load_token_from_file

token_data = load_token_from_file(".oauth_token")
if token_data:
    access_token = token_data['access_token']
```

### Token Expiration

Tokens typically expire after a certain time (e.g., 1 hour). When expired:

- Delete the saved token file
- Run the OAuth flow again to get a fresh token

If your application has a refresh token, you can use it to get new access tokens without re-authorizing.

## Using Tokens with APIs

### With httpx

```python
import httpx

response = httpx.get(
    "https://production.com/api/endpoint/",
    headers={"Authorization": f"Bearer {access_token}"},
)
```

### With requests

```python
import requests

response = requests.get(
    "https://production.com/api/endpoint/",
    headers={"Authorization": f"Bearer {access_token}"},
)
```

## Security Notes

- **Public Client**: CLI tools use "Public" OAuth clients because they can't securely store secrets
- **PKCE**: The library uses PKCE (Proof Key for Code Exchange) for security
- **Localhost Only**: Callbacks only work on localhost (can't be intercepted remotely)
- **Token Storage**: If you save tokens to files, ensure proper file permissions (readable only by you)

## Troubleshooting

### Port Already in Use

```bash
python manage.py get_cli_token --port 8766
```

### Browser Doesn't Open

Manually visit the authorization URL printed in the terminal.

### Token Expired

Delete the saved token file and run the flow again:

```bash
rm .oauth_token
python manage.py get_cli_token --save-to .oauth_token
```

### 401 Unauthorized

Your token may have expired. Get a new one:

```bash
python manage.py get_cli_token
```

## Advanced Usage

### Custom Port

```python
token_data = get_oauth_token(
    client_id=CLIENT_ID,
    production_url=PRODUCTION_URL,
    port=9000,  # Use different port
)
```

### Confidential Client (with secret)

```python
token_data = get_oauth_token(
    client_id=CLIENT_ID,
    production_url=PRODUCTION_URL,
    client_secret=CLIENT_SECRET,  # Include secret
)
```

### Quiet Mode (no output)

```python
token_data = get_oauth_token(
    client_id=CLIENT_ID,
    production_url=PRODUCTION_URL,
    verbose=False,  # No output
)
```

## Examples

See `commcare_connect/labs/examples/cli_oauth_example.py` for a complete working example.
