from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.config import settings
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
