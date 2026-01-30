**Date:** 2026-01-30
**Subject:** Invoice Automation Implementation Plan
**Status:** Planning

# Implementation Plan

## Overview

This plan breaks the invoice automation service into phases with clear dependencies. Each phase builds on the previous, allowing for incremental testing and validation.

## Phase 1: Project Foundation

**Goal:** Basic project structure, Docker setup, configuration, and data models.

### 1.1 Project scaffolding
- [ ] Create `requirements.txt` with all dependencies
- [ ] Create `Dockerfile`
- [ ] Create `docker-compose.yml`
- [ ] Create `.env.example`

### 1.2 Configuration module (`src/config.py`)
- [ ] Pydantic settings model with all env vars
- [ ] Validation for required fields
- [ ] Type-safe config access

### 1.3 Data models (`src/models.py`)
- [ ] `WorkflowState` enum (IDLE, PENDING_INIT_APPROVAL, WAITING_DOCS, ALL_DOCS_READY, COMPLETE)
- [ ] `WorkflowData` model:
  - `state: WorkflowState`
  - `timesheet_path: str | None`
  - `timesheet_info: TimesheetInfo | None`
  - `approval_received: bool`
  - `invoice_received: bool`
  - `manager_thread_id: str | None` — for reply-to functionality
  - `accountant_thread_id: str | None` — for reply-to functionality
  - `invoice_pdf_path: str | None` — downloaded invoice location
  - `approval_email_html: str | None` — for PDF conversion
  - `waiting_since: datetime | None` — for timeout tracking
  - `telegram_message_id: int | None` — for editing messages
- [ ] `TimesheetInfo` model (total_hours, date_range, month, year)
- [ ] JSON serialization for state persistence

### 1.4 Unit tests for Phase 1
- [ ] Test config loading and validation
- [ ] Test model serialization/deserialization
- [ ] Test WorkflowData with all new fields

**Deliverable:** Docker container that starts, loads config, and exits cleanly.

**Verification:**
- [ ] `python -m pytest tests/unit/test_config.py -v` passes
- [ ] `python -m pytest tests/unit/test_models.py -v` passes
- [ ] `docker build -t invoice-automation .` succeeds
- [ ] `docker run --rm invoice-automation python -c "from src.config import Settings"` exits 0

---

## Phase 2: PDF Processing

**Goal:** Extract data from timesheet PDFs, merge multiple PDFs, convert HTML to PDF.

### 2.1 PDF parser (`src/pdf/parser.py`)
- [ ] Extract total hours from Jira timesheet PDF
- [ ] Extract date range (format: "01/Jan/26 - 31/Jan/26")
- [ ] Parse month/year from date range
- [ ] Handle extraction errors gracefully

### 2.2 PDF merger (`src/pdf/merger.py`)
- [ ] Merge 3 PDFs in order: invoice → timesheet → approval
- [ ] Accept file paths, output merged PDF

### 2.3 HTML to PDF (`src/pdf/html_to_pdf.py`)
- [ ] Playwright-based HTML to PDF conversion
- [ ] Accept HTML string, output PDF file
- [ ] Async implementation
- [ ] Browser lifecycle management:
  - Lazy initialization (start browser on first use)
  - Reuse browser instance across conversions
  - Configurable timeout (default 30s)
  - Graceful shutdown on service stop
- [ ] Error handling: return None or raise on timeout/failure

### 2.4 Unit tests for Phase 2
- [ ] Test parser with sample Jira timesheet PDF (`tests/fixtures/timesheet_sample.pdf`)
- [ ] Test merger with sample PDFs (`tests/fixtures/invoice_sample.pdf`, etc.)
- [ ] Test HTML to PDF conversion
- [ ] Test browser timeout handling

**Deliverable:** CLI tool to parse timesheet, merge PDFs, convert HTML.

**Verification:**
- [ ] `python -m src.pdf.parser tests/fixtures/timesheet_sample.pdf` outputs hours and date range
- [ ] `python -m src.pdf.merger` with 3 sample PDFs produces valid merged PDF
- [ ] `python -m src.pdf.html_to_pdf` converts sample HTML to PDF

---

## Phase 3: Telegram Bot

**Goal:** Interactive Telegram bot with inline keyboards for approvals.

### 3.1 Bot setup (`src/telegram/bot.py`)
- [ ] Initialize bot with token
- [ ] Configure allowed chat ID
- [ ] Async polling/webhook setup

