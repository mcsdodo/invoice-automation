# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Python service that automates the monthly invoice workflow:
1. Monitor folder for timesheet PDFs (Jira exports)
2. Send emails (to manager+invoicing, to accountant) with Telegram approval
3. Watch for approval email and invoice response (parallel)
4. Merge 3 PDFs in order: invoice → timesheet → approval
5. Send final merged PDF with Telegram approval
6. Archive all files

All steps traced in Telegram with inline button approvals.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Invoice Automation Service                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   Folder     │    │    Gmail     │    │   Telegram   │      │
│  │   Watcher    │    │   Monitor    │    │     Bot      │      │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘      │
│         │                   │                   │               │
│         └───────────────────┼───────────────────┘               │
│                             ▼                                   │
│                    ┌────────────────┐                           │
│                    │   Workflow     │                           │
│                    │   Coordinator  │                           │
│                    └────────┬───────┘                           │
│                             │                                   │
│         ┌───────────────────┼───────────────────┐               │
│         ▼                   ▼                   ▼               │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │  PDF Parser  │    │    Email     │    │   Gemini     │      │
│  │  & Merger    │    │   Sender     │    │   LLM        │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Watch Source

Google Drive is the default watch source (`WATCH_SOURCE=gdrive`), configured to poll `_documents_intake/techlab/invoicing_automation`. It reuses the Gmail OAuth client with the added `drive` scope (one-time re-consent required on first run). Processed files are automatically moved to `processed/` and `errors/` subfolders in Drive, with deduplication tracking stored in `data/gdrive.db` (SQLite). For local folder watching, set `WATCH_SOURCE=local` to use the original folder watcher implementation.

A stuck `in_progress` row (e.g. from a process crash mid-workflow) can be cleared with the Telegram `/reset` command.

## Tech Stack

- **Runtime:** Python 3.12, asyncio
- **Folder monitoring:** watchdog
- **Gmail:** google-api-python-client, google-auth-oauthlib
- **Telegram:** python-telegram-bot (with inline keyboards)
- **PDF parsing:** pdfplumber
- **PDF merging:** pypdf
- **HTML to PDF:** playwright (headless Chromium)
- **LLM:** google-generativeai (Gemini 2.5 Flash Lite)
- **Config/models:** pydantic
- **Container:** Docker, docker-compose

## Project Structure

```
invoice-automation/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
├── CLAUDE.md                # This file
├── _tasks/                  # Task planning folder
│   ├── CLAUDE.md            # Task planning conventions
│   └── _TECH_DEBT/          # Tech debt tracking
│       └── CLAUDE.md        # Tech debt guidelines
├── src/
│   ├── __init__.py
│   ├── main.py              # Entry point, starts all components
│   ├── config.py            # Load & validate env vars
│   ├── workflow.py          # State machine, persistence
│   ├── watcher.py           # Folder monitoring
│   ├── gmail/
│   │   ├── __init__.py
│   │   ├── auth.py          # OAuth flow
│   │   ├── monitor.py       # Watch for incoming emails
│   │   └── sender.py        # Send emails
│   ├── telegram/
│   │   ├── __init__.py
│   │   └── bot.py           # Bot, inline keyboards, callbacks
│   ├── pdf/
│   │   ├── __init__.py
│   │   ├── parser.py        # Extract hours, dates from timesheet
│   │   ├── merger.py        # Merge 3 PDFs
│   │   └── html_to_pdf.py   # Convert approval email to PDF
│   ├── llm/
│   │   ├── __init__.py
│   │   └── gemini.py        # Gemini API wrapper
│   └── models.py            # Data classes (WorkflowState, etc.)
├── data/
│   └── state.json           # Persisted workflow state
├── config/
│   ├── credentials.json     # Gmail OAuth credentials (gitignored)
│   └── token.json           # Gmail refresh token (gitignored)
├── scripts/
│   ├── test_gemini.py       # Verify Gemini API credentials
│   ├── test_gmail.py        # Verify Gmail OAuth (creates token.json)
│   └── test_telegram.py     # Verify Telegram bot credentials
└── tests/
    ├── conftest.py
    ├── fixtures/
    ├── unit/
    ├── integration/
    └── mocks/
```

## Common Development Commands

### Running Locally

```bash
# Start with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f invoice-automation

# Rebuild after code changes
docker-compose build && docker-compose up -d

# Stop
docker-compose down
```

### Local Development (venv)

**Always use the virtual environment** - never install packages globally.

```bash
# Create virtual environment (first time only)
python -m venv .venv

# Install dependencies
.venv/Scripts/pip install -r requirements.txt   # Windows
.venv/bin/pip install -r requirements.txt       # Linux/Mac

# Run scripts
.venv/Scripts/python scripts/test_gmail.py      # Windows
.venv/bin/python scripts/test_gmail.py          # Linux/Mac

# Run main app
.venv/Scripts/python -m src.main                # Windows

# Install playwright browsers (for HTML→PDF)
.venv/Scripts/playwright install chromium       # Windows
```

### Testing

