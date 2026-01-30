# Plan Review: Telegram Persistent Debug Keyboard

**Date:** 2026-01-30
**Auditor:** Claude Code
**Status:** Complete
**Plan Location:** _tasks/01-telegram-debug-keyboard/02-plan.md

## Iterations

### Iteration 1

| Severity | Finding | Section | Status |
|----------|---------|---------|--------|
| Critical | Path hardcoding: `Path("data/state.json")` - should use `workflow.STATE_FILE` or import from workflow | Step 4a | [x] |
| Important | Gmail OAuth: `get_gmail_service()` is synchronous, must wrap in `asyncio.to_thread()` | Step 6 | [x] |
| Important | Missing error handling in debug handlers (Gmail fails, file write fails) | Step 4 | [x] |
| Important | No verification criteria for implementation steps | All | [x] |
| Minor | Step 5 unclear: two options given, no decision made | Step 5 | [x] |
| Minor | Handler 4c/4d comments say "Requires: workflow coordinator reference" but recommendation says import directly - inconsistent | Step 4c/4d | [x] |

### Iteration 2

| Severity | Finding | Section | Status |
|----------|---------|---------|--------|
| Important | Watch folder: Plan says hardcoded but should use `settings.watch_folder` from config | Step 4b | [x] |
| Important | Bot already has `_reset_handler` pattern - debug reset should use existing workflow reset, not duplicate logic | Step 4e | [x] |
| Important | Drop PDF hours should be configurable - script accepts `sys.argv[1]`, debug button should prompt or use default | Step 4b | [x] |
| Minor | Scripts use `settings.from_email` for both From and To (self-test) - debug handlers should do same for testing | Step 4c/4d | [x] |
| Minor | Missing: What happens if user presses "Send Approval" when not in WAITING_DOCS state? Need state validation | Step 4c | [x] |

### Iteration 3

| Severity | Finding | Section | Status |
|----------|---------|---------|--------|
| Important | Path hardcoding concern is RESOLVED - Docker overrides paths via env vars, `settings` object handles this correctly | Step 4a | [x] |
| Minor | No startup message mentioned to confirm keyboard is active (helpful for debugging first run) | Step 5 | [x] |
| Minor | No mention of logging in debug handlers for troubleshooting | Step 4 | [x] |

**No new critical findings in Iteration 3 - review complete.**

## Summary

### Revisions Applied

1. **Import `STATE_FILE` from workflow** instead of hardcoding path
2. **Wrap all Gmail calls in `asyncio.to_thread()`** to avoid blocking event loop
3. **Added try/except with error messages** to all debug handlers
4. **Added verification criteria** to each implementation step
5. **Decided on startup message approach** - send message in `initialize()` with keyboard
6. **Removed inconsistent comments** - all handlers import directly, no coordinator reference needed
7. **Use `settings.watch_folder`** for Drop PDF path
8. **Reuse `_reset_handler`** instead of duplicating reset logic
9. **Fixed default hours** to 160 (no prompting, simpler UX)
10. **Use `settings.from_email`** for both From/To in self-test emails
11. **Added state validation** - Send Approval/Invoice check for WAITING_DOCS state
12. **Added logging** to all debug handlers

**Plan Ready for Implementation:** Yes
