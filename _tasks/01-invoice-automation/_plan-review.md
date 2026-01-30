# Plan Review: Invoice Automation Service

**Date:** 2026-01-30
**Auditor:** Claude Code
**Status:** In Progress
**Plan Location:** `_tasks/01-invoice-automation/02-plan.md`
**Design Location:** `_tasks/01-invoice-automation/01-design.md`

## Iterations

### Iteration 1

| Severity | Finding | Section | Status |
|----------|---------|---------|--------|
| Critical | No error/timeout handling for email monitor waiting state | Phase 4, Phase 7 | [x] |
| Critical | Missing state machine transitions for Cancel button | Phase 7.2 | [x] |
| Important | No specific file paths for test fixtures | Phase 2.4, Phase 9 | [x] |
| Important | Missing thread management for reply-to functionality | Phase 4.3 | [x] |
| Important | No verification step after each phase deliverable | All phases | [x] |
| Important | Playwright browser lifecycle management not specified | Phase 2.3 | [x] |
| Minor | Dependencies graph shows linear path but phases can run parallel | Dependencies | [ ] |
| Minor | No explicit cleanup for failed workflow states | Phase 7 | [x] |

### Iteration 2

| Severity | Finding | Section | Status |
|----------|---------|---------|--------|
| Critical | WAITING_DOCS state has no timeout/expiration handling | Phase 7.2 | [x] |
| Important | Gmail OAuth token refresh not covered in monitor lifecycle | Phase 4.1, 4.3 | [x] |
| Important | Telegram edit flow lacks validation for invalid input | Phase 3.3 | [x] |
| Important | Missing attachment download/storage for invoice PDF | Phase 4.3 | [x] |
| Important | No specification for data folder structure in Docker | Phase 1.1 | [x] |
| Minor | LLM prompt templates not specified | Phase 5.2, 5.3 | [ ] |
| Minor | APPROVAL_KEYWORDS case sensitivity not specified | Phase 4.4 | [ ] |

### Iteration 3

| Severity | Finding | Section | Status |
|----------|---------|---------|--------|
| Important | Workflow coordinator event handler concurrency not addressed | Phase 7.3 | [x] |
| Important | No graceful degradation if Gemini API unavailable | Phase 5 | [x] |
| Important | Docker volume permissions for watch/archive folders | Phase 8.2 | [x] |
| Minor | Watchdog file stability check timing not specified | Phase 6.1 | [x] |
| Minor | State.json backup/corruption recovery details missing | Phase 7.1 | [ ] |

### Iteration 4

No new findings. Review complete.

---

## Summary

### Critical (Must Address)

1. **Missing Cancel/abort state transitions**: The plan describes Approve/Edit/Cancel buttons but doesn't specify what happens when Cancel is pressed. Need to define:
   - PENDING_INIT_APPROVAL + Cancel → IDLE (discard PDF? archive as cancelled?)
   - ALL_DOCS_READY + Cancel → ? (what happens to already-received docs?)

2. **No timeout for WAITING_DOCS state**: The system could wait indefinitely for approval/invoice emails. Need to specify:
   - Maximum wait time before alerting user
   - Optional manual override to proceed/cancel
   - What happens to partial state (approval received but no invoice, or vice versa)

3. **Email monitor waiting state lacks error handling**: Plan doesn't cover:
   - Gmail API rate limits
   - Network interruption during monitoring
   - Recovery from monitor failures

### Important (Should Address)

4. **Thread ID management for replies**: Phase 4 mentions "Reply to existing thread" but doesn't specify:
   - How/where thread IDs are stored in WorkflowData
   - Thread ID extraction from sent email response
   - Handling if thread ID is missing

5. **Attachment handling details missing**: Phase 4.3 lists "Extract email body, attachments" but doesn't specify:
   - Where downloaded PDFs are stored temporarily
   - Filename handling (keep original vs rename)
   - Cleanup of temp files

