# Testing

## Testing the Workflow

The easiest way to test the full workflow is via the **Telegram debug menu**.

Set `TELEGRAM_DEBUG_MENU=true` in your `.env` or `docker-compose.yml`, then restart the service. The bot will show a persistent keyboard with test actions:

| Button | Action |
|---|---|
| 📊 Status | Show current workflow state, received documents, thread IDs |
| 📄 Drop Test PDF | Create a test timesheet PDF (160h) in the watch folder |
| ✉️ Send Approval | Send a simulated manager approval reply to the email thread |
| 📨 Send Invoice | Create and send a simulated invoice reply to the accountant thread |
| 🔄 Reset | Clear state and temp files for a fresh test run |

### Complete Test Flow

1. Reset state (🔄 Reset)
2. Drop a test timesheet (📄 Drop Test PDF)
3. Approve the initial emails in Telegram (click "Approve" on the inline keyboard)
4. Send simulated approval (✉️ Send Approval)
5. Send simulated invoice (📨 Send Invoice)
6. Wait ~60s for email polling to detect them
7. Approve the final merge in Telegram (click "Approve" on the inline keyboard)
8. Check status (📊 Status) to confirm COMPLETE

## Credential Verification Scripts

Quick scripts to verify external service connectivity:

```bash
.venv/Scripts/python scripts/test_gmail.py      # Gmail OAuth flow + token
.venv/Scripts/python scripts/test_telegram.py    # Telegram bot token + test message
.venv/Scripts/python scripts/test_gemini.py      # Gemini API key
.venv/Scripts/python scripts/test_llm.py         # LLM via configured provider
```

## CLI Test Scripts

The same test actions are also available as standalone scripts, useful for automation or when you prefer the command line:

```bash
.venv/Scripts/python scripts/00_check_status.py          # Show workflow state
.venv/Scripts/python scripts/01_drop_timesheet.py [hours] # Create test PDF (default: 160h)
.venv/Scripts/python scripts/02_send_approval.py          # Send manager approval reply
.venv/Scripts/python scripts/03_send_invoice.py           # Send invoice reply
.venv/Scripts/python scripts/99_reset.py                  # Reset state
```

## Prerequisites

1. Service running via Docker Compose:
   ```bash
   docker-compose up -d
   ```

2. Virtual environment (for running scripts locally):
   ```bash
   .venv/Scripts/python <script>  # Windows
   .venv/bin/python <script>      # Linux/Mac
   ```