### 3.2 Notification messages
- [ ] Send text messages with formatting
- [ ] Send messages with inline keyboard buttons
- [ ] Update existing messages (edit text, remove buttons)

### 3.3 Approval interactions
- [ ] "New timesheet" message with Approve/Edit/Cancel buttons
- [ ] Handle button callbacks
- [ ] Edit flow: ask for hours, recalculate, show updated message
  - Validate input: must be positive integer, reasonable range (1-300)
  - On invalid input: send error message, re-prompt
  - Timeout for edit response: 5 minutes, then cancel edit mode
- [ ] "All docs ready" message with Approve/Cancel buttons
- [ ] Cancel handling:
  - PENDING_INIT_APPROVAL + Cancel → return to IDLE, move PDF to `archive/cancelled/`
  - ALL_DOCS_READY + Cancel → return to IDLE, archive all collected docs as cancelled

### 3.4 Error notifications
- [ ] Send error messages with context
- [ ] Optional retry buttons

### 3.5 Unit tests for Phase 3
- [ ] Test message formatting
- [ ] Test callback handling (mocked)
- [ ] Test input validation for edit flow

**Deliverable:** Standalone bot that responds to commands and button presses.

**Verification:**
- [ ] Run bot, send `/start` command, verify response
- [ ] Trigger test notification with inline buttons
- [ ] Press each button type, verify callback handled
- [ ] Test edit flow with valid and invalid inputs

---

## Phase 4: Gmail Integration

**Goal:** Send emails, monitor inbox for specific emails, OAuth authentication.

### 4.1 Authentication (`src/gmail/auth.py`)
- [ ] OAuth 2.0 flow with user consent
- [ ] Store/load refresh token
- [ ] Auto-refresh access token
- [ ] Proactive token refresh: check expiry before API calls, refresh if < 5 min remaining
- [ ] Handle refresh token revocation: notify via Telegram, require manual re-auth

### 4.2 Email sender (`src/gmail/sender.py`)
- [ ] Send email with attachment
- [ ] Reply to existing thread (preserve thread ID)
- [ ] Support TO and CC recipients

### 4.3 Email monitor (`src/gmail/monitor.py`)
- [ ] Poll inbox for new emails (configurable interval, default 60s)
- [ ] Filter by sender, CC, subject pattern
- [ ] Extract email body (HTML and plain text)
- [ ] Extract thread ID for replies, store in WorkflowData
- [ ] Attachment handling:
  - Download PDF attachments to `data/temp/` directory
  - Rename to `invoice_{timestamp}.pdf` for uniqueness
  - Store path in `WorkflowData.invoice_pdf_path`
  - Cleanup temp files after archiving
- [ ] Mark emails as read after processing
- [ ] Error handling:
  - Gmail API rate limit (429): exponential backoff, max 5 retries
  - Network error: retry with backoff, notify Telegram after 3 failures
  - Auth error: trigger token refresh, notify if refresh fails

### 4.4 Email matching logic
- [ ] Fuzzy keyword matching for approval emails
- [ ] Invoice detection from PDF attachment

### 4.5 Integration tests for Phase 4
- [ ] Test OAuth flow (manual one-time)
- [ ] Test sending email (to self with alias)
- [ ] Test receiving email (with alias filter)
- [ ] Test attachment download
- [ ] Test thread ID extraction

**Deliverable:** Scripts to send test email, monitor inbox, detect approval/invoice.

**Verification:**
- [ ] Run auth script, complete OAuth flow, verify token.json created
- [ ] Send test email with attachment, verify delivery
- [ ] Start monitor, send email from alias, verify detection and thread ID capture
- [ ] Verify PDF attachment downloaded to `data/temp/`

---

## Phase 5: LLM Integration

**Goal:** Gemini LLM for fallback email classification and invoice verification.

### 5.1 Gemini client (`src/llm/gemini.py`)
- [ ] Initialize with API key
- [ ] Async text generation
- [ ] Structured output parsing (JSON)
- [ ] Error handling with graceful degradation:
  - API timeout (30s): return "uncertain" result
  - API error (4xx/5xx): return "uncertain" result
  - Rate limit: return "uncertain" result (no retry for LLM fallback)
- [ ] When LLM unavailable: escalate to Telegram for manual classification

### 5.2 Email classification
- [ ] Prompt for "Is this an approval email?"
- [ ] Return yes/no with confidence

### 5.3 Invoice verification
- [ ] Prompt for "Is this a PDF an invoice? Extract invoice number and total."
- [ ] Return structured data (is_invoice, invoice_number, total)

