import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from src.gmail.auth import SCOPES
from src.gdrive.auth import DRIVE_SCOPE, get_drive_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

GMAIL_SCOPES_ONLY = [s for s in SCOPES if "drive" not in s]
ALL_SCOPES = list(SCOPES)


def _write_token(path, scopes, *, expiry_offset_sec=3600):
    """Write a minimal token.json to *path* with the given scopes."""
    expiry = datetime.now(timezone.utc) + timedelta(seconds=expiry_offset_sec)
    token_data = {
        "token": "dummy_access_token",
        "refresh_token": "dummy_refresh_token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "dummy_client_id",
        "client_secret": "dummy_client_secret",
        "scopes": scopes,
        "expiry": expiry.isoformat(),
    }
    path.write_text(json.dumps(token_data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Existing structural tests
# ---------------------------------------------------------------------------

def test_drive_scope_present_in_shared_scopes():
    assert DRIVE_SCOPE == "https://www.googleapis.com/auth/drive"
    assert DRIVE_SCOPE in SCOPES


def test_get_drive_service_builds_v3_with_shared_creds():
    fake_creds = MagicMock()
    with patch("src.gdrive.auth.get_credentials", return_value=fake_creds) as m_creds, \
         patch("src.gdrive.auth.build") as m_build:
        get_drive_service()
    m_creds.assert_called_once()
    m_build.assert_called_once_with("drive", "v3", credentials=fake_creds)


# ---------------------------------------------------------------------------
# Fix 1 — scope-staleness gate reads actual token.json scopes
# ---------------------------------------------------------------------------

def test_get_credentials_forces_reauth_when_scopes_stale(tmp_path, monkeypatch):
    """Stale token (no drive scope) must trigger a fresh OAuth flow.

    This test would FAIL against the old has_scopes()-based gate because
    Credentials.from_authorized_user_file(path, SCOPES) populates creds.scopes
    with SCOPES regardless of what the file contains, making has_scopes() always
    return True.  The fix reads scopes directly from the JSON file.
    """
    import src.gmail.auth as auth

    token_path = tmp_path / "token.json"
    _write_token(token_path, GMAIL_SCOPES_ONLY)  # drive scope absent

    fresh = MagicMock()
    monkeypatch.setattr(auth.settings, "gmail_token_file", token_path)
    monkeypatch.setattr(auth.settings, "gmail_credentials_file", tmp_path / "creds.json")

    with patch.object(auth, "_run_oauth_flow", return_value=fresh) as m_flow, \
         patch.object(auth, "_save_credentials"):
        out = auth.get_credentials()

    m_flow.assert_called_once()
    assert out is fresh


def test_get_credentials_skips_reauth_when_scopes_current(tmp_path, monkeypatch):
    """Current token (all scopes incl. drive, not expired) must NOT trigger OAuth.

    The key assertion is that _run_oauth_flow is never called.
    """
    import src.gmail.auth as auth

    token_path = tmp_path / "token.json"
    _write_token(token_path, ALL_SCOPES)  # all scopes present, far-future expiry

    monkeypatch.setattr(auth.settings, "gmail_token_file", token_path)
    monkeypatch.setattr(auth.settings, "gmail_credentials_file", tmp_path / "creds.json")

    with patch.object(auth, "_run_oauth_flow") as m_flow, \
         patch.object(auth, "_refresh_credentials", side_effect=lambda c: c), \
         patch.object(auth, "_save_credentials"):
        # _load_credentials will try to build a real Credentials object; patch it
        # to return something that looks valid so we reach the scope check.
        fake_creds = MagicMock()
        fake_creds.valid = True
        fake_creds.expiry = datetime.now(timezone.utc) + timedelta(hours=1)
        with patch.object(auth, "_load_credentials", return_value=fake_creds), \
             patch.object(auth, "_needs_refresh", return_value=False):
            out = auth.get_credentials()

    m_flow.assert_not_called()
    assert out is fake_creds
