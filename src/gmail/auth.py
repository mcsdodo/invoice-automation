"""Gmail OAuth authentication module.

Handles OAuth 2.0 flow, token storage, and automatic refresh.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build, Resource

from src.config import settings

logger = logging.getLogger(__name__)

# Gmail API scopes - must match what test_gmail.py uses
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

# Minimum remaining token lifetime before proactive refresh (5 minutes)
MIN_TOKEN_LIFETIME_SECONDS = 300


def _load_credentials(token_path: Path) -> Credentials | None:
    """Load credentials from token file if it exists."""
    if not token_path.exists():
        logger.debug("Token file not found: %s", token_path)
        return None

    try:
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        logger.debug("Credentials loaded from %s", token_path)
        return creds
    except Exception as e:
        logger.warning("Failed to load credentials from %s: %s", token_path, e)
        return None


def _save_credentials(creds: Credentials, token_path: Path) -> None:
    """Save credentials to token file."""
    # Ensure parent directory exists
    token_path.parent.mkdir(parents=True, exist_ok=True)

    token_path.write_text(creds.to_json())
    logger.debug("Credentials saved to %s", token_path)


def _needs_refresh(creds: Credentials) -> bool:
    """Check if credentials need refresh (expired or < 5 min remaining)."""
    if not creds.valid:
        return True

    if not creds.expiry:
        # No expiry info, assume it's fine
        return False

    # Check if less than 5 minutes remaining
    now = datetime.now(timezone.utc)
    expiry = creds.expiry.replace(tzinfo=timezone.utc) if creds.expiry.tzinfo is None else creds.expiry
    remaining = (expiry - now).total_seconds()

    if remaining < MIN_TOKEN_LIFETIME_SECONDS:
        logger.debug("Token expires in %d seconds, needs refresh", remaining)
        return True

    return False


def _refresh_credentials(creds: Credentials) -> Credentials:
    """Refresh expired or soon-to-expire credentials."""
    if not creds.refresh_token:
        raise ValueError("No refresh token available, re-authentication required")

    try:
        creds.refresh(Request())
        logger.info("Successfully refreshed access token")
        return creds
    except Exception as e:
        logger.error("Failed to refresh token: %s", e)
        raise


def _run_oauth_flow(credentials_path: Path) -> Credentials:
    """Run interactive OAuth flow to get new credentials."""
    if not credentials_path.exists():
        raise FileNotFoundError(
            f"OAuth credentials file not found: {credentials_path}. "
            "Download from Google Cloud Console."
        )

    import sys
    from wsgiref.simple_server import make_server
    import threading

    port = settings.oauth_callback_port
    host = settings.oauth_callback_host

    flow = InstalledAppFlow.from_client_secrets_file(
        str(credentials_path), SCOPES
    )
    flow.redirect_uri = f"http://{host}:{port}/"

    # Generate auth URL with state
    auth_url, state = flow.authorization_url(access_type="offline", prompt="consent")

    logger.warning("=" * 60)
    logger.warning("OAUTH AUTHENTICATION REQUIRED")
    logger.warning("=" * 60)
    logger.warning(f"Open this URL in your browser:")
    logger.warning(auth_url)
    logger.warning("=" * 60)
    logger.warning(f"Waiting for callback on http://{host}:{port}/ ...")
    sys.stdout.flush()
    sys.stderr.flush()

    # Simple WSGI app to capture the callback
    authorization_response = [None]

    def wsgi_app(environ, start_response):
        from urllib.parse import urlunsplit
        query = environ.get("QUERY_STRING", "")
        authorization_response[0] = f"http://{host}:{port}/?{query}"
        start_response("200 OK", [("Content-Type", "text/html")])
        return [b"<html><body><h1>Authorization successful!</h1><p>You can close this window.</p></body></html>"]

    # Start server
    server = make_server("0.0.0.0", port, wsgi_app)
    server.handle_request()  # Handle single request

    # Exchange code for token
    flow.fetch_token(authorization_response=authorization_response[0])
    logger.warning("OAuth flow completed successfully!")
    return flow.credentials


def get_credentials() -> Credentials:
    """Get valid Gmail API credentials.

    Loads from token file, refreshes if needed, or runs OAuth flow.

    Returns:
        Valid Credentials object.

    Raises:
        FileNotFoundError: If credentials.json not found and token doesn't exist.
        ValueError: If refresh token is revoked and re-auth needed.
    """
    token_path = settings.gmail_token_file
    credentials_path = settings.gmail_credentials_file

    # Try to load existing credentials
    creds = _load_credentials(token_path)

    if creds is not None:
        # Check if refresh is needed (expired or < 5 min remaining)
        if _needs_refresh(creds):
            if creds.refresh_token:
                creds = _refresh_credentials(creds)
                _save_credentials(creds, token_path)
            else:
                # No refresh token, need new OAuth flow
                logger.warning("No refresh token, running OAuth flow")
                creds = _run_oauth_flow(credentials_path)
                _save_credentials(creds, token_path)
    else:
        # No existing credentials, run OAuth flow
        creds = _run_oauth_flow(credentials_path)
        _save_credentials(creds, token_path)

    return creds


def get_gmail_service() -> Resource:
    """Get authenticated Gmail API service.

    Returns:
        Authenticated Gmail API service resource.

    Raises:
        FileNotFoundError: If credentials.json not found.
        ValueError: If token refresh fails.
    """
    creds = get_credentials()
    service = build("gmail", "v1", credentials=creds)
    logger.debug("Gmail service created")
    return service