### 5.4 Unit tests for Phase 5
- [ ] Test with sample email texts
- [ ] Test with sample invoice text extracts
- [ ] Test error handling (mocked API failures)
- [ ] Test graceful degradation returns "uncertain"

**Deliverable:** LLM helper functions for classification tasks.

**Verification:**
- [ ] Run classification on sample approval email, verify yes/no response
- [ ] Run classification on sample non-approval email, verify correct response
- [ ] Simulate API timeout, verify "uncertain" returned without crash

---

## Phase 6: Folder Watcher

**Goal:** Monitor folder for new timesheet PDFs.

### 6.1 Watcher (`src/watcher.py`)
- [ ] Watch configured folder using watchdog
- [ ] Detect new PDF files
- [ ] Debounce rapid changes: wait 2 seconds after last modification before emitting
- [ ] Emit events to workflow coordinator via async queue

### 6.2 Unit tests for Phase 6
- [ ] Test file detection
- [ ] Test debouncing (rapid writes coalesce to single event)

**Deliverable:** Watcher that logs new PDF detections.

**Verification:**
- [ ] Start watcher on test folder, drop PDF, verify event logged within 3 seconds
- [ ] Copy large PDF slowly, verify single event after file complete (not multiple)

---

## Phase 7: Workflow Coordinator

**Goal:** State machine that orchestrates the entire workflow.

### 7.1 State persistence (`src/workflow.py`)
- [ ] Load state from JSON on startup
- [ ] Save state after each transition
- [ ] Handle missing/corrupt state file

### 7.2 State machine
- [ ] IDLE: Wait for folder watcher event
- [ ] PENDING_INIT_APPROVAL: Parse PDF, send Telegram message, wait for approval
  - Approve → transition to WAITING_DOCS
  - Edit → stay in state, update hours, resend message
  - Cancel → archive PDF to `cancelled/`, transition to IDLE
- [ ] WAITING_DOCS: Send emails, track approval_received/invoice_received flags
  - Set `waiting_since` timestamp on entry
  - Timeout check: if waiting > 7 days, send Telegram reminder
  - Timeout check: if waiting > 14 days, send daily reminders
  - Manual override: add "Cancel workflow" button to reminder messages
  - On both received → transition to ALL_DOCS_READY
- [ ] ALL_DOCS_READY: Merge PDFs, send Telegram message, wait for approval
  - Approve → transition to COMPLETE
  - Cancel → archive all docs to `cancelled/`, transition to IDLE
- [ ] COMPLETE: Send final email, archive files, return to IDLE

### 7.3 Event handlers
- [ ] Handle folder watcher events
- [ ] Handle Telegram button callbacks
- [ ] Handle Gmail monitor events (new email detected)
- [ ] Concurrency handling:
  - Single asyncio.Queue for all events
  - Process events sequentially (one at a time)
  - Lock state during transitions to prevent race conditions
  - Log and discard duplicate/stale events (e.g., approval after cancel)

### 7.4 Archiving
- [ ] Move all files to archive folder (configurable)
- [ ] Organize by YYYY-MM subfolder

### 7.5 Integration tests for Phase 7
- [ ] Test state transitions with mocked components
- [ ] Test state persistence across restarts
- [ ] Test Cancel transitions from each cancellable state
- [ ] Test timeout reminders at 7 and 14 days (with mocked time)
- [ ] Test concurrent event handling (no race conditions)

**Deliverable:** Workflow that responds to events and persists state.

**Verification:**
- [ ] Start in IDLE, inject folder event, verify transition to PENDING_INIT_APPROVAL
- [ ] Inject approval, verify transition to WAITING_DOCS
- [ ] Kill process, restart, verify state restored from JSON
- [ ] Test Cancel at PENDING_INIT_APPROVAL, verify PDF archived to `cancelled/`
- [ ] Inject rapid events, verify sequential processing without errors

---

## Phase 8: Main Entry Point & Integration

**Goal:** Wire everything together, single entry point.

### 8.1 Main module (`src/main.py`)
- [ ] Load config
- [ ] Initialize all components
- [ ] Start async event loop with all tasks:
  - Folder watcher
  - Gmail monitor
  - Telegram bot
  - Workflow coordinator
- [ ] Graceful shutdown handling

