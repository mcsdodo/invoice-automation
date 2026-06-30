"""Unit tests for the pure helpers in src/gmail/auth.py."""

import pytest

from src.gmail.auth import _is_oauth_callback, _resolve_redirect_uri


class TestResolveRedirectUri:
    """Tests for _resolve_redirect_uri(host, port, configured)."""

    def test_returns_configured_when_set(self):
        uri = _resolve_redirect_uri("localhost", 8080, "https://invoice-merging.lacny.me/oauth2callback")
        assert uri == "https://invoice-merging.lacny.me/oauth2callback"

    def test_returns_localhost_fallback_when_empty_string(self):
        uri = _resolve_redirect_uri("localhost", 8080, "")
        assert uri == "http://localhost:8080/"

    def test_returns_localhost_fallback_uses_host_and_port(self):
        uri = _resolve_redirect_uri("192.168.1.10", 9090, "")
        assert uri == "http://192.168.1.10:9090/"

    def test_configured_returned_verbatim_no_trailing_slash_added(self):
        """Registered redirect URI must be used exactly as-is — no munging."""
        configured = "https://example.com/oauth2callback"
        uri = _resolve_redirect_uri("localhost", 8080, configured)
        assert uri == configured


class TestIsOauthCallback:
    """Tests for _is_oauth_callback(query)."""

    def test_query_with_code_is_callback(self):
        assert _is_oauth_callback("code=4/0AQSTx0k&state=abc") is True

    def test_query_with_error_is_callback(self):
        assert _is_oauth_callback("error=access_denied&state=abc") is True

    def test_empty_query_is_not_callback(self):
        assert _is_oauth_callback("") is False

    def test_favicon_probe_is_not_callback(self):
        assert _is_oauth_callback("") is False

    def test_unrelated_params_not_callback(self):
        assert _is_oauth_callback("foo=bar&baz=qux") is False

    def test_both_code_and_error_present(self):
        # Unlikely but should still be recognised as a callback
        assert _is_oauth_callback("code=abc&error=access_denied") is True
