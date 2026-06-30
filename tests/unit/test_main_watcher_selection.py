from unittest.mock import MagicMock, patch

from src.watcher import FolderWatcher
from src.gdrive.watcher import GDriveWatcher
import src.main as main


def _wf():
    wf = MagicMock()
    wf.data.state.name = "IDLE"
    return wf


def test_build_watcher_local(monkeypatch):
    monkeypatch.setattr(main.settings, "watch_source", "local")
    w = main.build_watcher(_wf())
    assert isinstance(w, FolderWatcher)


def test_build_watcher_gdrive(monkeypatch):
    monkeypatch.setattr(main.settings, "watch_source", "gdrive")
    drive = MagicMock()
    db = MagicMock()
    w = main.build_watcher(_wf(), drive_client=drive, gdrive_db=db)
    assert isinstance(w, GDriveWatcher)
