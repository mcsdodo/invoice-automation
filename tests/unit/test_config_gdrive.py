from pathlib import Path
from src.config import Settings


def _settings(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    # Minimal required fields for Settings to construct.
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    monkeypatch.setenv("FROM_EMAIL", "a@b.c")
    monkeypatch.setenv("MANAGER_EMAIL", "a@b.c")
    monkeypatch.setenv("INVOICING_DEPT_EMAIL", "a@b.c")
    monkeypatch.setenv("ACCOUNTANT_EMAIL", "a@b.c")
    return Settings(_env_file=None)


def test_gdrive_defaults(monkeypatch):
    s = _settings(monkeypatch)
    assert s.watch_source == "gdrive"
    assert s.gdrive_watch_path == "_documents_intake/techlab/invoicing_automation"
    assert s.gdrive_poll_interval_seconds == 30
    assert s.gdrive_db_path == Path("data/gdrive.db")
    assert s.gdrive_processed_subfolder == "processed"
    assert s.gdrive_errors_subfolder == "errors"


def test_watch_source_override(monkeypatch):
    s = _settings(monkeypatch, WATCH_SOURCE="local")
    assert s.watch_source == "local"
