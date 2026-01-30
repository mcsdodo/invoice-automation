"""Main entry point - starts all components."""

import asyncio
import logging
import signal
import sys
from pathlib import Path

from src.config import settings
from src.watcher import FolderWatcher
from src.telegram.bot import TelegramBot, ApprovalResult
from src.gmail.monitor import GmailMonitor
from src.llm.gemini import GeminiClient
from src.workflow import WorkflowCoordinator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


class InvoiceAutomationService:
    """Main service that coordinates all components."""

    def __init__(self):
        self.watcher: FolderWatcher | None = None
        self.bot: TelegramBot | None = None
        self.gmail_monitor: GmailMonitor | None = None
        self.llm: GeminiClient | None = None
        self.workflow: WorkflowCoordinator | None = None
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Initialize and start all components."""
        logger.info("Starting Invoice Automation Service...")

        # Ensure data directories exist
        Path("data/temp").mkdir(parents=True, exist_ok=True)
        Path("data/incoming").mkdir(parents=True, exist_ok=True)
        settings.archive_folder.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.watcher = FolderWatcher()
        self.bot = TelegramBot()
        self.gmail_monitor = GmailMonitor()
        self.llm = GeminiClient()
        self.workflow = WorkflowCoordinator(
            telegram_bot=self.bot,
            gmail_monitor=self.gmail_monitor,
            gemini_client=self.llm,
        )

        # Set up Telegram callback handler
        async def on_approval(result: ApprovalResult):
            await self.workflow.handle_event({
                "type": "approval_result",
                "result": result,
            })
        self.bot.set_callback_handler(on_approval)

        # Start components
        await self.bot.initialize()
        await self.watcher.start()

        logger.info(f"Service started, watching folder: {settings.watch_folder}")
        await self.bot.send_message(
            f"🚀 Invoice Automation Service started!\n"
            f"Watching: {settings.watch_folder}"
        )

        # Run main loops
        await asyncio.gather(
            self._run_workflow(),
            self._run_folder_watcher(),
            self._run_gmail_monitor(),
            self._wait_for_shutdown(),
        )

    async def _run_workflow(self) -> None:
        """Run the workflow coordinator."""
        try:
            await self.workflow.run()
        except asyncio.CancelledError:
            logger.info("Workflow task cancelled")

    async def _run_folder_watcher(self) -> None:
        """Watch for new timesheet PDFs."""
        try:
            while not self._shutdown_event.is_set():
                try:
                    event = await asyncio.wait_for(
                        self.watcher.get_event(),
                        timeout=5.0,
                    )
                    logger.info(f"New PDF detected: {event.file_path}")
                    await self.workflow.handle_event({
                        "type": "new_timesheet",
                        "path": event.file_path,
                    })
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            logger.info("Folder watcher task cancelled")

    async def _run_gmail_monitor(self) -> None:
        """Monitor Gmail for incoming emails by checking specific threads."""
        try:
            # Track which messages we've already processed
            processed_message_ids: set[str] = set()

            while not self._shutdown_event.is_set():
                try:
                    # Only check when in WAITING_DOCS state
                    if self.workflow.data.state.value != "WAITING_DOCS":
                        await asyncio.sleep(10)
                        continue

                    # Check manager thread for approval
                    if (
                        self.workflow.data.manager_thread_id
                        and not self.workflow.data.approval_received
                    ):
                        emails = await self._check_thread_for_replies(
                            self.workflow.data.manager_thread_id,
                            processed_message_ids,
                        )
                        for email in emails:
                            logger.info(f"Reply in manager thread from: {email.from_email}")
                            await self.workflow.handle_event({
                                "type": "email_received",
                                "email": email,
                            })

                    # Check accountant thread for invoice
                    if (
                        self.workflow.data.accountant_thread_id
                        and not self.workflow.data.invoice_received
                    ):
                        emails = await self._check_thread_for_replies(
                            self.workflow.data.accountant_thread_id,
                            processed_message_ids,
                        )
                        for email in emails:
                            logger.info(f"Reply in accountant thread from: {email.from_email}")
                            await self.workflow.handle_event({
                                "type": "email_received",
                                "email": email,
                            })

                    # Wait for poll interval
                    await asyncio.sleep(self.gmail_monitor.poll_interval)

                except Exception as e:
                    logger.error(f"Gmail monitor error: {e}")
                    await asyncio.sleep(60)  # Wait before retry

        except asyncio.CancelledError:
            logger.info("Gmail monitor task cancelled")

    async def _check_thread_for_replies(
        self, thread_id: str, processed_ids: set[str]
    ) -> list:
        """Check a thread for new replies (messages we didn't send)."""
        from src.models import EmailInfo

        try:
            service = self.gmail_monitor.service
            thread = service.users().threads().get(
                userId="me", id=thread_id
            ).execute()

            replies = []
            messages = thread.get("messages", [])

            for msg in messages:
                msg_id = msg["id"]
                # Skip if already processed
                if msg_id in processed_ids:
                    continue

                # Check if this is a reply (not our original sent message)
                labels = msg.get("labelIds", [])
                # If it has SENT label but not INBOX, it's our outgoing message
                if "SENT" in labels and "INBOX" not in labels:
                    processed_ids.add(msg_id)
                    continue

                # Parse the message
                email_info = self.gmail_monitor._parse_message(msg)
                processed_ids.add(msg_id)

                # Skip if it's from us (the sender account)
                if email_info.from_email.lower() == settings.from_email.lower():
                    # But only if it doesn't have INBOX label (meaning it's a reply TO us)
                    if "INBOX" in labels:
                        replies.append(email_info)
                else:
                    replies.append(email_info)

            return replies

        except Exception as e:
            logger.error(f"Error checking thread {thread_id}: {e}")
            return []

    async def _wait_for_shutdown(self) -> None:
        """Wait for shutdown signal."""
        await self._shutdown_event.wait()

    async def stop(self) -> None:
        """Stop all components gracefully."""
        logger.info("Stopping Invoice Automation Service...")
        self._shutdown_event.set()

        if self.workflow:
            await self.workflow.stop()
        if self.watcher:
            await self.watcher.stop()
        if self.bot:
            await self.bot.shutdown()

        logger.info("Service stopped")


async def main() -> None:
    """Main entry point."""
    service = InvoiceAutomationService()

    # Set up signal handlers for graceful shutdown
    loop = asyncio.get_event_loop()

    def signal_handler():
        logger.info("Received shutdown signal")
        asyncio.create_task(service.stop())

    # Handle signals on Unix
    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)
    else:
        # On Windows, Ctrl+C will raise KeyboardInterrupt
        pass

    try:
        await service.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        await service.stop()
    except Exception as e:
        logger.exception(f"Service error: {e}")
        await service.stop()
        raise


if __name__ == "__main__":
    asyncio.run(main())
