**Date:** 2026-01-30
**Subject:** Invoice Automation Service
**Status:** Planning

# Invoice Automation Design

## Overview

A Python service that automates the monthly invoice workflow:
1. Monitor folder for timesheet PDFs
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

**Components:**
- **Folder Watcher** - Monitors incoming folder for new timesheet PDFs
- **Gmail Monitor** - Watches for approval emails and accountant replies
- **Telegram Bot** - Handles approvals via inline buttons, sends status updates
- **Workflow Coordinator** - State machine managing the invoice workflow
- **PDF Parser & Merger** - Extracts data from PDFs, merges final document
- **Email Sender** - Sends emails via Gmail API
- **Gemini LLM** - Fallback classification for ambiguous emails, invoice verification

## Workflow States

```
┌─────────────────┐
│  IDLE           │ ◄───────────────────────────────────────┐
│  (watching)     │                                         │
└────────┬────────┘                                         │
         │ new timesheet PDF                                │
         ▼                                                  │
┌─────────────────┐                                         │
│  PENDING_INIT   │ parse PDF, extract hours & date         │
│  _APPROVAL      │ → Telegram: "Confirm to send?"          │
└────────┬────────┘                                         │
         │ user approves                                    │
         ▼                                                  │
┌─────────────────┐                                         │
│  WAITING_DOCS   │ send both emails                        │
│                 │ → watching for 2 responses              │
│  ┌────────────────────────────────┐                       │
│  │ □ approval (manager)           │                       │
│  │ □ invoice  (accountant)        │                       │
│  └────────────────────────────────┘                       │
└────────┬────────┘                                         │
         │ BOTH received (any order)                        │
         ▼                                                  │
┌─────────────────┐                                         │
│  ALL_DOCS_READY │ merge PDFs                              │
│                 │ → Telegram: "Confirm to send final?"    │
└────────┬────────┘                                         │
         │ user approves                                    │
         ▼                                                  │
┌─────────────────┐                                         │
│  COMPLETE       │ send final email, archive               │
│                 │ → Telegram: "Done!"                     │
└────────┬────────┘                                         │
         └──────────────────────────────────────────────────┘
```

**WAITING_DOCS state** tracks two independent flags:
- `approval_received: bool` - set when manager approval email arrives
- `invoice_received: bool` - set when accountant invoice email arrives

State persisted to JSON file, survives restarts.

## Telegram Interactions

**Inline keyboard buttons for approvals:**

```
┌─────────────────────────────────────────────────┐
│ 📄 New timesheet detected                       │
│                                                 │
│ Month: January 2026                             │
│ Total hours: 160                                │
│ • navrh soft. arch.: 144h                       │
│ • testovanie: 16h                               │
│                                                 │
│ Rate: 10€/h → 1600€                             │
│                                                 │
│ ┌────────┐  ┌────────┐  ┌────────┐              │
│ │✓ Approve│  │✎ Edit │  │✗ Cancel│              │
│ └────────┘  └────────┘  └────────┘              │
└─────────────────────────────────────────────────┘
```

**Edit flow:** Tap Edit → bot asks "Enter total hours:" → reply with number → bot recalculates and shows updated breakdown → Approve/Edit/Cancel again.

**Notifications throughout workflow:**

| Event | Message |
|-------|---------|
| New timesheet detected | Details + Approve/Edit/Cancel buttons |
| User approves initial | "✓ Approved. Sending emails..." |
| Emails sent | "📧 Emails sent..." |
| Approval email received | "✓ Manager approval received" |
| Invoice email received | "✓ Invoice received from accountant" |
| All docs ready | Merge details + Approve/Cancel buttons |
| User approves final | "✓ Sending final email..." |
| Complete | "🎉 Done! Archived to /archive/2026-01/" |

**Error notifications:**

| Error | Message |
|-------|---------|
| PDF parse failed | "⚠️ Could not extract hours from timesheet" |
| Email send failed | "❌ Failed to send email" + Retry/Cancel buttons |
| Unclear approval email | "❓ Received email from manager but couldn't confirm approval" |
| Attachment not invoice | "❓ Received PDF but doesn't look like invoice" |
| Gmail auth expired | "🔑 Gmail authentication expired" |

