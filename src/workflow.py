"""Workflow coordinator - state machine for invoice automation."""

import asyncio
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable, Awaitable

from src.config import settings
from src.models import WorkflowState, WorkflowData, TimesheetInfo, EmailInfo
from src.pdf import parse_timesheet, merge_pdfs, HtmlToPdfConverter, html_to_pdf
from src.telegram.bot import TelegramBot, ApprovalAction, ApprovalResult
from src.gmail import send_email, reply_to_thread, GmailMonitor
from src.llm.gemini import GeminiClient

logger = logging.getLogger(__name__)

STATE_FILE = Path("data/state.json")


class WorkflowCoordinator:
    """Orchestrates the invoice automation workflow."""

    def __init__(
        self,
        telegram_bot: TelegramBot,
        gmail_monitor: GmailMonitor,
        gemini_client: GeminiClient,
    ):
        self.bot = telegram_bot
        self.gmail_monitor = gmail_monitor
        self.llm = gemini_client
        self.data = WorkflowData()
        self.event_queue: asyncio.Queue = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._running = False
        self._load_state()

    def _load_state(self) -> None:
        """Load workflow state from disk."""
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE) as f:
                    data = json.load(f)
                self.data = WorkflowData.model_validate(data)
                logger.info(f"Loaded state: {self.data.state}")
            except Exception as e:
                logger.warning(f"Failed to load state, starting fresh: {e}")
                self.data = WorkflowData()
        else:
            logger.info("No state file, starting fresh")

    def _save_state(self) -> None:
        """Persist workflow state to disk."""
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(self.data.model_dump(mode="json"), f, indent=2, default=str)
        logger.debug(f"Saved state: {self.data.state}")

    async def handle_event(self, event: dict) -> None:
        """Queue an event for processing."""
        await self.event_queue.put(event)

    async def run(self) -> None:
        """Main event loop - process events sequentially."""
        self._running = True
        logger.info(f"Workflow coordinator started in state: {self.data.state}")

        while self._running:
            try:
                event = await asyncio.wait_for(
                    self.event_queue.get(),
                    timeout=60.0  # Check timeout every minute
                )
                async with self._lock:
                    await self._process_event(event)
            except asyncio.TimeoutError:
                # Check for WAITING_DOCS timeout
                await self._check_waiting_timeout()
            except Exception as e:
                logger.exception(f"Error processing event: {e}")
                await self.bot.send_error(f"Workflow error: {e}", str(type(e).__name__))

    async def stop(self) -> None:
        """Stop the workflow coordinator."""
        self._running = False

    async def _process_event(self, event: dict) -> None:
        """Process a single event based on current state."""
        event_type = event.get("type")
        logger.info(f"Processing event: {event_type} in state: {self.data.state}")

        if event_type == "new_timesheet":
            await self._handle_new_timesheet(event["path"])
        elif event_type == "approval_result":
            await self._handle_approval_result(event["result"])
        elif event_type == "email_received":
            await self._handle_email_received(event["email"])
        else:
            logger.warning(f"Unknown event type: {event_type}")

    async def _handle_new_timesheet(self, path: Path) -> None:
        """Handle a new timesheet PDF being detected."""
        if self.data.state != WorkflowState.IDLE:
            logger.warning(f"Ignoring new timesheet, not in IDLE state")
            await self.bot.send_message(
                f"⚠️ New timesheet detected but workflow already in progress.\n"
                f"Current state: {self.data.state}"
            )
            return

        try:
            # Parse the timesheet
            timesheet_info = parse_timesheet(path)
            logger.info(f"Parsed timesheet: {timesheet_info.total_hours}h for {timesheet_info.month}/{timesheet_info.year}")

            # Update state
            self.data.timesheet_path = path
            self.data.timesheet_info = timesheet_info
            self.data.state = WorkflowState.PENDING_INIT_APPROVAL
            self._save_state()

            # Send Telegram notification
            total = timesheet_info.total_hours * settings.hourly_rate
            msg_id = await self.bot.send_timesheet_approval(timesheet_info, total)
            self.data.telegram_message_id = msg_id
            self._save_state()

        except Exception as e:
            logger.exception(f"Failed to parse timesheet: {e}")
            await self.bot.send_error(f"Failed to parse timesheet: {e}", str(path))

    async def _handle_approval_result(self, result: ApprovalResult) -> None:
        """Handle Telegram approval button press."""
        if result.action == ApprovalAction.APPROVE:
            if self.data.state == WorkflowState.PENDING_INIT_APPROVAL:
                await self._send_initial_emails()
            elif self.data.state == WorkflowState.ALL_DOCS_READY:
                await self._send_final_email()

        elif result.action == ApprovalAction.CANCEL:
            await self._cancel_workflow()

        elif result.action == ApprovalAction.EDIT:
            if result.edited_hours and self.data.timesheet_info:
                self.data.timesheet_info.total_hours = result.edited_hours
                self._save_state()
                # Message already updated by bot

    async def _send_initial_emails(self) -> None:
        """Send emails to manager and accountant."""
        if not self.data.timesheet_info or not self.data.timesheet_path:
            return

        info = self.data.timesheet_info
        await self.bot.send_message("📧 Sending emails...")

        try:
            # Email to manager + invoicing
            subject = f"YourCompany inc. faktura {info.month:02d}/{info.year}"
            body = "Ahoj, v prilohe worklog na schvalenie"

            msg_id, thread_id = await asyncio.to_thread(
                send_email,
                to=settings.manager_email,
                subject=subject,
                body=body,
                cc=settings.invoicing_dept_email,
                attachment_path=self.data.timesheet_path,
            )
            self.data.manager_thread_id = thread_id
            logger.info(f"Sent manager email, thread: {thread_id}")

            # Email to accountant
            total = info.total_hours * settings.hourly_rate
            acc_subject = f"YourCompany inc. - podklady ku vystaveniu faktur {info.month:02d}/{info.year}"
            acc_body = (
                f"za {info.month_name} prosim takto:\n"
                f"{info.total_hours}*{settings.hourly_rate}={total} bez DPH\n\n"
                f"navrh soft. arch. pre nav. aplikaciu - {info.arch_hours}h\n"
                f"testovanie navigačnej apl. počas jazdy - {info.test_hours}h"
            )

            msg_id, thread_id = await asyncio.to_thread(
                send_email,
                to=settings.accountant_email,
                subject=acc_subject,
                body=acc_body,
            )
            self.data.accountant_thread_id = thread_id
            logger.info(f"Sent accountant email, thread: {thread_id}")

            # Transition to WAITING_DOCS
            self.data.state = WorkflowState.WAITING_DOCS
            self.data.waiting_since = datetime.now()
            self._save_state()

            await self.bot.send_message(
                "✅ Emails sent!\n"
                f"• Manager: {settings.manager_email}\n"
                f"• Accountant: {settings.accountant_email}\n\n"
                "Waiting for approval and invoice..."
            )

        except Exception as e:
            logger.exception(f"Failed to send emails: {e}")
            await self.bot.send_error(f"Failed to send emails: {e}", "Email sending")

    async def _handle_email_received(self, email: EmailInfo) -> None:
        """Handle incoming email detection."""
        if self.data.state != WorkflowState.WAITING_DOCS:
            logger.debug(f"Ignoring email, not in WAITING_DOCS state")
            return

        # Check by thread ID (more reliable than FROM for Gmail aliases)
        if self.data.manager_thread_id and email.thread_id == self.data.manager_thread_id:
            await self._check_approval_email(email)
        elif self.data.accountant_thread_id and email.thread_id == self.data.accountant_thread_id:
            await self._check_invoice_email(email)
        # Fallback: check FROM address
        elif email.from_email.lower() == settings.manager_email.lower():
            await self._check_approval_email(email)
        elif email.from_email.lower() == settings.accountant_email.lower():
            await self._check_invoice_email(email)

    def _format_email_as_html(self, email: EmailInfo) -> str:
        """Format an email as full HTML with headers (like Gmail view)."""
        body_content = email.body_html if email.body_html else f"<pre>{email.body_text}</pre>"

        # Build recipient list
        to_list = ", ".join(email.to_emails) if email.to_emails else ""
        cc_list = ", ".join(email.cc_emails) if email.cc_emails else ""

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .email-header {{ background: #f5f5f5; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
        .email-header h2 {{ margin: 0 0 15px 0; color: #333; }}
        .header-row {{ margin: 5px 0; font-size: 14px; }}
        .header-label {{ color: #666; display: inline-block; width: 50px; }}
        .header-value {{ color: #333; }}
        .email-body {{ padding: 15px; line-height: 1.5; }}
    </style>
</head>
<body>
    <div class="email-header">
        <h2>{email.subject}</h2>
        <div class="header-row">
            <span class="header-label">From:</span>
            <span class="header-value">{email.from_email}</span>
        </div>
        <div class="header-row">
            <span class="header-label">To:</span>
            <span class="header-value">{to_list}</span>
        </div>
        {"<div class='header-row'><span class='header-label'>Cc:</span><span class='header-value'>" + cc_list + "</span></div>" if cc_list else ""}
    </div>
    <div class="email-body">
        {body_content}
    </div>
</body>
</html>"""
        return html

    async def _check_approval_email(self, email: EmailInfo) -> None:
        """Check if email is an approval."""
        body = email.body_text.lower()

        # Check keywords
        is_approval = any(kw in body for kw in settings.approval_keywords_list)

        if not is_approval:
            # Fallback to LLM
            is_approval, confidence = await self.llm.is_approval_email(email.body_text)
            if confidence < 0.7:
                await self.bot.send_message(
                    f"❓ Received email from manager but couldn't confirm approval.\n"
                    f"Subject: {email.subject}\n"
                    f"Please check manually."
                )
                return

        if is_approval:
            self.data.approval_received = True
            # Store full email with headers as HTML
            self.data.approval_email_html = self._format_email_as_html(email)
            self._save_state()
            await self.bot.send_message("✅ Manager approval received!")
            await self._check_all_docs_ready()

    async def _check_invoice_email(self, email: EmailInfo) -> None:
        """Check if email contains invoice PDF."""
        if not email.attachments:
            return

        # Look for PDF attachment
        pdf_attachment = None
        for att in email.attachments:
            if att.lower().endswith(".pdf"):
                pdf_attachment = att
                break

        if not pdf_attachment:
            return

        # The monitor should have downloaded the PDF
        temp_dir = Path("data/temp")
        pdf_files = list(temp_dir.glob("invoice_*.pdf"))
        if pdf_files:
            self.data.invoice_pdf_path = pdf_files[-1]  # Most recent
            self.data.invoice_received = True
            self._save_state()
            await self.bot.send_message(f"✅ Invoice received from accountant!")
            await self._check_all_docs_ready()

    async def _check_all_docs_ready(self) -> None:
        """Check if both documents received, transition if so."""
        if self.data.approval_received and self.data.invoice_received:
            self.data.state = WorkflowState.ALL_DOCS_READY
            self._save_state()

            # Send approval request
            details = (
                f"📄 Documents ready:\n"
                f"• Invoice: {self.data.invoice_pdf_path}\n"
                f"• Timesheet: {self.data.timesheet_path}\n"
                f"• Approval: ✓"
            )
            msg_id = await self.bot.send_docs_ready_approval(details)
            self.data.telegram_message_id = msg_id
            self._save_state()

    async def _send_final_email(self) -> None:
        """Merge PDFs and send final email."""
        if not all([
            self.data.invoice_pdf_path,
            self.data.timesheet_path,
            self.data.approval_email_html,
            self.data.manager_thread_id,
        ]):
            await self.bot.send_error("Missing documents for final email", "")
            return

        await self.bot.send_message("📝 Preparing final document...")

        try:
            # Convert approval email to PDF
            approval_pdf = Path("data/temp/approval.pdf")
            await html_to_pdf(self.data.approval_email_html, approval_pdf)

            # Merge PDFs
            info = self.data.timesheet_info
            merged_path = Path(f"data/temp/merged_{info.month:02d}_{info.year}.pdf")
            merge_pdfs(
                self.data.invoice_pdf_path,
                self.data.timesheet_path,
                approval_pdf,
                merged_path,
            )

            # Send as reply to manager thread
            await asyncio.to_thread(
                reply_to_thread,
                thread_id=self.data.manager_thread_id,
                body="V prílohe.",
                attachment_path=merged_path,
            )

            await self.bot.send_message("✅ Final email sent!")

            # Archive and complete
            await self._archive_files(merged_path)

            self.data.state = WorkflowState.COMPLETE
            self._save_state()

            await self.bot.send_message(
                f"🎉 Workflow complete!\n"
                f"Files archived to {settings.archive_folder}"
            )

            # Reset for next workflow
            self.data.reset()
            self._save_state()

        except Exception as e:
            logger.exception(f"Failed to send final email: {e}")
            await self.bot.send_error(f"Failed to send final email: {e}", "Final email")

    async def _archive_files(self, merged_path: Path) -> None:
        """Move files to archive folder."""
        info = self.data.timesheet_info
        archive_dir = settings.archive_folder / f"{info.year}-{info.month:02d}"
        archive_dir.mkdir(parents=True, exist_ok=True)

        files_to_archive = [
            (self.data.timesheet_path, "timesheet.pdf"),
            (self.data.invoice_pdf_path, "invoice.pdf"),
            (merged_path, "merged.pdf"),
        ]

        for src, name in files_to_archive:
            if src and src.exists():
                dst = archive_dir / name
                shutil.move(str(src), str(dst))
                logger.info(f"Archived {src} -> {dst}")

    async def _cancel_workflow(self) -> None:
        """Cancel current workflow and archive files."""
        cancelled_dir = settings.archive_folder / "cancelled" / datetime.now().strftime("%Y%m%d_%H%M%S")
        cancelled_dir.mkdir(parents=True, exist_ok=True)

        # Archive any collected files
        files = [
            self.data.timesheet_path,
            self.data.invoice_pdf_path,
        ]
        for f in files:
            if f and Path(f).exists():
                shutil.move(str(f), str(cancelled_dir / Path(f).name))

        await self.bot.send_message(f"❌ Workflow cancelled. Files moved to {cancelled_dir}")

        self.data.reset()
        self._save_state()

    async def _check_waiting_timeout(self) -> None:
        """Check if WAITING_DOCS has timed out."""
        if self.data.state != WorkflowState.WAITING_DOCS:
            return
        if not self.data.waiting_since:
            return

        elapsed = datetime.now() - self.data.waiting_since
        days = elapsed.days

        if days >= 14:
            # Daily reminder after 14 days
            await self.bot.send_message(
                f"⏰ Still waiting for documents (day {days}).\n"
                f"• Approval: {'✅' if self.data.approval_received else '❌'}\n"
                f"• Invoice: {'✅' if self.data.invoice_received else '❌'}"
            )
        elif days >= 7 and days < 8:
            # One-time reminder at 7 days
            await self.bot.send_message(
                f"⏰ Waiting for documents for {days} days.\n"
                f"• Approval: {'✅' if self.data.approval_received else '❌'}\n"
                f"• Invoice: {'✅' if self.data.invoice_received else '❌'}"
            )