6. **Playwright browser lifecycle**: Phase 2.3 just says "async implementation" but should specify:
   - Browser instance reuse vs launch-per-conversion
   - Timeout handling for conversion
   - Memory cleanup

7. **Gmail OAuth in long-running monitor**: Token refresh during active monitoring session not addressed.

8. **Telegram edit flow validation**: What happens if user enters non-numeric or negative hours?

9. **Event handler concurrency**: Multiple events could arrive simultaneously (folder event + email event). Plan doesn't address:
   - Event queue vs direct handling
   - Race condition prevention

10. **Gemini API fallback**: If LLM API is down, what's the fallback for classification?

11. **Docker volume permissions**: Plan doesn't address read/write permissions for mounted volumes.

12. **Verification criteria per phase**: Each phase ends with "Deliverable" but no explicit "how to verify" steps.

### Minor (Nice to Have)

13. **Parallel phase execution**: Phases 2-6 could theoretically be developed in parallel. The linear dependency graph is overly conservative.

14. **Debounce timing**: Phase 6.1 says "debounce rapid changes" but doesn't specify the debounce window (e.g., 2 seconds?).

15. **APPROVAL_KEYWORDS matching**: Should clarify case-insensitive, partial match, word boundary handling.

16. **LLM prompt templates**: Including sample prompts would help implementation consistency.

17. **State file backup**: Should specify behavior on corruption (recreate as IDLE?).

---

**Recommendation**: ~~Revise before implementation. Address all Critical items and Important items 4-11 before starting Phase 1.~~

---

## Revisions Applied

**Date:** 2026-01-30

### Critical Items - All Addressed

1. **Cancel/abort state transitions** - Added to Phase 3.3 and Phase 7.2:
   - PENDING_INIT_APPROVAL + Cancel → IDLE, archive to `cancelled/`
   - ALL_DOCS_READY + Cancel → IDLE, archive all to `cancelled/`

2. **Timeout for WAITING_DOCS** - Added to Phase 7.2:
   - `waiting_since` timestamp in WorkflowData
   - 7-day reminder, 14-day daily reminders
   - Manual "Cancel workflow" button on reminders

3. **Email monitor error handling** - Added to Phase 4.3:
   - Rate limit: exponential backoff, max 5 retries
   - Network error: retry with backoff, Telegram notify after 3 failures
   - Auth error: trigger token refresh, notify if fails

### Important Items - All Addressed

4. **Thread ID management** - Added to Phase 1.3 WorkflowData model:
   - `manager_thread_id` and `accountant_thread_id` fields
   - Phase 4.3 updated to store thread ID on extraction

5. **Attachment handling** - Added to Phase 4.3:
   - Download to `data/temp/`
   - Rename to `invoice_{timestamp}.pdf`
   - Store path in `WorkflowData.invoice_pdf_path`
   - Cleanup after archiving

6. **Playwright lifecycle** - Added to Phase 2.3:
   - Lazy init, browser reuse, 30s timeout, graceful shutdown

7. **Gmail OAuth refresh** - Added to Phase 4.1:
   - Proactive refresh if < 5 min remaining
   - Handle revocation with Telegram notification

8. **Telegram edit validation** - Added to Phase 3.3:
   - Positive integer, range 1-300
   - Error message + re-prompt on invalid
   - 5-minute timeout

9. **Event concurrency** - Added to Phase 7.3:
   - Single asyncio.Queue
   - Sequential processing
   - Lock during transitions
   - Discard stale events

10. **Gemini fallback** - Added to Phase 5.1:
    - Return "uncertain" on timeout/error
    - Escalate to Telegram for manual classification

11. **Docker volume permissions** - Added to Phase 8.2:
    - Specified `:ro` and `:rw` for each mount
    - Create `data/temp/` on startup

12. **Verification steps** - Added to all phases:
    - Specific commands to run
    - Expected outcomes

---

**Status:** Complete
**Plan Ready for Implementation:** Yes
