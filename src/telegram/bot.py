"""Telegram bot for invoice automation notifications and approvals."""

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Coroutine

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.config import settings
from src.models import TimesheetInfo

logger = logging.getLogger(__name__)


class ApprovalAction(str, Enum):
    """Actions that can result from approval interactions."""

    APPROVE = "approve"
    CANCEL = "cancel"
    EDIT = "edit"


class CallbackData(str, Enum):
    """Callback data identifiers for inline buttons."""

    TIMESHEET_APPROVE = "ts_approve"
    TIMESHEET_EDIT = "ts_edit"
    TIMESHEET_CANCEL = "ts_cancel"
    DOCS_APPROVE = "docs_approve"
    DOCS_CANCEL = "docs_cancel"
    ERROR_RETRY = "error_retry"


class DebugButton(str, Enum):
    """Debug keyboard button labels."""

    STATUS = "📊 Status"
    DROP_PDF = "📄 Drop Test PDF"
    SEND_APPROVAL = "✅ Send Approval"
    SEND_INVOICE = "💰 Send Invoice"
    RESET = "🔄 Reset"


# Persistent debug keyboard
DEBUG_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton(DebugButton.STATUS.value), KeyboardButton(DebugButton.DROP_PDF.value)],
        [KeyboardButton(DebugButton.SEND_APPROVAL.value), KeyboardButton(DebugButton.SEND_INVOICE.value)],
        [KeyboardButton(DebugButton.RESET.value)],
    ],
    resize_keyboard=True,
    is_persistent=True,
)


@dataclass
class ApprovalResult:
    """Result of an approval interaction."""

    action: ApprovalAction
    edited_hours: int | None = None


# Type alias for callback handlers
CallbackHandler = Callable[[ApprovalResult], Coroutine[Any, Any, None]]


