"""Tests for TelegramBot._handle_debug_drop_pdf — gdrive and local branches."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import the ACTUAL module (not the TelegramBot singleton shadowing it via __init__)
import importlib
_bot_module = importlib.import_module("src.telegram.bot")
from src.telegram.bot import TelegramBot

# The real settings object in the bot module namespace — used for monkeypatching
_bot_settings = _bot_module.settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bot() -> TelegramBot:
    """Return a TelegramBot with no Telegram Application (never initialized)."""
    bot = TelegramBot.__new__(TelegramBot)
    bot._app = None
    bot._chat_id = 123
    bot._callback_handler = None
    bot._reset_handler = None
    bot._drive_client = None
    bot._edit_mode = False
    bot._edit_timeout_task = None
    bot._pending_edit_message_id = None
    bot._original_timesheet_info = None
    bot._original_total_amount = None
    return bot


# ---------------------------------------------------------------------------
# DriveClient.upload_pdf tests (Change 1)
# ---------------------------------------------------------------------------

class TestUploadPdf:
    def test_upload_pdf_calls_create_with_correct_body(self, tmp_path):
        """upload_pdf passes the right body, media_body, and supportsAllDrives."""
        from googleapiclient.http import MediaFileUpload
        from src.gdrive.client import DriveClient

        src_file = tmp_path / "test.pdf"
        src_file.write_bytes(b"%PDF-1.4 dummy")

        service = MagicMock()
        service.files.return_value.create.return_value.execute.return_value = {"id": "new_file_id"}

        client = DriveClient(service)
        result = client.upload_pdf("folder123", src_file, "timesheet_test.pdf")

        assert result == "new_file_id"
        call_kwargs = service.files.return_value.create.call_args.kwargs
        assert call_kwargs["body"] == {"name": "timesheet_test.pdf", "parents": ["folder123"]}
        assert call_kwargs["fields"] == "id"
        assert call_kwargs["supportsAllDrives"] is True
        assert isinstance(call_kwargs["media_body"], MediaFileUpload)

    def test_upload_pdf_returns_created_id(self, tmp_path):
        from src.gdrive.client import DriveClient

        src_file = tmp_path / "x.pdf"
        src_file.write_bytes(b"%PDF dummy")

        service = MagicMock()
        service.files.return_value.create.return_value.execute.return_value = {"id": "abc123"}

        client = DriveClient(service)
        assert client.upload_pdf("fld", src_file, "x.pdf") == "abc123"


# ---------------------------------------------------------------------------
# set_drive_client setter (Change 2)
# ---------------------------------------------------------------------------

class TestSetDriveClient:
    def test_set_drive_client_stores_value(self):
        bot = _make_bot()
        mock_client = MagicMock()
        bot.set_drive_client(mock_client)
        assert bot._drive_client is mock_client

    def test_drive_client_defaults_to_none(self):
        bot = _make_bot()
        assert bot._drive_client is None


# ---------------------------------------------------------------------------
# _handle_debug_drop_pdf — gdrive branch (Change 3)
# ---------------------------------------------------------------------------

class TestHandleDebugDropPdfGdrive:
    """In gdrive mode the handler must upload to Drive, not just write locally."""

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_gdrive_mode_calls_resolve_and_upload(self, monkeypatch, tmp_path):
        bot = _make_bot()
        drive = MagicMock()
        drive.resolve_folder_path.return_value = "folder_id_xyz"
        drive.upload_pdf.return_value = "uploaded_file_id"
        bot.set_drive_client(drive)
        bot.send_message = AsyncMock(return_value=1)

        monkeypatch.setattr(_bot_settings, "watch_source", "gdrive")
        monkeypatch.setattr(_bot_settings, "gdrive_watch_path",
                            "_documents_intake/techlab/invoicing_automation")
        monkeypatch.setattr(_bot_settings, "gdrive_poll_interval_seconds", 30)
        monkeypatch.setattr(_bot_settings, "watch_folder", tmp_path)

        with patch("reportlab.pdfgen.canvas.Canvas") as mock_canvas_cls:
            mock_canvas_cls.return_value = MagicMock()
            self._run(bot._handle_debug_drop_pdf())

        drive.resolve_folder_path.assert_called_once_with(
            "_documents_intake/techlab/invoicing_automation"
        )
        drive.upload_pdf.assert_called_once()
        upload_args = drive.upload_pdf.call_args
        assert upload_args.args[0] == "folder_id_xyz"   # folder_id
        assert upload_args.args[2] == "timesheet_test.pdf"  # name

    def test_gdrive_mode_send_message_mentions_drive(self, monkeypatch, tmp_path):
        bot = _make_bot()
        drive = MagicMock()
        drive.resolve_folder_path.return_value = "folder_id_xyz"
        bot.set_drive_client(drive)
        bot.send_message = AsyncMock(return_value=1)

        monkeypatch.setattr(_bot_settings, "watch_source", "gdrive")
        monkeypatch.setattr(_bot_settings, "gdrive_watch_path", "_documents_intake/foo")
        monkeypatch.setattr(_bot_settings, "gdrive_poll_interval_seconds", 60)
        monkeypatch.setattr(_bot_settings, "watch_folder", tmp_path)

        with patch("reportlab.pdfgen.canvas.Canvas") as mock_canvas_cls:
            mock_canvas_cls.return_value = MagicMock()
            self._run(bot._handle_debug_drop_pdf())

        sent_text = bot.send_message.call_args.args[0]
        assert "Drive" in sent_text or "drive" in sent_text.lower()

    def test_gdrive_mode_no_drive_client_sends_error(self, monkeypatch, tmp_path):
        bot = _make_bot()
        bot._drive_client = None
        bot.send_message = AsyncMock(return_value=1)

        monkeypatch.setattr(_bot_settings, "watch_source", "gdrive")
        monkeypatch.setattr(_bot_settings, "gdrive_watch_path", "_documents_intake/foo")
        monkeypatch.setattr(_bot_settings, "watch_folder", tmp_path)

        with patch("reportlab.pdfgen.canvas.Canvas") as mock_canvas_cls:
            mock_canvas_cls.return_value = MagicMock()
            self._run(bot._handle_debug_drop_pdf())

        sent_text = bot.send_message.call_args.args[0]
        assert (
            "unavailable" in sent_text
            or "error" in sent_text.lower()
            or "no Drive" in sent_text
        )


# ---------------------------------------------------------------------------
# _handle_debug_drop_pdf — local branch stays unchanged (Change 3)
# ---------------------------------------------------------------------------

class TestHandleDebugDropPdfLocal:
    """In local mode, upload_pdf must NOT be called."""

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_local_mode_does_not_call_drive(self, monkeypatch, tmp_path):
        bot = _make_bot()
        drive = MagicMock()
        bot.set_drive_client(drive)
        bot.send_message = AsyncMock(return_value=1)

        monkeypatch.setattr(_bot_settings, "watch_source", "local")
        monkeypatch.setattr(_bot_settings, "watch_folder", tmp_path)

        with patch("reportlab.pdfgen.canvas.Canvas") as mock_canvas_cls:
            mock_canvas_cls.return_value = MagicMock()
            self._run(bot._handle_debug_drop_pdf())

        drive.upload_pdf.assert_not_called()
        drive.resolve_folder_path.assert_not_called()

    def test_local_mode_send_message_mentions_watcher(self, monkeypatch, tmp_path):
        bot = _make_bot()
        bot.send_message = AsyncMock(return_value=1)

        monkeypatch.setattr(_bot_settings, "watch_source", "local")
        monkeypatch.setattr(_bot_settings, "watch_folder", tmp_path)

        with patch("reportlab.pdfgen.canvas.Canvas") as mock_canvas_cls:
            mock_canvas_cls.return_value = MagicMock()
            self._run(bot._handle_debug_drop_pdf())

        sent_text = bot.send_message.call_args.args[0]
        assert "watcher" in sent_text.lower() or "detect" in sent_text.lower()
