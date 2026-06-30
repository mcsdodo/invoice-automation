"""Google Drive watcher with the same get_event() contract as FolderWatcher."""

import asyncio
import logging
from pathlib import Path
from typing import Awaitable, Callable

from src.config import settings
from src.gdrive.client import DriveClient
from src.gdrive.db import GDriveDB, STATUS_DONE, STATUS_IN_PROGRESS
from src.watcher import FileEvent

logger = logging.getLogger(__name__)


class GDriveWatcher:
    def __init__(
        self,
        client: DriveClient,
        db: GDriveDB,
        is_workflow_idle: Callable[[], bool],
        watch_path: str | None = None,
        poll_interval: float | None = None,
        download_dir: Path | None = None,
        on_error: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self._client = client
        self._db = db
        self._is_workflow_idle = is_workflow_idle
        self._watch_path = watch_path or settings.gdrive_watch_path
        self._poll_interval = (
            poll_interval if poll_interval is not None
            else settings.gdrive_poll_interval_seconds
        )
        self._download_dir = Path(download_dir or Path("data/incoming"))
        self._on_error = on_error
        self._queue: asyncio.Queue[FileEvent] = asyncio.Queue()
        self._folder_id: str | None = None
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            logger.warning("GDrive watcher already running")
            return
        self._folder_id = self._client.resolve_folder_path(self._watch_path)
        logger.info("Watching Drive folder '%s' (id=%s)", self._watch_path, self._folder_id)
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())

    async def _poll_loop(self) -> None:
        try:
            while self._running:
                try:
                    await self.poll_once()
                except Exception as e:  # never let the loop die
                    logger.exception("GDrive poll cycle failed: %s", e)
                await asyncio.sleep(self._poll_interval)
        except asyncio.CancelledError:
            logger.info("GDrive poll loop cancelled")

    async def poll_once(self) -> None:
        if not self._is_workflow_idle() or self._db.has_in_progress():
            return
        if self._folder_id is None:
            self._folder_id = self._client.resolve_folder_path(self._watch_path)
        pdfs = self._client.list_pdfs(self._folder_id)
        candidates = [
            f for f in pdfs
            if self._db.get_status(f.id) not in (STATUS_DONE, STATUS_IN_PROGRESS)
        ]
        if not candidates:
            return
        target = candidates[0]  # list_pdfs returns oldest-first
        self._db.mark_in_progress(target.id, target.name)
        dest = self._download_dir / target.name
        try:
            self._client.download(target.id, dest)
        except Exception as e:
            logger.exception("GDrive download failed for %s: %s", target.name, e)
            if self._on_error is not None:
                await self._on_error(
                    f"GDrive download failed for {target.name}: {e}. Run /reset to retry."
                )
            return
        logger.info("New Drive timesheet: %s (id=%s)", target.name, target.id)
        self._queue.put_nowait(
            FileEvent(
                file_path=dest,
                gdrive_file_id=target.id,
                gdrive_folder_id=self._folder_id,
            )
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def get_event(self) -> FileEvent:
        return await self._queue.get()

    @property
    def is_running(self) -> bool:
        return self._running