## Email Detection Logic

### Manager Approval Email

1. Filter: FROM = MANAGER_EMAIL
2. Filter: CC contains INVOICING_DEPT_EMAIL
3. Filter: In reply to our "YourCompany inc. faktura MM/YYYY" thread
4. Check body: fuzzy match against APPROVAL_KEYWORDS
   - If match → approval confirmed
   - If no match → call Gemini LLM: "Is this email approving a timesheet?"
     - If yes → approval confirmed
     - If no/uncertain → Telegram notification for manual check

### Accountant Invoice Email

1. Filter: FROM = ACCOUNTANT_EMAIL
2. Filter: In reply to our "YourCompany inc. - podklady ku vystaveniu faktur MM/YYYY" thread
3. Filter: Has PDF attachment
4. Extract text from PDF
5. Check: contains "faktúra" or "invoice", has invoice number pattern, has total amount
   - If all present → invoice confirmed
   - If uncertain → call Gemini LLM: "Is this an invoice?"
     - If yes → invoice confirmed
     - If no → Telegram notification for manual check

## Email Formats

### Email to Manager + Invoicing (with timesheet)

- **To:** MANAGER_EMAIL, INVOICING_DEPT_EMAIL
- **Subject:** `YourCompany inc. faktura MM/YYYY`
- **Body:** `Ahoj, v prilohe worklog na schvalenie`
- **Attachment:** timesheet PDF

### Email to Accountant (invoice request)

- **To:** ACCOUNTANT_EMAIL
- **Subject:** `YourCompany inc. - podklady ku vystaveniu faktur MM/YYYY`
- **Body:**
  ```
  za {month} prosim takto:
  {total_hours}*{rate}={total} bez DPH

  navrh soft. arch. pre nav. aplikaciu - {hours_arch}h
  testovanie navigačnej apl. počas jazdy - 16h
  ```

### Final Email (merged PDF)

- **Reply to:** Manager's approval email thread
- **Body:** `V prílohe.`
- **Attachment:** merged PDF (invoice + timesheet + approval)

## Invoice Items Calculation

Fixed formula based on extracted total hours:
- Line 1: "navrh soft. arch. pre nav. aplikaciu - **X**h" where X = total - 16
- Line 2: "testovanie navigačnej apl. počas jazdy - **16h**" (fixed)

Total hours extracted from Jira timesheet PDF (date range format: "01/Jan/26 - 31/Jan/26").

## PDF Merge Order

1. **Invoice** (from accountant)
2. **Timesheet** (exported from Jira)
3. **Approval email** (converted to PDF via HTML rendering)

## Configuration

All settings via environment variables:

```env
# Folders
WATCH_FOLDER=/data/invoices/incoming
ARCHIVE_FOLDER=/data/invoices/archive

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

## Project Structure

```
invoice-automation/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
├── src/
│   ├── __init__.py
│   ├── main.py                 # Entry point, starts all components
│   ├── config.py               # Load & validate env vars
│   ├── workflow.py             # State machine, persistence
│   ├── watcher.py              # Folder monitoring
│   ├── gmail/
│   │   ├── __init__.py
│   │   ├── auth.py             # OAuth flow
│   │   ├── monitor.py          # Watch for incoming emails
│   │   └── sender.py           # Send emails
│   ├── telegram/
│   │   ├── __init__.py
│   │   └── bot.py              # Bot, inline keyboards, callbacks
│   ├── pdf/
│   │   ├── __init__.py
│   │   ├── parser.py           # Extract hours, dates from timesheet
│   │   ├── merger.py           # Merge 3 PDFs
│   │   └── html_to_pdf.py      # Convert approval email to PDF
│   ├── llm/
│   │   ├── __init__.py
│   │   └── gemini.py           # Gemini API wrapper
│   └── models.py               # Data classes (WorkflowState, etc.)
├── data/
│   └── state.json              # Persisted workflow state
└── config/
    ├── credentials.json        # Gmail OAuth credentials (gitignored)
    └── token.json              # Gmail refresh token (gitignored)