class TelegramBot:
    """Telegram bot for sending notifications and handling approvals."""

    def __init__(self) -> None:
        """Initialize the Telegram bot."""
        self._app: Application | None = None
        self._chat_id: int = settings.telegram_chat_id
        self._callback_handler: CallbackHandler | None = None
        self._reset_handler: Callable[[], Coroutine[Any, Any, None]] | None = None
        self._edit_mode: bool = False
        self._edit_timeout_task: asyncio.Task | None = None
        self._pending_edit_message_id: int | None = None
        self._original_timesheet_info: TimesheetInfo | None = None
        self._original_total_amount: float | None = None

    async def initialize(self) -> None:
        """Initialize and start the bot application."""
        self._app = (
            Application.builder()
            .token(settings.telegram_bot_token)
            .build()
        )

        # Add handlers
        self._app.add_handler(CommandHandler("reset", self._handle_reset_command))
        self._app.add_handler(CallbackQueryHandler(self._handle_callback))
        self._app.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self._handle_text_message,
            )
        )

        # Error handler
        async def error_handler(update, context):
            logger.error(f"Telegram error: {context.error}", exc_info=context.error)
        self._app.add_error_handler(error_handler)

        # Initialize the application
        await self._app.initialize()
        await self._app.start()

        # Start polling in background
        await self._app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

        # Send startup message (with debug keyboard if enabled)
        if settings.telegram_debug_menu:
            await self._app.bot.send_message(
                chat_id=self._chat_id,
                text="🤖 Bot started. Debug menu active.",
                reply_markup=DEBUG_KEYBOARD,
            )
            logger.info("Telegram bot initialized with debug keyboard")
        else:
            await self._app.bot.send_message(
                chat_id=self._chat_id,
                text="🤖 Bot started.",
                reply_markup=ReplyKeyboardRemove(),
            )
            logger.info("Telegram bot initialized")

    async def shutdown(self) -> None:
        """Shutdown the bot gracefully."""
        if self._edit_timeout_task and not self._edit_timeout_task.done():
            self._edit_timeout_task.cancel()
            try:
                await self._edit_timeout_task
            except asyncio.CancelledError:
                pass

        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            logger.info("Telegram bot shutdown complete")

    def set_callback_handler(self, handler: CallbackHandler) -> None:
        """Set the callback handler for approval results.

        Args:
            handler: Async function to call with ApprovalResult
        """
        self._callback_handler = handler

    def set_reset_handler(self, handler: Callable[[], Coroutine[Any, Any, None]]) -> None:
        """Set the handler for /reset command."""
        self._reset_handler = handler

    async def _handle_reset_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /reset command."""
        if update.effective_chat.id != self._chat_id:
            return

        if self._reset_handler:
            await self._reset_handler()
            await self.send_message("🔄 Workflow reset. Drop a new timesheet to start.")
        else:
            await self.send_message("❌ Reset handler not configured.")

    async def send_message(self, text: str) -> int:
        """Send a text message to the configured chat.

        Args:
            text: Message text (supports Markdown formatting)

        Returns:
            Message ID of the sent message
        """
        if not self._app:
            raise RuntimeError("Bot not initialized. Call initialize() first.")

        message = await self._app.bot.send_message(
            chat_id=self._chat_id,
            text=text,
            parse_mode="Markdown",
        )
        logger.debug(f"Sent message {message.message_id}: {text[:50]}...")
        return message.message_id

    async def send_message_with_buttons(
        self,
        text: str,
        buttons: list[list[tuple[str, str]]],
    ) -> int:
        """Send a message with inline keyboard buttons.

        Args:
            text: Message text (supports Markdown formatting)
            buttons: List of button rows, each row is a list of (label, callback_data) tuples

        Returns:
            Message ID of the sent message
        """
        if not self._app:
            raise RuntimeError("Bot not initialized. Call initialize() first.")

        keyboard = [
            [InlineKeyboardButton(label, callback_data=data) for label, data in row]
            for row in buttons
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        message = await self._app.bot.send_message(
            chat_id=self._chat_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )
        logger.debug(f"Sent message with buttons {message.message_id}: {text[:50]}...")
        return message.message_id

    async def edit_message(self, message_id: int, text: str) -> None:
        """Edit an existing message.

        Args:
            message_id: ID of the message to edit
            text: New message text (supports Markdown formatting)
        """
        if not self._app:
            raise RuntimeError("Bot not initialized. Call initialize() first.")

        await self._app.bot.edit_message_text(
            chat_id=self._chat_id,
            message_id=message_id,
            text=text,
            parse_mode="Markdown",
        )
        logger.debug(f"Edited message {message_id}")

    async def remove_buttons(self, message_id: int) -> None:
        """Remove inline keyboard from an existing message.

        Args:
            message_id: ID of the message to update
        """
        if not self._app:
            raise RuntimeError("Bot not initialized. Call initialize() first.")

        await self._app.bot.edit_message_reply_markup(
            chat_id=self._chat_id,
            message_id=message_id,
            reply_markup=None,
        )
        logger.debug(f"Removed buttons from message {message_id}")

    async def send_timesheet_approval(
        self,
        timesheet_info: TimesheetInfo,
        total_amount: float,
    ) -> int:
        """Send a timesheet approval notification with action buttons.

        Args:
            timesheet_info: Parsed timesheet information
            total_amount: Calculated total invoice amount

        Returns:
            Message ID of the sent message
        """
        self._original_timesheet_info = timesheet_info
        self._original_total_amount = total_amount

        text = self._format_timesheet_message(timesheet_info, total_amount)
        buttons = [
            [
                ("Approve", CallbackData.TIMESHEET_APPROVE.value),
                ("Edit Hours", CallbackData.TIMESHEET_EDIT.value),
                ("Cancel", CallbackData.TIMESHEET_CANCEL.value),
            ]
        ]

        return await self.send_message_with_buttons(text, buttons)

    async def send_docs_ready_approval(self, details: str) -> int:
        """Send notification that all documents are ready for final approval.

        Args:
            details: Summary of the collected documents

        Returns:
            Message ID of the sent message
        """
        text = (
            "*All Documents Ready*\n\n"
            f"{details}\n\n"
            "Ready to merge and send final invoice?"
        )
        buttons = [
            [
                ("Approve", CallbackData.DOCS_APPROVE.value),
                ("Cancel", CallbackData.DOCS_CANCEL.value),
            ]
        ]

        return await self.send_message_with_buttons(text, buttons)

    async def send_error(
        self,
        message: str,
        context: str | None = None,
        retry_callback: str | None = None,
    ) -> int:
        """Send an error notification.

        Args:
            message: Error message
            context: Additional context about the error
            retry_callback: Optional callback data for retry button

        Returns:
            Message ID of the sent message
        """
        text = f"*Error*\n\n{message}"
        if context:
            text += f"\n\n_Context:_ {context}"

        if retry_callback:
            buttons = [[("Retry", retry_callback)]]
            return await self.send_message_with_buttons(text, buttons)
        else:
            return await self.send_message(text)

    def _format_timesheet_message(
        self,
        timesheet_info: TimesheetInfo,
        total_amount: float,
    ) -> str:
        """Format the timesheet approval message.

        Args:
            timesheet_info: Parsed timesheet information
            total_amount: Calculated total amount

        Returns:
            Formatted message text
        """
        return (
            f"*New Timesheet Detected*\n\n"
            f"*Period:* {timesheet_info.date_range}\n"
            f"*Total Hours:* {timesheet_info.total_hours}h\n\n"
            f"*Invoice Breakdown:*\n"
            f"  - Software architecture: {timesheet_info.arch_hours}h\n"
            f"  - Testing: {timesheet_info.test_hours}h\n\n"
            f"*Total Amount:* {total_amount:.2f} {settings.currency}\n\n"
            f"Please approve to send emails to manager and accountant."
        )

    async def _handle_callback(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle inline keyboard button callbacks.

        Args:
            update: Telegram update
            context: Callback context
        """
        query = update.callback_query
        if not query or not query.data:
            return

        # Verify chat ID for security
        if query.message and query.message.chat_id != self._chat_id:
            logger.warning(
                f"Ignoring callback from unauthorized chat: {query.message.chat_id}"
            )
            await query.answer("Unauthorized", show_alert=True)
            return

        await query.answer()

        callback_data = query.data

        if callback_data == CallbackData.TIMESHEET_APPROVE.value:
            await self._handle_timesheet_approve(query.message.message_id)
        elif callback_data == CallbackData.TIMESHEET_EDIT.value:
            await self._handle_timesheet_edit(query.message.message_id)
        elif callback_data == CallbackData.TIMESHEET_CANCEL.value:
            await self._handle_timesheet_cancel(query.message.message_id)
        elif callback_data == CallbackData.DOCS_APPROVE.value:
            await self._handle_docs_approve(query.message.message_id)
        elif callback_data == CallbackData.DOCS_CANCEL.value:
            await self._handle_docs_cancel(query.message.message_id)
        elif callback_data == CallbackData.ERROR_RETRY.value:
            # Error retry is handled by external callback
            if self._callback_handler:
                await self._callback_handler(ApprovalResult(action=ApprovalAction.APPROVE))

    async def _handle_timesheet_approve(self, message_id: int) -> None:
        """Handle timesheet approval button press."""
        await self.edit_message(
            message_id,
            "*Timesheet Approved*\n\nSending emails to manager and accountant...",
        )

        if self._callback_handler:
            await self._callback_handler(ApprovalResult(action=ApprovalAction.APPROVE))

    async def _handle_timesheet_edit(self, message_id: int) -> None:
        """Handle timesheet edit button press - enter edit mode."""
        self._edit_mode = True
        self._pending_edit_message_id = message_id

        await self.edit_message(
            message_id,
            "*Edit Mode*\n\n"
            "Please enter the corrected total hours (1-300).\n\n"
            "_Timeout: 5 minutes_",
        )

        # Start timeout task
        if self._edit_timeout_task and not self._edit_timeout_task.done():
            self._edit_timeout_task.cancel()

        self._edit_timeout_task = asyncio.create_task(self._edit_timeout())

    async def _handle_timesheet_cancel(self, message_id: int) -> None:
        """Handle timesheet cancel button press."""
        await self.edit_message(
            message_id,
            "*Cancelled*\n\nWorkflow cancelled. Timesheet will be archived.",
        )

        if self._callback_handler:
            await self._callback_handler(ApprovalResult(action=ApprovalAction.CANCEL))

    async def _handle_docs_approve(self, message_id: int) -> None:
        """Handle docs ready approval button press."""
        await self.edit_message(
            message_id,
            "*Approved*\n\nMerging documents and sending final invoice...",
        )

        if self._callback_handler:
            await self._callback_handler(ApprovalResult(action=ApprovalAction.APPROVE))

    async def _handle_docs_cancel(self, message_id: int) -> None:
        """Handle docs ready cancel button press."""
        await self.edit_message(
            message_id,
            "*Cancelled*\n\nWorkflow cancelled. All documents will be archived.",
        )

        if self._callback_handler:
            await self._callback_handler(ApprovalResult(action=ApprovalAction.CANCEL))

    async def _handle_text_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle text messages (debug buttons and edit flow).

        Args:
            update: Telegram update
            context: Callback context
        """
        if not update.message or not update.message.text:
            return

        # Security: only process messages from configured chat
        if update.message.chat_id != self._chat_id:
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

        # Only process further if in edit mode
        if not self._edit_mode:
            return

        # Validate input
        try:
            hours = int(text)
            if hours < 1 or hours > 300:
                raise ValueError("Out of range")
        except ValueError:
            await self.send_message(
                "*Invalid Input*\n\n"
                "Please enter a valid number between 1 and 300."
            )
            return

        # Cancel timeout
        if self._edit_timeout_task and not self._edit_timeout_task.done():
            self._edit_timeout_task.cancel()

        self._edit_mode = False

        # Update the original message with new hours
        if self._original_timesheet_info and self._pending_edit_message_id:
            # Create updated timesheet info
            updated_info = TimesheetInfo(
                total_hours=hours,
                date_range=self._original_timesheet_info.date_range,
                month=self._original_timesheet_info.month,
                year=self._original_timesheet_info.year,
            )
            new_amount = hours * settings.hourly_rate

            # Show updated message with buttons again
            text = self._format_timesheet_message(updated_info, new_amount)
            text += "\n\n_Hours updated from "
            text += f"{self._original_timesheet_info.total_hours} to {hours}_"

            keyboard = [
                [
                    InlineKeyboardButton(
                        "Approve",
                        callback_data=CallbackData.TIMESHEET_APPROVE.value,
                    ),
                    InlineKeyboardButton(
                        "Edit Hours",
                        callback_data=CallbackData.TIMESHEET_EDIT.value,
                    ),
                    InlineKeyboardButton(
                        "Cancel",
                        callback_data=CallbackData.TIMESHEET_CANCEL.value,
                    ),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await self._app.bot.edit_message_text(
                chat_id=self._chat_id,
                message_id=self._pending_edit_message_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )

            # Update stored info for potential further edits
            self._original_timesheet_info = updated_info
            self._original_total_amount = new_amount

            # Notify callback handler with edited hours
            if self._callback_handler:
                await self._callback_handler(
                    ApprovalResult(action=ApprovalAction.EDIT, edited_hours=hours)
                )

    async def _edit_timeout(self) -> None:
        """Handle edit mode timeout (5 minutes)."""
        try:
            await asyncio.sleep(300)  # 5 minutes

            if self._edit_mode:
                self._edit_mode = False

                # Restore original message with buttons
                if self._original_timesheet_info and self._pending_edit_message_id:
                    text = self._format_timesheet_message(
                        self._original_timesheet_info,
                        self._original_total_amount or 0,
                    )
                    text += "\n\n_Edit timed out. Original values restored._"

                    keyboard = [
                        [
                            InlineKeyboardButton(
                                "Approve",
                                callback_data=CallbackData.TIMESHEET_APPROVE.value,
                            ),
                            InlineKeyboardButton(
                                "Edit Hours",
                                callback_data=CallbackData.TIMESHEET_EDIT.value,
                            ),
                            InlineKeyboardButton(
                                "Cancel",
                                callback_data=CallbackData.TIMESHEET_CANCEL.value,
                            ),
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    await self._app.bot.edit_message_text(
                        chat_id=self._chat_id,
                        message_id=self._pending_edit_message_id,
                        text=text,
                        parse_mode="Markdown",
                        reply_markup=reply_markup,
                    )

                    await self.send_message("_Edit mode timed out._")

        except asyncio.CancelledError:
            pass  # Normal cancellation when edit completes

    # =========================================================================
    # Debug Handlers
    # =========================================================================

    async def _handle_debug_status(self) -> None:
        """Show current workflow status."""
        import json
        from src.workflow import STATE_FILE

        logger.debug("Debug: status requested")

        try:
            if not STATE_FILE.exists():
                await self.send_message("*Status:* IDLE (no state file)")
                return

            state = json.loads(STATE_FILE.read_text())

            status_lines = [
                f"*Status:* {state.get('state', 'unknown')}",
                "",
            ]

            if state.get("timesheet_info"):
                info = state["timesheet_info"]
                status_lines.append(
                    f"Timesheet: {info.get('total_hours', '?')}h "
                    f"({info.get('month', '?')}/{info.get('year', '?')})"
                )
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

    async def _handle_debug_drop_pdf(self) -> None:
        """Create and drop a test timesheet PDF (160h default)."""
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

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

            await self.send_message(
                f"📄 Test PDF created: `{output_path.name}`\n\n"
                "Watcher should detect it shortly."
            )
            logger.info(f"Debug: created test PDF at {output_path}")

        except Exception as e:
            logger.exception("Debug drop PDF failed")
            await self.send_message(f"*Error creating PDF:* {e}")

    async def _handle_debug_send_approval(self) -> None:
        """Send approval email to manager thread (for testing)."""
        import base64
        import json
        from email.mime.text import MIMEText
        from src.workflow import STATE_FILE
        from src.gmail.auth import get_gmail_service

        logger.debug("Debug: send approval requested")

        try:
            # Validate state
            if not STATE_FILE.exists():
                await self.send_message("*Error:* No state file. Start workflow first.")
                return

            state = json.loads(STATE_FILE.read_text())

            if state.get("state") != "WAITING_DOCS":
                await self.send_message(
                    f"*Error:* Not in WAITING_DOCS state (current: {state.get('state')})"
                )
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

            await self.send_message(
                "✅ Approval reply sent!\n\nMonitor should detect it within ~60s."
            )
            logger.info("Debug: sent approval reply")

        except Exception as e:
            logger.exception("Debug send approval failed")
            await self.send_message(f"*Error sending approval:* {e}")

    async def _handle_debug_send_invoice(self) -> None:
        """Send invoice email with PDF attachment (for testing)."""
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

        logger.debug("Debug: send invoice requested")

        try:
            # Validate state
            if not STATE_FILE.exists():
                await self.send_message("*Error:* No state file. Start workflow first.")
                return

            state = json.loads(STATE_FILE.read_text())

            if state.get("state") != "WAITING_DOCS":
                await self.send_message(
                    f"*Error:* Not in WAITING_DOCS state (current: {state.get('state')})"
                )
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
                attachment.add_header(
                    "Content-Disposition", "attachment", filename="faktura_2026_01.pdf"
                )
                msg.attach(attachment)

            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            await asyncio.to_thread(
                lambda: service.users().messages().send(
                    userId="me",
                    body={"raw": raw, "threadId": thread_id}
                ).execute()
            )

            await self.send_message(
                "✅ Invoice reply sent!\n\nMonitor should detect it within ~60s."
            )
            logger.info("Debug: sent invoice reply")

        except Exception as e:
            logger.exception("Debug send invoice failed")
            await self.send_message(f"*Error sending invoice:* {e}")

    async def _handle_debug_reset(self) -> None:
        """Reset workflow via existing reset handler."""
        logger.debug("Debug: reset requested")

        if self._reset_handler:
            await self._reset_handler()
            await self.send_message("🔄 Workflow reset. Drop a new timesheet to start.")
        else:
            await self.send_message("*Error:* Reset handler not configured.")


# Module-level bot instance for convenience
bot = TelegramBot()