### 8.2 Docker integration
- [ ] Verify container starts correctly
- [ ] Verify volume mounts work
- [ ] Verify env vars loaded
- [ ] Volume permissions:
  - `/watch` mount: read-only (`:ro`)
  - `/archive` mount: read-write, ensure container user can write
  - `/app/data` mount: read-write for state.json and temp files
  - `/app/config` mount: read-only for credentials
- [ ] Create `data/temp/` directory on startup if missing

### 8.3 End-to-end manual test
- [ ] Drop test PDF
- [ ] Verify Telegram message
- [ ] Approve via button
- [ ] Verify emails sent

**Deliverable:** Running service in Docker.

**Verification:**
- [ ] `docker-compose up -d` starts without errors
- [ ] `docker-compose logs` shows "Service started, watching folder..."
- [ ] Container can write to `data/state.json`
- [ ] Container can write to archive folder
- [ ] Container can read from watch folder

---

## Phase 9: Testing Suite

**Goal:** Comprehensive testing with automated and interactive tests.

### 9.1 Test configuration
- [ ] Create `.env.test` with Gmail aliases
- [ ] Create test fixtures (sample PDFs, email HTML)
- [ ] Set up separate Telegram test chat

### 9.2 Unit tests (complete coverage)
- [ ] All pure logic functions tested
- [ ] Config validation
- [ ] State transitions
- [ ] Email matching
- [ ] PDF parsing

### 9.3 Automated integration tests
- [ ] Gmail send/receive with aliases
- [ ] Telegram bot interactions (programmatic)
- [ ] Full workflow happy path
- [ ] Error scenarios

### 9.4 Interactive test runner
- [ ] CLI for step-by-step human-in-the-loop testing
- [ ] Scenarios: happy path, edit hours, error recovery

**Deliverable:** Full test suite with `pytest` commands documented.

---

## Phase 10: Documentation & Cleanup

**Goal:** Finalize documentation, clean up code.

### 10.1 Documentation
- [ ] Update CLAUDE.md if needed
- [ ] Verify .env.example is complete
- [ ] Add comments to complex logic

### 10.2 Code cleanup
- [ ] Remove debug prints
- [ ] Verify logging is consistent
- [ ] Run linter (ruff/black)
- [ ] Type check (mypy)

### 10.3 Final verification
- [ ] Full interactive test
- [ ] Deploy to homelab (Komodo)
- [ ] Run one real workflow

**Deliverable:** Production-ready service.

---

## Dependencies Graph

```
                      Phase 1 (Foundation)
                              │
          ┌─────────┬─────────┼─────────┬─────────┐
          ▼         ▼         ▼         ▼         ▼
       Phase 2   Phase 3   Phase 4   Phase 5   Phase 6
        (PDF)   (Telegram) (Gmail)   (LLM)    (Watcher)
          │         │         │         │         │
          └─────────┴─────────┴────┬────┴─────────┘
                                   ▼
                        Phase 7 (Workflow)
                                   │
                                   ▼
                        Phase 8 (Integration)
                                   │
                                   ▼
                         Phase 9 (Testing)
                                   │
                                   ▼
Phase 10 (Docs & Cleanup)
```

## Implementation Notes

- **Phases 2-6 are parallelizable** - After Phase 1, these 5 modules can be developed independently
- **Test each phase before moving on** - Don't accumulate untested code
- **Start with happy path** - Error handling can be refined later
- **Use structured logging** - Will help debugging in production
- **Keep async consistent** - All I/O operations should be async

## Parallelization Strategy

| Step | Phases | Can Parallelize? |
|------|--------|------------------|
| 1 | Phase 1 (Foundation) | No - required by all |
| 2 | Phases 2, 3, 4, 5, 6 | **Yes - 5 independent modules** |
| 3 | Phase 7 (Workflow) | No - needs all of 2-6 |
| 4 | Phase 8 (Integration) | No - needs 7 |
| 5 | Phases 9, 10 | No - sequential |

**Optimal with parallel agents:** Complete in 5 steps instead of 10 sequential phases.

## Estimated Complexity

| Phase | Complexity | Notes |
|-------|------------|-------|
| 1 | Low | Boilerplate |
| 2 | Medium | PDF parsing may need iteration |
| 3 | Medium | Telegram API learning curve |
| 4 | High | Gmail API complexity, OAuth |
| 5 | Low | Simple API calls |
| 6 | Low | watchdog is straightforward |
| 7 | High | Core logic, many edge cases |
| 8 | Medium | Integration debugging |
| 9 | Medium | Test setup effort |
| 10 | Low | Polish |
