from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.gdrive.client import DriveFile
from src.gdrive.db import GDriveDB
from src.gdrive.watcher import GDriveWatcher


def _client(pdfs, tmp_path, *, download_raises=None):
    client = MagicMock()
    client.resolve_folder_path.return_value = "leaf_id"
    client.list_pdfs.return_value = pdfs

    if download_raises:
        client.download.side_effect = download_raises
    else:
        def _dl(file_id, dest):
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            Path(dest).write_bytes(b"%PDF-1.4")
            return Path(dest)
        client.download.side_effect = _dl
    return client


async def _make(tmp_path, pdfs, idle=True, *, download_raises=None, on_error=None):
    db = GDriveDB(tmp_path / "gdrive.db")
    client = _client(pdfs, tmp_path, download_raises=download_raises)
    w = GDriveWatcher(
        client=client,
        db=db,
        is_workflow_idle=lambda: idle,
        watch_path="root/leaf",
        poll_interval=999,
        download_dir=tmp_path / "incoming",
        on_error=on_error,
    )
    w._folder_id = "leaf_id"  # skip resolve in unit test
    return w, client, db


async def test_poll_picks_oldest_and_marks_in_progress(tmp_path):
    pdfs = [
        DriveFile("a", "a.pdf", "2026-01-01T00:00:00Z"),
        DriveFile("b", "b.pdf", "2026-02-01T00:00:00Z"),
    ]
    w, client, db = await _make(tmp_path, pdfs)
    await w.poll_once()
    ev = await w.get_event()
    assert ev.gdrive_file_id == "a"
    assert ev.gdrive_folder_id == "leaf_id"
    assert ev.file_path.exists()
    assert db.get_status("a") == "in_progress"
    # only one file per cycle
    assert db.get_status("b") is None


async def test_poll_skips_when_not_idle(tmp_path):
    pdfs = [DriveFile("a", "a.pdf", "2026-01-01T00:00:00Z")]
    w, client, db = await _make(tmp_path, pdfs, idle=False)
    await w.poll_once()
    client.download.assert_not_called()
    assert db.get_status("a") is None


async def test_poll_skips_when_in_progress_exists(tmp_path):
    pdfs = [DriveFile("a", "a.pdf", "2026-01-01T00:00:00Z")]
    w, client, db = await _make(tmp_path, pdfs)
    db.mark_in_progress("zzz", "other.pdf")
    await w.poll_once()
    client.download.assert_not_called()


async def test_poll_skips_already_done_file(tmp_path):
    pdfs = [DriveFile("a", "a.pdf", "2026-01-01T00:00:00Z")]
    w, client, db = await _make(tmp_path, pdfs)
    db.mark_in_progress("a", "a.pdf")
    db.mark_done("a")
    await w.poll_once()
    client.download.assert_not_called()


async def test_download_failure_calls_on_error_and_no_event(tmp_path):
    """Download raises → on_error called once with filename, no event enqueued, row stays in_progress."""
    pdfs = [DriveFile("a", "a.pdf", "2026-01-01T00:00:00Z")]
    on_error = AsyncMock()
    w, client, db = await _make(
        tmp_path, pdfs,
        download_raises=RuntimeError("drive 403"),
        on_error=on_error,
    )

    await w.poll_once()

    # on_error awaited once and message contains the filename
    on_error.assert_awaited_once()
    call_msg = on_error.call_args[0][0]
    assert "a.pdf" in call_msg

    # no event enqueued
    assert w._queue.empty()

    # row stays in_progress (recovery model preserved)
    assert db.get_status("a") == "in_progress"
