# Tech Debt: OAuth Docker Workarounds

**Date:** 2026-01-30
**Priority:** Medium
**Effort:** Medium (2-8h)
**Component:** `src/gmail/auth.py`, `docker-compose.yml`
**Status:** Open

## Problem

The Gmail OAuth flow in Docker required multiple workarounds to function:

1. **Insecure transport flag**: Had to set `OAUTHLIB_INSECURE_TRANSPORT=1` to allow HTTP callback
2. **Custom WSGI server**: The google-auth-oauthlib `run_local_server()` uses `print()` for URL output which doesn't appear in Docker logs. Had to implement custom WSGI handler.
3. **Manual state management**: Had to call `authorization_url()` manually and handle state ourselves instead of using the library's built-in flow
4. **Unbuffered Python**: Required `PYTHONUNBUFFERED=1` for real-time log output

## Impact

- **Security**: `OAUTHLIB_INSECURE_TRANSPORT=1` disables HTTPS requirement
- **Maintenance**: Custom OAuth flow code is more complex than using library defaults
- **Deployment**: OAuth must happen at startup; if container restarts and token expired, requires manual intervention

## Root Cause

The google-auth-oauthlib library was designed for desktop apps where:
- Browser can be opened automatically
- Callback is on localhost directly accessible
- stdout is visible to user

In Docker:
- No browser available
- Callback needs port mapping
- stdout goes to logs, `print()` may be buffered

## Recommended Solution

### Option A: Use `run_console()` flow (Simpler)
The library has `run_console()` which prints a URL and asks user to paste the authorization code. This is designed for headless environments.

```python
creds = flow.run_console()
```

Pros: Simpler, no port mapping needed
Cons: Requires user to copy-paste auth code

### Option B: Pre-generate token externally (Cleanest)
Require token.json to exist before container starts:
1. Run `scripts/test_gmail.py` locally to generate token
2. Mount token.json into container
3. Container fails fast if no valid token

Pros: No OAuth complexity in container
Cons: Requires local setup step

### Option C: HTTPS with self-signed cert (Most secure)
Use HTTPS for callback with self-signed certificate:
1. Generate self-signed cert at container startup
2. Use HTTPS callback URL
3. User accepts browser security warning

Pros: No insecure transport flag needed
Cons: More complex, user sees security warning

## Alternative Options

Current implementation (custom WSGI + insecure transport) works but is hacky.

## Related

- `docker-compose.yml` - Environment variables
- `src/gmail/auth.py` - OAuth implementation
- `scripts/test_gmail.py` - Local token generation

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-01-30 | Implemented custom WSGI OAuth flow | Library's run_local_server() didn't work in Docker due to print() buffering and HTTPS requirements |
| 2026-01-30 | Added OAUTHLIB_INSECURE_TRANSPORT=1 | Required for HTTP localhost callback |
| 2026-01-30 | Created tech debt item | Workarounds functional but need proper solution |
