# Plan: Telegram Persistent Debug Keyboard

## Overview

Add a `ReplyKeyboardMarkup` with `is_persistent=True` to the Telegram bot, with handlers for each debug action. Port logic from `scripts/*.py` into the bot module.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    TelegramBot                              │
├─────────────────────────────────────────────────────────────┤
│  Existing:                                                  │
│  - Inline keyboards for approvals (keep as-is)              │
│  - /reset command handler + _reset_handler callback         │
│                                                             │
│  New:                                                       │
│  - Persistent ReplyKeyboard (debug menu)                    │
│  - MessageHandler routes debug button text                  │
│  - Debug action methods with state validation               │
└─────────────────────────────────────────────────────────────┘
```

## Implementation Steps

### Step 1: Add Debug Keyboard Definition

In `src/telegram/bot.py`, add imports and keyboard markup:

```python
from telegram import ReplyKeyboardMarkup, KeyboardButton

DEBUG_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📊 Status"), KeyboardButton("📄 Drop Test PDF")],
        [KeyboardButton("✅ Send Approval"), KeyboardButton("💰 Send Invoice")],
        [KeyboardButton("🔄 Reset")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)
```

**Verification:** Import statement compiles, keyboard constant defined.

---

### Step 2: Add Debug Button Text Constants

```python
class DebugButton(str, Enum):
    """Debug keyboard button labels."""
    STATUS = "📊 Status"
    DROP_PDF = "📄 Drop Test PDF"
    SEND_APPROVAL = "✅ Send Approval"
    SEND_INVOICE = "💰 Send Invoice"
    RESET = "🔄 Reset"
```

**Verification:** Enum values match keyboard button text exactly.

---

### Step 3: Send Startup Message with Keyboard

In `initialize()`, send a startup message that activates the keyboard:

```python
async def initialize(self) -> None:
    # ... existing init code ...

    # Send startup message with debug keyboard
    await self._app.bot.send_message(
        chat_id=self._chat_id,
        text="🤖 Bot started. Debug menu active.",
        reply_markup=DEBUG_KEYBOARD,
    )
    logger.info("Telegram bot initialized with debug keyboard")