```bash
# Run all tests
.venv/Scripts/python -m pytest -v

# Run unit tests only
.venv/Scripts/python -m pytest tests/unit/ -v

# Run with coverage
.venv/Scripts/python -m pytest --cov=src --cov-report=term-missing
```

## Environment Variables

All settings via environment variables (see [.env.example](./.env.example)):

```env
# Folders
WATCH_FOLDER=/data/invoices/incoming
ARCHIVE_FOLDER=/data/invoices/archive

# Watch source
WATCH_SOURCE=gdrive
GDRIVE_WATCH_PATH=_documents_intake/techlab/invoicing_automation
GDRIVE_POLL_INTERVAL_SECONDS=30
GDRIVE_DB_PATH=/app/data/gdrive.db
GDRIVE_PROCESSED_SUBFOLDER=processed
GDRIVE_ERRORS_SUBFOLDER=errors

# Gmail OAuth
GMAIL_CREDENTIALS_FILE=/config/credentials.json
GMAIL_TOKEN_FILE=/config/token.json

# Telegram
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=987654321

# Email addresses
MANAGER_EMAIL=manager@company.com
INVOICING_DEPT_EMAIL=invoicing@company.com
ACCOUNTANT_EMAIL=accountant@example.com

# Invoice settings
HOURLY_RATE=10
CURRENCY=€

# LLM
GEMINI_API_KEY=AIza...

# Matching rules
APPROVAL_KEYWORDS=approved,schválené,súhlasím,ok
```

## Workflow States

```
IDLE → PENDING_INIT_APPROVAL → WAITING_DOCS → ALL_DOCS_READY → COMPLETE
         (user approves)      (parallel wait)   (user approves)
```

- **IDLE**: Watching for new timesheet PDFs
- **PENDING_INIT_APPROVAL**: PDF parsed, waiting for Telegram approval to send emails
- **WAITING_DOCS**: Both emails sent, waiting for manager approval AND accountant invoice
- **ALL_DOCS_READY**: Both docs received, waiting for Telegram approval to send final
- **COMPLETE**: Final email sent, files archived

State persisted to `data/state.json`, survives restarts.

## Key Implementation Details

### Invoice Items Calculation

Fixed formula based on extracted total hours:
- Line 1: "navrh soft. arch. pre nav. aplikaciu - **X**h" where X = total - 16
- Line 2: "testovanie navigačnej apl. počas jazdy - **16h**" (fixed)

### PDF Merge Order

1. Invoice (from accountant)
2. Timesheet (exported from Jira)
3. Approval email (converted to PDF via HTML rendering)

### Email Detection

- **Manager approval**: FROM=MANAGER_EMAIL, CC contains INVOICING, fuzzy keyword match or LLM fallback
- **Accountant invoice**: FROM=ACCOUNTANT_EMAIL, has PDF attachment, invoice pattern match or LLM fallback

## Code Conventions

### Python Style

- Use type hints everywhere
- Pydantic for configuration and data models
- Async/await for all I/O operations
- Structured logging with context

### Error Handling

- All errors → Telegram notification
- Stay in current state, wait for manual intervention
- No auto-retry (explicit user control)
- State persisted, survives service restarts

### Testing

- Unit tests for pure logic (PDF parsing, email matching, state transitions)
- Integration tests with Gmail aliases for real email flow
- Interactive tests for human-in-the-loop validation

## File Encoding Standards

**CRITICAL**: This project runs on Linux containers. All files MUST use Unix line endings (LF, not CRLF).

## Windows Development Environment

When running Docker commands on Windows (Git Bash/MSYS), prefix with `MSYS_NO_PATHCONV=1` to disable path conversion:

```bash
MSYS_NO_PATHCONV=1 docker run --rm --entrypoint cat myimage:latest /app/config.yaml
```

## Deployment

- **Development:** docker-compose on Windows
- **Production:** Docker on Debian homelab, managed by Komodo

## Task Planning Folder (`_tasks/`)

> **🚨 PLAN MODE**: When in plan mode, **ALWAYS save plans to `_tasks/{NN}-{name}/`**, NOT `.claude/plans/`. Check existing folders for next number.

Complex features and multi-session work go in `_tasks/`. See [`_tasks/CLAUDE.md`](_tasks/CLAUDE.md) for detailed conventions (folder structure, file naming, lifecycle).

### Quick Reference

```
_tasks/
├── CLAUDE.md                    # Conventions for task planning
├── {NN}-{task-name}/            # Individual task folders (01-, 02-, etc.)
│   ├── 01-task.md               # Task description and requirements
│   ├── 02-plan.md               # Implementation plan
│   └── 03-*.md                  # Additional docs (design, notes, etc.)
├── _done/                       # Completed tasks (moved here, keep numbers)
└── _TECH_DEBT/                  # Tech debt tracking
    └── CLAUDE.md                # Tech debt guidelines
```

**When to use `_tasks/`:**
- Multi-step features requiring planning
- Work spanning multiple sessions
- Tasks needing design discussion before implementation

## Documentation

- **Design document:** `_tasks/01-invoice-automation/01-design.md`
- **Task planning:** `_tasks/` folder for complex features
- Keep this CLAUDE.md in sync with code changes
- Update design doc if workflow or architecture changes
