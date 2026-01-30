# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Implementation plan with 10 phases covering full invoice automation workflow
- Plan review document with iterative quality assessment
- Parallelization strategy showing phases 2-6 can be developed independently
- Infrastructure setup with verified credentials (Gemini, Gmail OAuth, Telegram)
- `requirements.txt` with all project dependencies
- `.env.example` with all configuration options
- Credential verification scripts in `scripts/` directory
- Docker setup: `Dockerfile` and `docker-compose.yml`
- Interactive test scripts for manual workflow testing:
  - `00_check_status.py` - Show workflow state
  - `01_drop_timesheet.py` - Create test timesheet
  - `02_send_approval.py` - Send approval email
  - `03_send_invoice.py` - Send invoice with PDF
  - `99_reset.py` - Reset for fresh test
- Virtual environment (venv) setup instructions in CLAUDE.md
- Full implementation of invoice automation service:
  - `src/config.py` - Pydantic settings with environment variables
  - `src/models.py` - WorkflowState, WorkflowData, TimesheetInfo, EmailInfo
  - `src/pdf/` - PDF parsing, merging, and HTML-to-PDF conversion
  - `src/telegram/bot.py` - Interactive bot with inline keyboards and approval flows
  - `src/gmail/` - OAuth auth, email sending, inbox monitoring
  - `src/llm/gemini.py` - Email classification and invoice verification
  - `src/watcher.py` - Folder monitoring with debounce
  - `src/workflow.py` - State machine with persistence
  - `src/main.py` - Main entry point wiring all components

### Changed
- Email monitor now checks threads by ID instead of polling for unread emails
- Approval email formatted as full HTML with headers (From, To, Subject) for PDF
- Expanded WorkflowData model with thread IDs, attachment paths, and timeout tracking
- Added Cancel state transitions for PENDING_INIT_APPROVAL and ALL_DOCS_READY states
- Added WAITING_DOCS timeout handling with 7/14-day reminders
- Added verification steps to all implementation phases
- Specified email monitor error handling (rate limits, network, auth)
- Specified Playwright browser lifecycle management
- Specified Docker volume permissions
- Added Telegram edit flow input validation
- Added event handler concurrency controls (asyncio.Queue)
- Added Gemini API graceful degradation behavior
