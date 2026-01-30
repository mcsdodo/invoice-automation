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

# Configure logging - WARNING level to reduce noise
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)
# Set our app loggers to INFO for important messages
logging.getLogger("src").setLevel(logging.INFO)
logging.getLogger("__main__").setLevel(logging.INFO)


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

        # Verify Gmail credentials at startup (triggers OAuth if needed)
        logger.info("Checking Gmail credentials...")
        from src.gmail.auth import get_gmail_service
        get_gmail_service()  # This will prompt for OAuth if no token
        logger.info("Gmail credentials OK")

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

        # Set up reset handler
        async def on_reset():
            self.workflow.data.reset()
            self.workflow._save_state()
            # Clear temp files
            import shutil
            from pathlib import Path
            for f in Path("data/temp").glob("*"):
                if f.is_file():
                    f.unlink()
            for f in Path("data/incoming").glob("*.pdf"):
                f.unlink()
            logger.info("Workflow reset via Telegram command")
        self.bot.set_reset_handler(on_reset)

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
            while not self._shutdown_event.is_set():
                try:
                    # Only check when in WAITING_DOCS state
                    if self.workflow.data.state.value != "WAITING_DOCS":
                        await asyncio.sleep(10)
                        continue

                    logger.info("Checking Gmail threads for replies...")

                    # Check manager thread for approval
                    if (
                        self.workflow.data.manager_thread_id
                        and not self.workflow.data.approval_received
                    ):
                        logger.info(f"Checking manager thread: {self.workflow.data.manager_thread_id}")
                        emails = await self._check_thread_for_replies(
                            self.workflow.data.manager_thread_id,
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
                        logger.info(f"Checking accountant thread: {self.workflow.data.accountant_thread_id}")
                        emails = await self._check_thread_for_replies(
                            self.workflow.data.accountant_thread_id,
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

    async def _check_thread_for_replies(self, thread_id: str) -> list:
        """Check a thread for replies (any message after the initial sent message).

        We don't need UNREAD filter because:
        - approval_received/invoice_received flags prevent re-checking threads
        - Once a reply is found and processed, the flag is set True
        - Thread is never checked again after that
        """
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

                # Skip the initial sent message (first message in thread)
                if msg_id == thread_id:
                    continue

                # Any other message is a reply - parse it
                email_info = self.gmail_monitor._parse_message(msg)
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