```

**Verification:** Bot startup shows message in Telegram, keyboard appears at bottom.

---

### Step 4: Modify Text Message Handler

Update `_handle_text_message` to route debug buttons BEFORE edit mode check:

```python
async def _handle_text_message(
    self,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()

    # Debug buttons (check before edit mode)
    if text == DebugButton.STATUS.value:
        await self._handle_debug_status()
        return
    elif text == DebugButton.DROP_PDF.value:
        await self._handle_debug_drop_pdf()
        return
    elif text == DebugButton.SEND_APPROVAL.value:
        await self._handle_debug_send_approval()
        return
    elif text == DebugButton.SEND_INVOICE.value:
        await self._handle_debug_send_invoice()
        return
    elif text == DebugButton.RESET.value:
        await self._handle_debug_reset()
        return

    # Existing edit mode handling below...
    if not self._edit_mode:
        return
    # ...
```

**Verification:** Each button press triggers correct handler, edit mode still works.

---

### Step 5: Implement Debug Handlers

#### 5a: Status Handler

```python
async def _handle_debug_status(self) -> None:
    """Show current workflow status."""
    from src.workflow import STATE_FILE  # Import constant, not hardcode

    logger.debug("Debug: status requested")

    try:
        if not STATE_FILE.exists():
            await self.send_message("*Status:* IDLE (no state file)")
            return

        import json
        state = json.loads(STATE_FILE.read_text())

        status_lines = [
            f"*Status:* {state.get('state', 'unknown')}",
            "",
        ]

        if state.get("timesheet_info"):
            info = state["timesheet_info"]
            status_lines.append(f"Timesheet: {info.get('total_hours', '?')}h ({info.get('month', '?')}/{info.get('year', '?')})")
        else:
            status_lines.append("Timesheet: Not detected")

        status_lines.append(f"Approval: {'✅' if state.get('approval_received') else '⏳'}")
        status_lines.append(f"Invoice: {'✅' if state.get('invoice_received') else '⏳'}")

        if state.get("manager_thread_id"):
            status_lines.append(f"\nManager thread: `{state['manager_thread_id']}`")
        if state.get("accountant_thread_id"):
            status_lines.append(f"Accountant thread: `{state['accountant_thread_id']}`")

        await self.send_message("\n".join(status_lines))

    except Exception as e:
        logger.exception("Debug status failed")
        await self.send_message(f"*Error reading status:* {e}")
```

**Verification:** Shows correct state info, handles missing file gracefully.

---

#### 5b: Drop PDF Handler

```python
async def _handle_debug_drop_pdf(self) -> None:
    """Create and drop a test timesheet PDF (160h default)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from src.config import settings

    logger.debug("Debug: drop PDF requested")

    total_hours = 160  # Fixed default for debug

    try:
        output_path = settings.watch_folder / "timesheet_test.pdf"
        settings.watch_folder.mkdir(parents=True, exist_ok=True)

        # Create test PDF
        c = canvas.Canvas(str(output_path), pagesize=A4)
        width, height = A4

        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, height - 50, "Jira Timesheet Export")

        c.setFont("Helvetica", 12)
        c.drawString(50, height - 80, "Period: 01/Jan/26 - 31/Jan/26")
        c.drawString(50, height - 110, "Project: YourCompany inc. Navigation App")

        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, height - 160, f"Total: {total_hours}h")

        c.save()

        await self.send_message(f"📄 Test PDF created: `{output_path.name}`\n\nWatcher should detect it shortly.")
        logger.info(f"Debug: created test PDF at {output_path}")

    except Exception as e:
        logger.exception("Debug drop PDF failed")
        await self.send_message(f"*Error creating PDF:* {e}")
```

**Verification:** PDF created in watch folder, watcher detects it, approval message appears.

---

#### 5c: Send Approval Handler

```python
async def _handle_debug_send_approval(self) -> None:
    """Send approval email to manager thread (for testing)."""
    import asyncio
    import base64
    import json
    from email.mime.text import MIMEText
    from src.workflow import STATE_FILE
    from src.gmail.auth import get_gmail_service
    from src.config import settings

    logger.debug("Debug: send approval requested")

    try:
        # Validate state
        if not STATE_FILE.exists():
            await self.send_message("*Error:* No state file. Start workflow first.")
            return

        state = json.loads(STATE_FILE.read_text())

        if state.get("state") != "WAITING_DOCS":
            await self.send_message(f"*Error:* Not in WAITING_DOCS state (current: {state.get('state')})")
            return

        thread_id = state.get("manager_thread_id")
        if not thread_id:
            await self.send_message("*Error:* No manager thread ID. Emails not sent yet?")
            return

        if state.get("approval_received"):
            await self.send_message("*Note:* Approval already received.")
            return

        await self.send_message("📧 Sending approval reply...")

        # Get Gmail service (sync call, wrap in thread)
        service = await asyncio.to_thread(get_gmail_service)

        # Get original message to reply to
        thread = await asyncio.to_thread(
            lambda: service.users().threads().get(userId="me", id=thread_id).execute()
        )
        messages = thread.get("messages", [])
        if not messages:
            await self.send_message("*Error:* No messages in thread.")
            return

        original_msg = messages[0]
        headers = {h["name"]: h["value"] for h in original_msg["payload"]["headers"]}
        subject = headers.get("Subject", "")
        message_id = headers.get("Message-ID", "")

        # Create reply (self-test: from and to are same account)
        reply = MIMEText("ok schvalujem\n\nS pozdravom,\nManager")
        reply["To"] = settings.from_email
        reply["From"] = settings.from_email
        reply["Subject"] = f"Re: {subject}" if not subject.startswith("Re:") else subject
        reply["In-Reply-To"] = message_id
        reply["References"] = message_id

        raw = base64.urlsafe_b64encode(reply.as_bytes()).decode()
        await asyncio.to_thread(
            lambda: service.users().messages().send(
                userId="me",
                body={"raw": raw, "threadId": thread_id}
            ).execute()
        )

        await self.send_message("✅ Approval reply sent!\n\nMonitor should detect it within ~60s.")
        logger.info("Debug: sent approval reply")

    except Exception as e:
        logger.exception("Debug send approval failed")
        await self.send_message(f"*Error sending approval:* {e}")
```

**Verification:** Only works in WAITING_DOCS state, sends email, monitor detects it.

---

#### 5d: Send Invoice Handler

```python
async def _handle_debug_send_invoice(self) -> None:
    """Send invoice email with PDF attachment (for testing)."""
    import asyncio
    import base64
    import json
    from email.mime.application import MIMEApplication
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from pathlib import Path
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from src.workflow import STATE_FILE
    from src.gmail.auth import get_gmail_service
    from src.config import settings

    logger.debug("Debug: send invoice requested")

    try:
        # Validate state
        if not STATE_FILE.exists():
            await self.send_message("*Error:* No state file. Start workflow first.")
            return

        state = json.loads(STATE_FILE.read_text())

        if state.get("state") != "WAITING_DOCS":
            await self.send_message(f"*Error:* Not in WAITING_DOCS state (current: {state.get('state')})")
            return

        thread_id = state.get("accountant_thread_id")
        if not thread_id:
            await self.send_message("*Error:* No accountant thread ID. Emails not sent yet?")
            return

        if state.get("invoice_received"):
            await self.send_message("*Note:* Invoice already received.")
            return

        await self.send_message("📧 Creating and sending invoice...")

        # Create invoice PDF
        timesheet_info = state.get("timesheet_info", {})
        hours = timesheet_info.get("total_hours", 160)
        rate = settings.hourly_rate
        total = hours * rate

        invoice_path = Path("data/temp/test_invoice.pdf")
        invoice_path.parent.mkdir(parents=True, exist_ok=True)

        c = canvas.Canvas(str(invoice_path), pagesize=A4)
        width, height = A4
        c.setFont("Helvetica-Bold", 20)
        c.drawString(50, height - 50, "INVOICE")
        c.setFont("Helvetica", 12)
        c.drawString(50, height - 90, "Invoice #: 2026-001")
        c.drawString(50, height - 150, f"Hours: {hours}")
        c.drawString(50, height - 170, f"Rate: {rate} EUR/h")
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, height - 210, f"Total: {total} EUR")
        c.save()

        # Get Gmail service
        service = await asyncio.to_thread(get_gmail_service)

        # Get original message
        thread = await asyncio.to_thread(
            lambda: service.users().threads().get(userId="me", id=thread_id).execute()
        )
        messages = thread.get("messages", [])
        if not messages:
            await self.send_message("*Error:* No messages in thread.")
            return

        original_msg = messages[0]
        headers = {h["name"]: h["value"] for h in original_msg["payload"]["headers"]}
        subject = headers.get("Subject", "")
        message_id = headers.get("Message-ID", "")

        # Create reply with attachment
        msg = MIMEMultipart()
        msg["To"] = settings.from_email
        msg["From"] = settings.from_email
        msg["Subject"] = f"Re: {subject}" if not subject.startswith("Re:") else subject
        msg["In-Reply-To"] = message_id
        msg["References"] = message_id

        msg.attach(MIMEText("V prilohe faktura.\n\nS pozdravom,\nAccountant"))

        with open(invoice_path, "rb") as f:
            attachment = MIMEApplication(f.read(), _subtype="pdf")
            attachment.add_header("Content-Disposition", "attachment", filename="faktura_2026_01.pdf")
            msg.attach(attachment)

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        await asyncio.to_thread(
            lambda: service.users().messages().send(
                userId="me",
                body={"raw": raw, "threadId": thread_id}
            ).execute()
        )

        await self.send_message("✅ Invoice reply sent!\n\nMonitor should detect it within ~60s.")
        logger.info("Debug: sent invoice reply")

    except Exception as e:
        logger.exception("Debug send invoice failed")
        await self.send_message(f"*Error sending invoice:* {e}")
```

**Verification:** Only works in WAITING_DOCS state, creates PDF, sends email, monitor detects it.

---

#### 5e: Reset Handler

```python
async def _handle_debug_reset(self) -> None:
    """Reset workflow via existing reset handler."""
    logger.debug("Debug: reset requested")

    if self._reset_handler:
        await self._reset_handler()
        await self.send_message("🔄 Workflow reset. Drop a new timesheet to start.")
    else:
        await self.send_message("*Error:* Reset handler not configured.")
```

**Verification:** Reuses existing `_reset_handler` from workflow coordinator, no duplicated logic.

---

### Step 6: Add reportlab Dependency

Add to `requirements.txt`:

```
# PDF generation (debug tools)
reportlab>=4.0
```

**Verification:** `pip install -r requirements.txt` succeeds, Docker build succeeds.

---

## File Changes

| File | Change |
|------|--------|
| `src/telegram/bot.py` | Add keyboard, DebugButton enum, 5 handlers, modify text handler |
| `requirements.txt` | Add `reportlab>=4.0` |

## Testing

1. **Startup**: Bot shows "Bot started" message, keyboard visible at bottom
2. **Status button**: Shows correct state, handles no-state gracefully
3. **Drop PDF**: Creates file in watch folder, watcher triggers workflow
4. **Send Approval**:
   - Error if not in WAITING_DOCS
   - Sends email, monitor detects within 60s
5. **Send Invoice**:
   - Error if not in WAITING_DOCS
   - Creates PDF, sends email with attachment, monitor detects
6. **Reset**: Clears state, confirms in chat
7. **Edit mode**: Still works for hour editing (no regression)
8. **Docker**: All above works in container

## Rollback

If issues arise:
1. Remove debug handlers from `_handle_text_message`
2. Remove startup message with keyboard
3. Core workflow unaffected (debug is additive only)

## Scope

- ~250 lines of new code (increased due to proper error handling)
- Single file primary change + requirements.txt
- Low risk - all debug code is additive, doesn't modify core workflow