```

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

## Docker Setup

**Dockerfile:**
```dockerfile
FROM python:3.12-slim

# Install Playwright dependencies for HTML→PDF
RUN apt-get update && apt-get install -y \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxrandr2 libgbm1 libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

COPY src/ ./src/

CMD ["python", "-m", "src.main"]
```

**docker-compose.yml:**
```yaml
services:
  invoice-automation:
    build: .
    env_file: .env
    volumes:
      - ./data:/app/data
      - ./config:/app/config
      - ${WATCH_FOLDER}:/watch:ro
      - ${ARCHIVE_FOLDER}:/archive
    restart: unless-stopped
```

## Testing Strategy

### Test Configuration

```env
# .env.test
WATCH_FOLDER=/tmp/test-invoices/incoming
ARCHIVE_FOLDER=/tmp/test-invoices/archive

# Test Gmail account (separate from production)
GMAIL_CREDENTIALS_FILE=/config/test-credentials.json
GMAIL_TOKEN_FILE=/config/test-token.json

# Separate Telegram bot for tests
TELEGRAM_BOT_TOKEN=test-bot-token
TELEGRAM_CHAT_ID=your-test-chat-id

# Test email addresses using Gmail aliases
MANAGER_EMAIL=yourname+manager@gmail.com
INVOICING_DEPT_EMAIL=yourname+invoicing@gmail.com
ACCOUNTANT_EMAIL=yourname+accountant@gmail.com

# Flag to enable test mode behaviors
TEST_MODE=true
```

Gmail aliases (`yourname+anything@gmail.com`) all route to your inbox but can be filtered/identified by alias.

### Test Structure

```
tests/
├── conftest.py              # Pytest fixtures, test config loader
├── fixtures/
│   ├── timesheet_sample.pdf # Real Jira export sample
│   ├── invoice_sample.pdf   # Sample invoice PDF
│   └── emails/              # Sample email HTML content
├── unit/
│   ├── test_pdf_parser.py   # Extract hours, dates
│   ├── test_email_matcher.py # Detection logic
│   └── test_workflow.py     # State transitions
├── integration/
│   ├── automated/           # Fully automated
│   │   ├── test_gmail_send.py
│   │   ├── test_gmail_receive.py
│   │   ├── test_telegram_bot.py
│   │   └── test_full_workflow.py
│   └── interactive/         # Human-in-the-loop
│       ├── run_interactive.py
│       └── scenarios/
│           ├── happy_path.yaml
│           ├── edit_hours.yaml
│           └── error_recovery.yaml
└── mocks/
    ├── gmail_mock.py
    └── telegram_mock.py
```

### Automated Integration Tests

- Uses Gmail aliases, test Telegram chat
- Simulates button presses programmatically via Telegram API
- Sends/receives real emails but automated end-to-end
- Runs without human interaction
- Each test run uses unique subject prefix: `[TEST-abc123] YourCompany inc. faktura...`
- Cleanup after tests: delete test emails, clear test folders

### Interactive Integration Tests

Human-in-the-loop for validating UX and real-world feel:

```
$ python -m tests.integration.interactive.run_interactive happy_path

🧪 Interactive Test: Happy Path
================================
Step 1: Dropping test timesheet to watch folder...
        → Check Telegram for notification
        → Press Approve when ready
        [Press Enter to continue]

Step 2: Emails sent. Check your inbox for:
        • yourname+manager@gmail.com - approval request
        • yourname+accountant@gmail.com - invoice request
        → Reply as manager (just say "ok schvalujem")
        [Press Enter when done]

Step 3: Send invoice reply from accountant...
        → Reply to invoice request with attached PDF
        [Press Enter when done]

...
```

## Deployment

**Development:** docker-compose on Windows

**Production:** Docker on Debian homelab, managed by Komodo

## Error Handling

- All errors → Telegram notification
- Stay in current state, wait for manual intervention
- No auto-retry (explicit user control)
- State persisted, survives service restarts
