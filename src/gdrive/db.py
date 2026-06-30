"""SQLite dedup / in-flight state for the Google Drive watcher."""

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

STATUS_IN_PROGRESS = "in_progress"
STATUS_DONE = "done"
STATUS_ERROR = "error"


class GDriveDB:
    """Tracks Drive file IDs and their processing status.

    Dedup is by Drive file ID. `in_progress` also acts as the single-tenant
    in-flight guard: while any row is in_progress, the watcher must not pick a
    new file. Every terminal path (done/error) MUST resolve the row, or the
    watcher would stall forever.
    """

    def __init__(self, db_path: Path) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gdrive_files (
                id TEXT PRIMARY KEY,
                name TEXT,
                status TEXT NOT NULL,
                seen_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def get_status(self, file_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT status FROM gdrive_files WHERE id = ?", (file_id,)
        ).fetchone()
        return row[0] if row else None

    def mark_in_progress(self, file_id: str, name: str) -> None:
        self._conn.execute(
            """
            INSERT INTO gdrive_files (id, name, status, seen_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET status=excluded.status, name=excluded.name
            """,
            (file_id, name, STATUS_IN_PROGRESS, self._now()),
        )
        self._conn.commit()

    def _set_status(self, file_id: str, status: str) -> None:
        self._conn.execute(
            "UPDATE gdrive_files SET status = ? WHERE id = ?", (status, file_id)
        )
        self._conn.commit()

    def mark_done(self, file_id: str) -> None:
        self._set_status(file_id, STATUS_DONE)

    def mark_error(self, file_id: str) -> None:
        self._set_status(file_id, STATUS_ERROR)

    def has_in_progress(self) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM gdrive_files WHERE status = ? LIMIT 1",
            (STATUS_IN_PROGRESS,),
        ).fetchone()
        return row is not None

    def clear_in_progress(self) -> int:
        """Flip every in_progress row to error. Returns the number changed.

        Recovery hook for /reset: a row left in_progress (e.g. process died
        mid-workflow) otherwise stalls the watcher forever.
        """
        cur = self._conn.execute(
            "UPDATE gdrive_files SET status = ? WHERE status = ?",
            (STATUS_ERROR, STATUS_IN_PROGRESS),
        )
        self._conn.commit()
        return cur.rowcount

    def close(self) -> None:
        self._conn.close()
