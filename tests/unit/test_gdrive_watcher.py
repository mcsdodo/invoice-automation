from pathlib import Path
from unittest.mock import MagicMock

from src.gdrive.client import DriveFile
from src.gdrive.db import GDriveDB
from src.gdrive.watcher import GDriveWatcher


def _client(pdfs, tmp_path):
    client = MagicMock()
    client.resolve_folder_path.return_value = "leaf_id"
    client.list_pdfs.return_value = pdfs

    def _dl(file_id, dest):
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"%PDF-1.4")
        return Path(dest)

    client.download.side_effect = _dl
    return client


async def _make(tmp_path, pdfs, idle=True):
    db = GDriveDB(tmp_path / "gdrive.db")
    client = _client(pdfs, tmp_path)
    w = GDriveWatcher(
        client=client,
        db=db,
        is_workflow_idle=lambda: idle,
        watch_path="root/leaf",
        poll_interval=999,
        download_dir=tmp_path / "incoming",
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
