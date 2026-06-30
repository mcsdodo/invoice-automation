import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.config import settings
from src.models import TimesheetInfo
from src.workflow import WorkflowCoordinator
from src.gdrive.db import GDriveDB


def _coord(tmp_path, with_drive=True):
    bot = MagicMock()
    bot.send_message = AsyncMock()
    bot.send_error = AsyncMock()
    drive = MagicMock() if with_drive else None
    if drive:
        drive.ensure_subfolder.return_value = "sub_id"
    db = GDriveDB(tmp_path / "gdrive.db") if with_drive else None
    coord = WorkflowCoordinator(
        telegram_bot=bot,
        gmail_monitor=MagicMock(),
        llm_client=MagicMock(),
        drive_client=drive,
        gdrive_db=db,
    )
    return coord, drive, db


async def test_finalize_gdrive_moves_to_processed_and_marks_done(tmp_path):
    coord, drive, db = _coord(tmp_path)
    coord.data.gdrive_file_id = "f1"
    coord.data.gdrive_folder_id = "leaf"
    db.mark_in_progress("f1", "a.pdf")
    await coord._finalize_gdrive(settings.gdrive_processed_subfolder, "done")
    drive.ensure_subfolder.assert_called_once_with("leaf", "processed")
    drive.move.assert_called_once_with("f1", "sub_id")
    assert db.get_status("f1") == "done"


async def test_finalize_gdrive_moves_to_errors_and_marks_error(tmp_path):
    coord, drive, db = _coord(tmp_path)
    coord.data.gdrive_file_id = "f2"
    coord.data.gdrive_folder_id = "leaf"
    db.mark_in_progress("f2", "a.pdf")
    await coord._finalize_gdrive(settings.gdrive_errors_subfolder, "error")
    drive.ensure_subfolder.assert_called_once_with("leaf", "errors")
    assert db.get_status("f2") == "error"


async def test_finalize_gdrive_noop_without_drive(tmp_path):
    coord, _, _ = _coord(tmp_path, with_drive=False)
    coord.data.gdrive_file_id = None
    # must not raise
    await coord._finalize_gdrive("processed", "done")


async def test_finalize_gdrive_move_failure_notifies_but_not_raises(tmp_path):
    coord, drive, db = _coord(tmp_path)
    coord.data.gdrive_file_id = "f3"
    coord.data.gdrive_folder_id = "leaf"
    db.mark_in_progress("f3", "a.pdf")
    drive.move.side_effect = RuntimeError("drive down")
    await coord._finalize_gdrive("processed", "done")  # must not raise
    coord.bot.send_error.assert_awaited()


# ---------------------------------------------------------------------------
# Fix 3 — terminal paths actually invoke _finalize_gdrive
# ---------------------------------------------------------------------------

def _timesheet_info():
    return TimesheetInfo(
        total_hours=40,
        month=6,
        year=2026,
        month_name="June",
        date_range="01/Jun/26 - 30/Jun/26",
    )


async def test_archive_files_calls_finalize_with_processed(tmp_path, monkeypatch):
    """_archive_files (COMPLETE path) → _finalize_gdrive called with processed + 'done'."""
    coord, drive, db = _coord(tmp_path)
    coord.data.gdrive_file_id = "f_arch"
    coord.data.gdrive_folder_id = "leaf"
    coord.data.timesheet_info = _timesheet_info()

    # Create a dummy merged PDF in tmp_path
    merged = tmp_path / "merged.pdf"
    merged.write_bytes(b"%PDF-1.4")
    coord.data.timesheet_path = merged
    coord.data.invoice_pdf_path = merged

    db.mark_in_progress("f_arch", "merged.pdf")

    with patch.object(coord, "_finalize_gdrive", new_callable=AsyncMock) as m_finalize:
        await coord._archive_files(merged)

    m_finalize.assert_awaited_once_with(settings.gdrive_processed_subfolder, "done")


async def test_cancel_workflow_calls_finalize_with_errors(tmp_path, monkeypatch):
    """_cancel_workflow → _finalize_gdrive called with errors subfolder + 'error'."""
    coord, drive, db = _coord(tmp_path)
    coord.data.gdrive_file_id = "f_cancel"
    coord.data.gdrive_folder_id = "leaf"

    # Ensure archive_folder exists so the cancelled dir can be created
    monkeypatch.setattr(settings, "archive_folder", tmp_path / "archive")

    db.mark_in_progress("f_cancel", "file.pdf")

    with patch.object(coord, "_finalize_gdrive", new_callable=AsyncMock) as m_finalize:
        await coord._cancel_workflow()

    m_finalize.assert_awaited_once_with(settings.gdrive_errors_subfolder, "error")
