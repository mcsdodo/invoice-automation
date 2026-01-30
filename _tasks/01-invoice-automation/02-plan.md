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
- [ ] `WorkflowData` model (state, timesheet_path, approval_received, invoice_received, etc.)
- [ ] `TimesheetInfo` model (total_hours, date_range, month, year)
- [ ] JSON serialization for state persistence

### 1.4 Unit tests for Phase 1
- [ ] Test config loading and validation
- [ ] Test model serialization/deserialization

**Deliverable:** Docker container that starts, loads config, and exits cleanly.

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

### 2.4 Unit tests for Phase 2
- [ ] Test parser with sample Jira timesheet PDF
- [ ] Test merger with sample PDFs
- [ ] Test HTML to PDF conversion

**Deliverable:** CLI tool to parse timesheet, merge PDFs, convert HTML.

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
- [ ] "All docs ready" message with Approve/Cancel buttons

### 3.4 Error notifications
- [ ] Send error messages with context
- [ ] Optional retry buttons

### 3.5 Unit tests for Phase 3
- [ ] Test message formatting
- [ ] Test callback handling (mocked)

**Deliverable:** Standalone bot that responds to commands and button presses.

---

## Phase 4: Gmail Integration

**Goal:** Send emails, monitor inbox for specific emails, OAuth authentication.

### 4.1 Authentication (`src/gmail/auth.py`)
- [ ] OAuth 2.0 flow with user consent
- [ ] Store/load refresh token
- [ ] Auto-refresh access token

### 4.2 Email sender (`src/gmail/sender.py`)
- [ ] Send email with attachment
- [ ] Reply to existing thread (preserve thread ID)
- [ ] Support TO and CC recipients

### 4.3 Email monitor (`src/gmail/monitor.py`)
- [ ] Poll inbox for new emails (configurable interval)
- [ ] Filter by sender, CC, subject pattern
- [ ] Extract email body, attachments
- [ ] Extract thread ID for replies
- [ ] Mark emails as read after processing

### 4.4 Email matching logic
- [ ] Fuzzy keyword matching for approval emails
- [ ] Invoice detection from PDF attachment

### 4.5 Integration tests for Phase 4
- [ ] Test OAuth flow (manual one-time)
- [ ] Test sending email (to self with alias)
- [ ] Test receiving email (with alias filter)

**Deliverable:** Scripts to send test email, monitor inbox, detect approval/invoice.

---

## Phase 5: LLM Integration

**Goal:** Gemini LLM for fallback email classification and invoice verification.

### 5.1 Gemini client (`src/llm/gemini.py`)
- [ ] Initialize with API key
- [ ] Async text generation
- [ ] Structured output parsing (JSON)

### 5.2 Email classification
- [ ] Prompt for "Is this an approval email?"
- [ ] Return yes/no with confidence

### 5.3 Invoice verification
- [ ] Prompt for "Is this a PDF an invoice? Extract invoice number and total."
- [ ] Return structured data (is_invoice, invoice_number, total)

### 5.4 Unit tests for Phase 5
- [ ] Test with sample email texts
- [ ] Test with sample invoice text extracts

**Deliverable:** LLM helper functions for classification tasks.

---

## Phase 6: Folder Watcher

**Goal:** Monitor folder for new timesheet PDFs.

### 6.1 Watcher (`src/watcher.py`)
- [ ] Watch configured folder using watchdog
- [ ] Detect new PDF files
- [ ] Debounce rapid changes (file still being written)
- [ ] Emit events to workflow coordinator

### 6.2 Unit tests for Phase 6
- [ ] Test file detection
- [ ] Test debouncing

**Deliverable:** Watcher that logs new PDF detections.

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
- [ ] WAITING_DOCS: Send emails, track approval_received/invoice_received flags
- [ ] ALL_DOCS_READY: Merge PDFs, send Telegram message, wait for approval
- [ ] COMPLETE: Send final email, archive files, return to IDLE

### 7.3 Event handlers
- [ ] Handle folder watcher events
- [ ] Handle Telegram button callbacks
- [ ] Handle Gmail monitor events (new email detected)

### 7.4 Archiving
- [ ] Move all files to archive folder (configurable)
- [ ] Organize by YYYY-MM subfolder

### 7.5 Integration tests for Phase 7
- [ ] Test state transitions with mocked components
- [ ] Test state persistence across restarts

**Deliverable:** Workflow that responds to events and persists state.

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

### 8.3 End-to-end manual test
- [ ] Drop test PDF
- [ ] Verify Telegram message
- [ ] Approve via button
- [ ] Verify emails sent

**Deliverable:** Running service in Docker.

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
    ↓
Phase 2 (PDF) ←──────────────────────┐
    ↓                                │
Phase 3 (Telegram)                   │
    ↓                                │
Phase 4 (Gmail)                      │
    ↓                                │
Phase 5 (LLM)                        │
    ↓                                │
Phase 6 (Watcher)                    │
    ↓                                │
Phase 7 (Workflow) ──────────────────┘
    ↓
Phase 8 (Integration)
    ↓
Phase 9 (Testing)
    ↓
Phase 10 (Docs & Cleanup)
```

## Implementation Notes

- **Test each phase before moving on** - Don't accumulate untested code
- **Start with happy path** - Error handling can be refined later
- **Use structured logging** - Will help debugging in production
- **Keep async consistent** - All I/O operations should be async

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
