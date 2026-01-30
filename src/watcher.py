"""Folder watcher for monitoring incoming PDF files."""

import asyncio
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from watchdog.events import FileCreatedEvent, FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from src.config import settings

logger = logging.getLogger(__name__)


@dataclass
class FileEvent:
    """Event representing a new PDF file detected in the watch folder."""

    file_path: Path


class _DebouncedPDFHandler(FileSystemEventHandler):
    """Watchdog event handler with debouncing for PDF files.

    Waits for a file to be stable (no modifications for debounce_seconds)
    before emitting an event. This handles large file copies that trigger
    multiple modification events.
    """

    def __init__(
        self,
        callback: Callable[[Path], None],
        debounce_seconds: float = 2.0,
    ) -> None:
        """Initialize the handler.

        Args:
            callback: Function to call when a PDF file is ready.
            debounce_seconds: Time to wait after last modification before
                             considering the file ready.
        """
        super().__init__()
        self._callback = callback
        self._debounce_seconds = debounce_seconds
        self._pending_files: dict[Path, threading.Timer] = {}
        self._lock = threading.Lock()

    def _is_pdf_file(self, path: str) -> bool:
        """Check if the path is a PDF file (case insensitive)."""
        return path.lower().endswith(".pdf")

    def _schedule_callback(self, file_path: Path) -> None:
        """Schedule a callback for a file, canceling any existing timer."""
        with self._lock:
            # Cancel existing timer for this file if any
            if file_path in self._pending_files:
                self._pending_files[file_path].cancel()

            # Schedule new callback
            timer = threading.Timer(
                self._debounce_seconds,
                self._emit_event,
                args=[file_path],
            )
            self._pending_files[file_path] = timer
            timer.start()
            logger.debug(
                "Scheduled callback for %s in %.1f seconds",
                file_path,
                self._debounce_seconds,
            )

    def _emit_event(self, file_path: Path) -> None:
        """Emit the event for a ready file."""
        with self._lock:
            # Remove from pending
            self._pending_files.pop(file_path, None)

        # Verify file still exists
        if file_path.exists():
            logger.info("PDF file ready: %s", file_path)
            self._callback(file_path)
        else:
            logger.warning("PDF file no longer exists: %s", file_path)

    def on_created(self, event: FileCreatedEvent) -> None:
        """Handle file creation event."""
        if event.is_directory:
            return

        if self._is_pdf_file(event.src_path):
            file_path = Path(event.src_path)
            logger.debug("PDF file created: %s", file_path)
            self._schedule_callback(file_path)

    def on_modified(self, event: FileModifiedEvent) -> None:
        """Handle file modification event."""
        if event.is_directory:
            return

        if self._is_pdf_file(event.src_path):
            file_path = Path(event.src_path)
            logger.debug("PDF file modified: %s", file_path)
            self._schedule_callback(file_path)

    def cancel_all(self) -> None:
        """Cancel all pending timers."""
        with self._lock:
            for timer in self._pending_files.values():
                timer.cancel()
            self._pending_files.clear()


class FolderWatcher:
    """Watches a folder for new PDF files and emits events via async queue.

    Usage:
        watcher = FolderWatcher()
        await watcher.start()

        while True:
            event = await watcher.get_event()
            # Process event.file_path
    """

    def __init__(
        self,
        watch_folder: Path | None = None,
        debounce_seconds: float = 2.0,
    ) -> None:
        """Initialize the folder watcher.

        Args:
            watch_folder: Folder to watch. Defaults to settings.watch_folder.
            debounce_seconds: Time to wait after last modification before
                             considering a file ready.
        """
        self._watch_folder = watch_folder or settings.watch_folder
        self._debounce_seconds = debounce_seconds
        self._observer: Observer | None = None
        self._handler: _DebouncedPDFHandler | None = None
        self._queue: asyncio.Queue[FileEvent] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._running = False

    def _on_file_ready(self, file_path: Path) -> None:
        """Callback from watchdog handler when a file is ready.

        Bridges the sync watchdog callback to the async queue.
        """
        if self._loop is None:
            logger.error("Event loop not set, cannot emit event")
            return

        event = FileEvent(file_path=file_path)
        # Thread-safe way to put item into async queue from sync context
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event)

    async def start(self) -> None:
        """Start watching the folder for PDF files.

        Creates the watch folder if it doesn't exist.
        """
        if self._running:
            logger.warning("Watcher already running")
            return

        # Ensure watch folder exists
        self._watch_folder.mkdir(parents=True, exist_ok=True)
        logger.info("Watching folder: %s", self._watch_folder)

        # Store event loop for thread-safe queue access
        self._loop = asyncio.get_running_loop()

        # Create handler and observer
        self._handler = _DebouncedPDFHandler(
            callback=self._on_file_ready,
            debounce_seconds=self._debounce_seconds,
        )
        self._observer = Observer()
        self._observer.schedule(
            self._handler,
            str(self._watch_folder),
            recursive=False,
        )
        self._observer.start()
        self._running = True
        logger.info("Folder watcher started")

    async def stop(self) -> None:
        """Stop watching the folder."""
        if not self._running:
            logger.warning("Watcher not running")
            return

        # Cancel pending debounce timers
        if self._handler:
            self._handler.cancel_all()
            self._handler = None

        # Stop observer
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5.0)
            self._observer = None

        self._running = False
        self._loop = None
        logger.info("Folder watcher stopped")

    async def get_event(self) -> FileEvent:
        """Get the next file event from the queue.

        Blocks until an event is available.

        Returns:
            FileEvent containing the path to the new PDF file.
        """
        return await self._queue.get()

    @property
    def is_running(self) -> bool:
        """Check if the watcher is currently running."""
        return self._running

    @property
    def watch_folder(self) -> Path:
        """Get the folder being watched."""
        return self._watch_folder
