# Interactive Test Scripts

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

## Workflow Steps

### 0. Check Status (anytime)
```bash
.venv/Scripts/python scripts/00_check_status.py
```
Shows current workflow state, received documents, thread IDs.

### 1. Drop Timesheet
```bash
.venv/Scripts/python scripts/01_drop_timesheet.py [hours]
```
Creates a test timesheet PDF in `data/incoming/`.
Default: 160 hours.

**Then:** Check Telegram for approval message, click "Approve".

### 2. Send Manager Approval
```bash
.venv/Scripts/python scripts/02_send_approval.py
```
Sends "ok schvalujem" reply to the manager email thread.

**Note:** Service polls every 60 seconds, so wait or check status.

### 3. Send Invoice
```bash
.venv/Scripts/python scripts/03_send_invoice.py
```
Creates an invoice PDF and sends it as reply to accountant thread.

**Then:** Check Telegram for final approval message, click "Approve".

### 99. Reset
```bash
.venv/Scripts/python scripts/99_reset.py
```
Clears state and temp files for a fresh test run.

## Complete Test Flow

```bash
# Start fresh
.venv/Scripts/python scripts/99_reset.py

# Start service
docker-compose up -d

# Step 1: Drop timesheet
.venv/Scripts/python scripts/01_drop_timesheet.py

# >> Telegram: Click "Approve" to send emails

# Step 2 & 3: Send approval and invoice
.venv/Scripts/python scripts/02_send_approval.py
.venv/Scripts/python scripts/03_send_invoice.py

# >> Wait ~60s for service to detect emails
# >> Telegram: Click "Approve" to merge and send final email

# Check status
.venv/Scripts/python scripts/00_check_status.py
```
