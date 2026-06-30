from unittest.mock import patch, MagicMock

from src.gmail.auth import SCOPES
from src.gdrive.auth import DRIVE_SCOPE, get_drive_service


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


def test_get_credentials_forces_reauth_when_scopes_stale(tmp_path):
    """A stored token missing the drive scope must force a fresh OAuth flow."""
    import src.gmail.auth as auth

    stale = MagicMock()
    stale.has_scopes.return_value = False  # token predates the drive scope
    fresh = MagicMock()
    with patch.object(auth, "_load_credentials", return_value=stale), \
         patch.object(auth, "_run_oauth_flow", return_value=fresh) as m_flow, \
         patch.object(auth, "_save_credentials"):
        out = auth.get_credentials()
    m_flow.assert_called_once()
    assert out is fresh
