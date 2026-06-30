# GDrive Watch Source — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the service watch the Google Drive folder `_documents_intake/techlab/invoicing_automation` for timesheet PDFs (selectable via `WATCH_SOURCE`, default `gdrive`), feed them into the existing workflow, and move processed Drive files to `processed/`/`errors/` — verified live via the local docker-compose stack.

**Architecture:** A new `src/gdrive/` package (auth, client, db, watcher) reuses the existing Gmail OAuth credentials (with an added Drive scope) and exposes a `GDriveWatcher` with the SAME `get_event() -> FileEvent` contract as the local `FolderWatcher`. `main.py` picks the watcher from `WATCH_SOURCE`; the watcher polls, dedups via SQLite, and downloads new PDFs into `data/incoming/` so the existing `_handle_new_timesheet` flow is unchanged. The workflow carries the file's Drive origin and, on terminal states, moves the Drive file to `processed/`/`errors/`.

**Tech Stack:** Python 3.12, asyncio, pydantic / pydantic-settings, `google-api-python-client` (already a dependency), sqlite3 (stdlib), pytest + pytest-asyncio.

## Global Constraints

- Python 3.12, asyncio; type hints everywhere; pydantic for config/models. (verbatim from project CLAUDE.md)
- All files MUST use Unix line endings (LF). All file I/O explicit `encoding="utf-8"`. (project CLAUDE.md)
- Errors → Telegram notification; stay in current state; no auto-retry; state persisted. (project CLAUDE.md)
- Unit tests mock external APIs (the Drive `Resource` is mocked the way Gmail is). No network in unit tests.
- `google-api-python-client>=2.100` is already in `requirements.txt`; do NOT add new runtime deps.
- Reuse the existing OAuth client (`config/credentials.json` / `config/token.json`); do NOT introduce a second OAuth client or service account.
- `WATCH_SOURCE=local` must behave exactly as today; do not regress it.

---

### Task 1: Test scaffolding + pytest config

**Files:**
- Create: `pyproject.toml`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/unit/test_smoke.py`

**Interfaces:**
- Consumes: nothing.
- Produces: a working `pytest` setup with `asyncio_mode = "auto"` so later async tests need no per-test decorator.

- [ ] **Step 1: Create `pyproject.toml` with pytest config**

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 2: Create the test package files**

`tests/__init__.py`, `tests/unit/__init__.py` — both empty.

`tests/conftest.py`:

```python
"""Shared pytest fixtures."""
import sys
from pathlib import Path

# Ensure the repo root (containing `src/`) is importable when pytest is run
# from any working directory.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
```

- [ ] **Step 3: Write a smoke test**

`tests/unit/test_smoke.py`:

```python
def test_src_importable():
    import src  # noqa: F401
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/unit/test_smoke.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/__init__.py tests/conftest.py tests/unit/__init__.py tests/unit/test_smoke.py
git commit -m "test(invoice-automation): scaffold pytest config + tests dir"
```

---

### Task 2: Add Drive scope + `src/gdrive/auth.py`

**Files:**
- Modify: `src/gmail/auth.py:20-24` (the `SCOPES` list) AND `get_credentials()` (scope-staleness gate)
- Create: `src/gdrive/__init__.py`
- Create: `src/gdrive/auth.py`
- Create: `tests/unit/test_gdrive_auth.py`

**Interfaces:**
- Consumes: `src.gmail.auth.get_credentials() -> google.oauth2.credentials.Credentials` (existing).
- Produces: `src.gdrive.auth.get_drive_service() -> googleapiclient.discovery.Resource` and the Drive scope constant `DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"`.

> **CRITICAL (scope re-consent):** adding a scope does NOT by itself trigger
> re-auth. The existing `get_credentials()` only re-auths when `_needs_refresh()`
> (expiry) is true — a non-expired `token.json` minted for the OLD scopes is
> returned as `creds.valid == True`, and every Drive call then 403s
> ("insufficient permission"). Step 3b fixes this by forcing a fresh OAuth flow
> when the stored token lacks the now-required scopes. `Credentials.has_scopes`
> is confirmed available in the pinned google-auth.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_gdrive_auth.py`:

```python
from unittest.mock import patch, MagicMock

from src.gmail.auth import SCOPES
from src.gdrive.auth import DRIVE_SCOPE, get_drive_service


def test_drive_scope_present_in_shared_scopes():
    assert DRIVE_SCOPE == "https://www.googleapis.com/auth/drive"
    assert DRIVE_SCOPE in SCOPES


def test_get_drive_service_builds_v3_with_shared_creds():
    fake_creds = MagicMock()
    with patch("src.gdrive.auth.get_credentials", return_value=fake_creds) as m_creds, \
         patch("src.gdrive.auth.build") as m_build:
        get_drive_service()
    m_creds.assert_called_once()
    m_build.assert_called_once_with("drive", "v3", credentials=fake_creds)


def test_get_credentials_forces_reauth_when_scopes_stale(tmp_path):
    """A stored token missing the drive scope must force a fresh OAuth flow."""
    import src.gmail.auth as auth

    stale = MagicMock()
    stale.has_scopes.return_value = False  # token predates the drive scope
    fresh = MagicMock()
    with patch.object(auth, "_load_credentials", return_value=stale), \
         patch.object(auth, "_run_oauth_flow", return_value=fresh) as m_flow, \
         patch.object(auth, "_save_credentials"):
        out = auth.get_credentials()
    m_flow.assert_called_once()
    assert out is fresh
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_gdrive_auth.py -v`
Expected: FAIL (ModuleNotFoundError: src.gdrive.auth).

- [ ] **Step 3: Add the Drive scope to gmail SCOPES**

In `src/gmail/auth.py`, change the `SCOPES` list (currently lines 20-24) to include Drive:

```python
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive",
]
```

- [ ] **Step 3b: Force re-consent when stored token lacks required scopes**

In `src/gmail/auth.py`, in `get_credentials()`, immediately after
`creds = _load_credentials(token_path)` and BEFORE the `if creds is not None:`
refresh branch, insert:

```python
    # A token minted for an older scope set is still "valid" but will 403 on the
    # new scope. Force a fresh OAuth flow when granted scopes are stale.
    if creds is not None and not creds.has_scopes(set(SCOPES)):
        logger.warning("Stored token missing required scopes; re-running OAuth flow")
        creds = None
```

- [ ] **Step 4: Create `src/gdrive/__init__.py`** (empty file).

- [ ] **Step 5: Create `src/gdrive/auth.py`**

```python
"""Google Drive service built from the shared Gmail OAuth credentials."""

import logging

from googleapiclient.discovery import build, Resource

from src.gmail.auth import get_credentials

logger = logging.getLogger(__name__)

# Full Drive scope is required: Drive OAuth scopes are not folder-scoped, and
# drive.file cannot see files the app did not create (timesheets are dropped by
# the user). Moving a processed file to processed/ is a write to such a file.
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"


def get_drive_service() -> Resource:
    """Build an authenticated Drive v3 service from the shared credentials."""
    creds = get_credentials()
    service = build("drive", "v3", credentials=creds)
    logger.debug("Drive service created")
    return service
```

- [ ] **Step 6: Run tests, verify pass**

Run: `python -m pytest tests/unit/test_gdrive_auth.py -v`
Expected: PASS (3 passed).

- [ ] **Step 7: Commit**

```bash
git add src/gmail/auth.py src/gdrive/__init__.py src/gdrive/auth.py tests/unit/test_gdrive_auth.py
git commit -m "feat(invoice-automation): add Drive scope + get_drive_service"
```

---

### Task 3: `src/gdrive/db.py` — dedup / in-flight state

**Files:**
- Create: `src/gdrive/db.py`
- Create: `tests/unit/test_gdrive_db.py`

**Interfaces:**
- Consumes: nothing (stdlib `sqlite3`).
- Produces: class `GDriveDB(db_path: Path)` with methods:
  - `get_status(file_id: str) -> str | None`
  - `mark_in_progress(file_id: str, name: str) -> None`
  - `mark_done(file_id: str) -> None`
  - `mark_error(file_id: str) -> None`
  - `has_in_progress() -> bool`
  - `clear_in_progress() -> int` — flip every `in_progress` row to `error`, return count (used by the `/reset` recovery path so a stalled watcher can be unstuck).
  - `close() -> None`
  - Statuses are the literals `"in_progress"`, `"done"`, `"error"`.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_gdrive_db.py`:

```python
from src.gdrive.db import GDriveDB


def _db(tmp_path):
    return GDriveDB(tmp_path / "gdrive.db")


def test_unknown_id_has_no_status(tmp_path):
    db = _db(tmp_path)
    assert db.get_status("abc") is None
    assert db.has_in_progress() is False


def test_in_progress_then_done(tmp_path):
    db = _db(tmp_path)
    db.mark_in_progress("abc", "timesheet.pdf")
    assert db.get_status("abc") == "in_progress"
    assert db.has_in_progress() is True
    db.mark_done("abc")
    assert db.get_status("abc") == "done"
    assert db.has_in_progress() is False


def test_in_progress_then_error(tmp_path):
    db = _db(tmp_path)
    db.mark_in_progress("abc", "x.pdf")
    db.mark_error("abc")
    assert db.get_status("abc") == "error"
    assert db.has_in_progress() is False


def test_mark_in_progress_is_idempotent_upsert(tmp_path):
    db = _db(tmp_path)
    db.mark_in_progress("abc", "x.pdf")
    db.mark_in_progress("abc", "x.pdf")  # must not raise on duplicate PK
    assert db.get_status("abc") == "in_progress"


def test_clear_in_progress_flips_to_error(tmp_path):
    db = _db(tmp_path)
    db.mark_in_progress("a", "a.pdf")
    db.mark_in_progress("b", "b.pdf")
    db.mark_done("b")
    n = db.clear_in_progress()
    assert n == 1
    assert db.get_status("a") == "error"
    assert db.get_status("b") == "done"
    assert db.has_in_progress() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_gdrive_db.py -v`
Expected: FAIL (ModuleNotFoundError: src.gdrive.db).

- [ ] **Step 3: Write the implementation**

`src/gdrive/db.py`:

```python
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
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/unit/test_gdrive_db.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/gdrive/db.py tests/unit/test_gdrive_db.py
git commit -m "feat(invoice-automation): GDrive dedup/in-flight SQLite store"
```

---

### Task 4: `src/gdrive/client.py` — Drive operations

**Files:**
- Create: `src/gdrive/client.py`
- Create: `tests/unit/test_gdrive_client.py`

**Interfaces:**
- Consumes: a Drive `Resource` (injected; in production from `get_drive_service()`).
- Produces:
  - `@dataclass DriveFile` with fields `id: str`, `name: str`, `created_time: str`.
  - class `DriveClient(service)` with methods:
    - `resolve_folder_path(path: str) -> str` — slash-separated names → leaf folder ID. Raises `FileNotFoundError` if any segment is missing.
    - `list_pdfs(folder_id: str) -> list[DriveFile]` — direct-child PDFs, non-trashed, sorted by `created_time` ascending (oldest first).
    - `download(file_id: str, dest_path: Path) -> Path` — write bytes to dest, return dest.
    - `ensure_subfolder(parent_id: str, name: str) -> str` — find-or-create, return ID.
    - `move(file_id: str, dest_folder_id: str) -> None` — swap parents.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_gdrive_client.py`:

```python
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.gdrive.client import DriveClient, DriveFile


def _service_with_files_list(pages):
    """Build a mock Drive service whose files().list().execute() returns pages."""
    service = MagicMock()
    files = service.files.return_value
    files.list.return_value.execute.side_effect = pages
    return service, files


def test_resolve_folder_path_descends_segments():
    # root -> techlab -> invoicing_automation
    service, files = _service_with_files_list([
        {"files": [{"id": "root_id", "name": "_documents_intake"}]},
        {"files": [{"id": "owner_id", "name": "techlab"}]},
        {"files": [{"id": "leaf_id", "name": "invoicing_automation"}]},
    ])
    client = DriveClient(service)
    leaf = client.resolve_folder_path("_documents_intake/techlab/invoicing_automation")
    assert leaf == "leaf_id"
    # root query must NOT contain a parent clause; child queries must.
    first_q = files.list.call_args_list[0].kwargs["q"]
    second_q = files.list.call_args_list[1].kwargs["q"]
    assert "in parents" not in first_q
    assert "'root_id' in parents" in second_q


def test_resolve_folder_path_missing_segment_raises():
    service, _ = _service_with_files_list([{"files": []}])
    client = DriveClient(service)
    with pytest.raises(FileNotFoundError):
        client.resolve_folder_path("_documents_intake/techlab/invoicing_automation")


def test_list_pdfs_filters_and_sorts_oldest_first():
    service = MagicMock()
    service.files.return_value.list.return_value.execute.return_value = {
        "files": [
            {"id": "b", "name": "b.pdf", "createdTime": "2026-02-01T00:00:00Z"},
            {"id": "a", "name": "a.pdf", "createdTime": "2026-01-01T00:00:00Z"},
        ]
    }
    client = DriveClient(service)
    out = client.list_pdfs("leaf_id")
    assert [f.id for f in out] == ["a", "b"]
    assert isinstance(out[0], DriveFile)
    q = service.files.return_value.list.call_args.kwargs["q"]
    assert "'leaf_id' in parents" in q
    assert "mimeType = 'application/pdf'" in q
    assert "trashed = false" in q


def test_ensure_subfolder_returns_existing():
    service = MagicMock()
    service.files.return_value.list.return_value.execute.return_value = {
        "files": [{"id": "proc_id", "name": "processed"}]
    }
    client = DriveClient(service)
    assert client.ensure_subfolder("leaf_id", "processed") == "proc_id"
    service.files.return_value.create.assert_not_called()


def test_ensure_subfolder_creates_when_missing():
    service = MagicMock()
    service.files.return_value.list.return_value.execute.return_value = {"files": []}
    service.files.return_value.create.return_value.execute.return_value = {"id": "new_id"}
    client = DriveClient(service)
    assert client.ensure_subfolder("leaf_id", "errors") == "new_id"
    body = service.files.return_value.create.call_args.kwargs["body"]
    assert body["mimeType"] == "application/vnd.google-apps.folder"
    assert body["parents"] == ["leaf_id"]


def test_move_swaps_parents():
    service = MagicMock()
    service.files.return_value.get.return_value.execute.return_value = {"parents": ["old"]}
    client = DriveClient(service)
    client.move("file1", "dest")
    kwargs = service.files.return_value.update.call_args.kwargs
    assert kwargs["fileId"] == "file1"
    assert kwargs["addParents"] == "dest"
    assert kwargs["removeParents"] == "old"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_gdrive_client.py -v`
Expected: FAIL (ModuleNotFoundError: src.gdrive.client).

- [ ] **Step 3: Write the implementation**

`src/gdrive/client.py`:

```python
"""Thin Google Drive wrapper: resolve folders by name, list/download/move PDFs.

Ported from personal-assistant's gdrive-poller (resolveWatchFolders / move).
"""

import io
import logging
from dataclasses import dataclass
from pathlib import Path

from googleapiclient.http import MediaIoBaseDownload

logger = logging.getLogger(__name__)

_FOLDER_MIME = "application/vnd.google-apps.folder"

# Include Shared Drives in every query. Harmless for My Drive; REQUIRED if the
# intake folder lives in a Shared Drive (otherwise queries silently return []).
_LIST_KW = {"supportsAllDrives": True, "includeItemsFromAllDrives": True}
_WRITE_KW = {"supportsAllDrives": True}


@dataclass
class DriveFile:
    id: str
    name: str
    created_time: str


def _escape(name: str) -> str:
    """Escape single quotes for a Drive query string literal."""
    return name.replace("'", "\\'")


class DriveClient:
    def __init__(self, service) -> None:
        self._service = service

    def resolve_folder_path(self, path: str) -> str:
        """Resolve a slash-separated folder name path to its leaf folder ID."""
        parent_id: str | None = None
        segments = [seg for seg in path.strip("/").split("/") if seg]
        for seg in segments:
            clauses = [
                f"name = '{_escape(seg)}'",
                f"mimeType = '{_FOLDER_MIME}'",
                "trashed = false",
            ]
            if parent_id is not None:
                clauses.append(f"'{parent_id}' in parents")
            q = " and ".join(clauses)
            resp = self._service.files().list(
                q=q,
                spaces="drive",
                fields="files(id,name)",
                pageSize=10,
                **_LIST_KW,
            ).execute()
            files = resp.get("files", [])
            if not files:
                raise FileNotFoundError(
                    f"Drive folder segment not found: '{seg}' (in path '{path}')"
                )
            parent_id = files[0]["id"]
        if parent_id is None:
            raise FileNotFoundError(f"Empty Drive folder path: '{path}'")
        return parent_id

    def list_pdfs(self, folder_id: str) -> list[DriveFile]:
        q = " and ".join([
            f"'{folder_id}' in parents",
            "mimeType = 'application/pdf'",
            "trashed = false",
        ])
        resp = self._service.files().list(
            q=q,
            spaces="drive",
            fields="files(id,name,createdTime)",
            pageSize=100,
            **_LIST_KW,
        ).execute()
        out = [
            DriveFile(id=f["id"], name=f["name"], created_time=f.get("createdTime", ""))
            for f in resp.get("files", [])
        ]
        out.sort(key=lambda f: f.created_time)
        return out

    def download(self, file_id: str, dest_path: Path) -> Path:
        dest_path = Path(dest_path)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        request = self._service.files().get_media(fileId=file_id, **_WRITE_KW)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _status, done = downloader.next_chunk()
        dest_path.write_bytes(buffer.getvalue())
        logger.info("Downloaded Drive file %s -> %s", file_id, dest_path)
        return dest_path

    def ensure_subfolder(self, parent_id: str, name: str) -> str:
        q = " and ".join([
            f"name = '{_escape(name)}'",
            f"mimeType = '{_FOLDER_MIME}'",
            f"'{parent_id}' in parents",
            "trashed = false",
        ])
        resp = self._service.files().list(
            q=q, spaces="drive", fields="files(id,name)", pageSize=1, **_LIST_KW
        ).execute()
        files = resp.get("files", [])
        if files:
            return files[0]["id"]
        created = self._service.files().create(
            body={"name": name, "mimeType": _FOLDER_MIME, "parents": [parent_id]},
            fields="id",
            **_WRITE_KW,
        ).execute()
        return created["id"]

    def move(self, file_id: str, dest_folder_id: str) -> None:
        meta = self._service.files().get(
            fileId=file_id, fields="parents", **_WRITE_KW
        ).execute()
        old_parents = ",".join(meta.get("parents", []))
        self._service.files().update(
            fileId=file_id,
            addParents=dest_folder_id,
            removeParents=old_parents,
            fields="id,parents",
            **_WRITE_KW,
        ).execute()
        logger.info("Moved Drive file %s -> folder %s", file_id, dest_folder_id)
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/unit/test_gdrive_client.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add src/gdrive/client.py tests/unit/test_gdrive_client.py
git commit -m "feat(invoice-automation): Drive client (resolve/list/download/move)"
```

---

### Task 5: Extend config (`src/config.py`)

**Files:**
- Modify: `src/config.py` (add fields after the Folders block, ~line 18)
- Create: `tests/unit/test_config_gdrive.py`

**Interfaces:**
- Produces new `Settings` fields (env names in UPPER):
  - `watch_source: str = "gdrive"` (`WATCH_SOURCE`)
  - `gdrive_watch_path: str = "_documents_intake/techlab/invoicing_automation"` (`GDRIVE_WATCH_PATH`)
  - `gdrive_poll_interval_seconds: int = 30` (`GDRIVE_POLL_INTERVAL_SECONDS`)
  - `gdrive_db_path: Path = Path("data/gdrive.db")` (`GDRIVE_DB_PATH`)
  - `gdrive_processed_subfolder: str = "processed"` (`GDRIVE_PROCESSED_SUBFOLDER`)
  - `gdrive_errors_subfolder: str = "errors"` (`GDRIVE_ERRORS_SUBFOLDER`)

- [ ] **Step 1: Write the failing test**

`tests/unit/test_config_gdrive.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_config_gdrive.py -v`
Expected: FAIL (AttributeError: watch_source).

- [ ] **Step 3: Add the fields**

In `src/config.py`, immediately after the Folders block (after line 18 `archive_folder: Path = Path("data/archive")`), insert:

```python
    # Watch source: "gdrive" (Google Drive folder) or "local" (folder watcher)
    watch_source: str = "gdrive"

    # Google Drive watcher
    gdrive_watch_path: str = "_documents_intake/techlab/invoicing_automation"
    gdrive_poll_interval_seconds: int = 30
    gdrive_db_path: Path = Path("data/gdrive.db")
    gdrive_processed_subfolder: str = "processed"
    gdrive_errors_subfolder: str = "errors"
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/unit/test_config_gdrive.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/unit/test_config_gdrive.py
git commit -m "feat(invoice-automation): WATCH_SOURCE + GDRIVE_* settings"
```

---

### Task 6: Carry Drive origin on `FileEvent` and `WorkflowData`

**Files:**
- Modify: `src/watcher.py:18-22` (the `FileEvent` dataclass)
- Modify: `src/models.py` (`WorkflowData` fields + `reset()`)
- Create: `tests/unit/test_models_gdrive_origin.py`

**Interfaces:**
- `FileEvent` gains `gdrive_file_id: str | None = None` and `gdrive_folder_id: str | None = None` (keep `file_path` first/positional).
- `WorkflowData` gains `gdrive_file_id: str | None = None` and `gdrive_folder_id: str | None = None`, cleared by `reset()`.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_models_gdrive_origin.py`:

```python
from pathlib import Path
from src.watcher import FileEvent
from src.models import WorkflowData, WorkflowState


def test_file_event_optional_gdrive_fields():
    ev = FileEvent(file_path=Path("x.pdf"))
    assert ev.gdrive_file_id is None and ev.gdrive_folder_id is None
    ev2 = FileEvent(file_path=Path("x.pdf"), gdrive_file_id="f", gdrive_folder_id="d")
    assert ev2.gdrive_file_id == "f" and ev2.gdrive_folder_id == "d"


def test_workflow_data_reset_clears_gdrive_origin():
    data = WorkflowData()
    data.gdrive_file_id = "f"
    data.gdrive_folder_id = "d"
    data.state = WorkflowState.PENDING_INIT_APPROVAL
    data.reset()
    assert data.state == WorkflowState.IDLE
    assert data.gdrive_file_id is None
    assert data.gdrive_folder_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_models_gdrive_origin.py -v`
Expected: FAIL (TypeError / AttributeError on gdrive fields).

- [ ] **Step 3a: Extend `FileEvent`** in `src/watcher.py`:

```python
@dataclass
class FileEvent:
    """Event representing a new PDF file detected (local folder or Google Drive)."""

    file_path: Path
    gdrive_file_id: str | None = None
    gdrive_folder_id: str | None = None
```

- [ ] **Step 3b: Extend `WorkflowData`** in `src/models.py`. Add after the `timesheet_info` field (line 54):

```python
    # Google Drive origin (set when watch source is gdrive)
    gdrive_file_id: str | None = None
    gdrive_folder_id: str | None = None
```

And in `WorkflowData.reset()`, add after `self.timesheet_info = None`:

```python
        self.gdrive_file_id = None
        self.gdrive_folder_id = None
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/unit/test_models_gdrive_origin.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/watcher.py src/models.py tests/unit/test_models_gdrive_origin.py
git commit -m "feat(invoice-automation): carry Drive origin on FileEvent + WorkflowData"
```

---

### Task 7: `src/gdrive/watcher.py` — poll + idle-gate

**Files:**
- Create: `src/gdrive/watcher.py`
- Create: `tests/unit/test_gdrive_watcher.py`

**Interfaces:**
- Consumes: `DriveClient` (Task 4), `GDriveDB` (Task 3), `FileEvent` (Task 6), `settings` (Task 5).
- Produces: class `GDriveWatcher(client: DriveClient, db: GDriveDB, is_workflow_idle: Callable[[], bool], watch_path: str | None = None, poll_interval: float | None = None, download_dir: Path | None = None)` with:
  - `async start() -> None` (resolves folder, launches internal poll task)
  - `async stop() -> None`
  - `async get_event() -> FileEvent` (same contract as `FolderWatcher`)
  - `async poll_once() -> None` (one cycle; unit-tested directly)
  - property `is_running -> bool`
- Behavior of `poll_once()`:
  1. If `not is_workflow_idle()` or `db.has_in_progress()` → return (skip).
  2. `list_pdfs(folder_id)`; drop any whose `get_status` is `done`/`in_progress`; if none → return.
  3. Take the oldest candidate; `db.mark_in_progress(id, name)`; `client.download(id, download_dir/name)`; enqueue `FileEvent(path, gdrive_file_id=id, gdrive_folder_id=folder_id)`.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_gdrive_watcher.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_gdrive_watcher.py -v`
Expected: FAIL (ModuleNotFoundError: src.gdrive.watcher).

- [ ] **Step 3: Write the implementation**

`src/gdrive/watcher.py`:

```python
"""Google Drive watcher with the same get_event() contract as FolderWatcher."""

import asyncio
import logging
from pathlib import Path
from typing import Callable

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
        self._client.download(target.id, dest)
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
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/unit/test_gdrive_watcher.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/gdrive/watcher.py tests/unit/test_gdrive_watcher.py
git commit -m "feat(invoice-automation): GDriveWatcher poll loop + idle gate"
```

---

### Task 8: Workflow terminal-state Drive moves

**Files:**
- Modify: `src/workflow.py` — `WorkflowCoordinator.__init__` (accept `drive_client`, `gdrive_db`), `_handle_new_timesheet` (store origin + errors-on-parse-fail), `_archive_files` (processed), `_cancel_workflow` (errors); add `_finalize_gdrive` helper.
- Create: `tests/unit/test_workflow_gdrive_moves.py`

**Interfaces:**
- Consumes: `DriveClient` (Task 4), `GDriveDB` (Task 3), `WorkflowData.gdrive_file_id/_folder_id` (Task 6).
- Produces: `WorkflowCoordinator(..., drive_client=None, gdrive_db=None)`; helper
  `_finalize_gdrive(self, subfolder: str, mark: str) -> None` that moves the Drive file to `subfolder` and sets the DB status — a no-op when `drive_client` is None or `data.gdrive_file_id` is None. `mark` is `"done"` or `"error"`.

> NOTE for implementer: read the current `WorkflowCoordinator.__init__` signature and the exact bodies of `_handle_new_timesheet`, `_archive_files`, and `_cancel_workflow` before editing (see `_tasks/02-gdrive-watch-source/02-design.md` §5). Keep all existing behavior; only ADD the Drive hooks. The `__init__` currently takes `telegram_bot`, `gmail_monitor`, `llm_client` (all keyword) — add `drive_client=None, gdrive_db=None` as new optional keyword params and store them on `self`.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_workflow_gdrive_moves.py`:

```python
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

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
    await coord._finalize_gdrive(coord.settings.gdrive_processed_subfolder, "done")
    drive.ensure_subfolder.assert_called_once_with("leaf", "processed")
    drive.move.assert_called_once_with("f1", "sub_id")
    assert db.get_status("f1") == "done"


async def test_finalize_gdrive_moves_to_errors_and_marks_error(tmp_path):
    coord, drive, db = _coord(tmp_path)
    coord.data.gdrive_file_id = "f2"
    coord.data.gdrive_folder_id = "leaf"
    db.mark_in_progress("f2", "a.pdf")
    await coord._finalize_gdrive(coord.settings.gdrive_errors_subfolder, "error")
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
```

> The implementer must expose `self.settings` on the coordinator if not already present; if `WorkflowCoordinator` imports the module-level `settings` instead, change the test to `from src.config import settings` and use `settings.gdrive_processed_subfolder`. Verify which during Step 3 and keep the test consistent.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_workflow_gdrive_moves.py -v`
Expected: FAIL (TypeError: unexpected keyword 'drive_client').

- [ ] **Step 3: Implement**

3a. In `WorkflowCoordinator.__init__`, add optional params and store them:

```python
        drive_client=None,
        gdrive_db=None,
```
```python
        self.drive_client = drive_client
        self.gdrive_db = gdrive_db
```

3b. Add the helper (uses module-level `settings` already imported in workflow.py):

```python
    async def _finalize_gdrive(self, subfolder: str, mark: str) -> None:
        """Move the Drive origin file to `subfolder` and set its DB status.

        No-op when not running off Google Drive. Best-effort: a Drive API
        failure notifies via Telegram but never crashes the workflow.
        """
        file_id = self.data.gdrive_file_id
        folder_id = self.data.gdrive_folder_id
        if not self.drive_client or not file_id or not folder_id:
            return
        try:
            dest_id = self.drive_client.ensure_subfolder(folder_id, subfolder)
            self.drive_client.move(file_id, dest_id)
            if self.gdrive_db:
                if mark == "done":
                    self.gdrive_db.mark_done(file_id)
                else:
                    self.gdrive_db.mark_error(file_id)
        except Exception as e:
            logger.exception("Failed to move Drive file %s to %s: %s", file_id, subfolder, e)
            await self.bot.send_error(
                f"Drive move to {subfolder}/ failed: {e}", file_id
            )
```

3c. In `_handle_new_timesheet`, after the IDLE guard returns and BEFORE parsing, store the origin (the caller passes the ids — see Task 9 wiring). Change the signature to:

```python
    async def _handle_new_timesheet(self, path: Path, gdrive_file_id: str | None = None, gdrive_folder_id: str | None = None) -> None:
```

Right after the IDLE check, add:

```python
        self.data.gdrive_file_id = gdrive_file_id
        self.data.gdrive_folder_id = gdrive_folder_id
```

In the `except Exception` parse-failure block (after `send_error`), add the errors move:

```python
            await self._finalize_gdrive(settings.gdrive_errors_subfolder, "error")
```

3d. In `_archive_files`, after the local archive loop completes, add the processed move:

```python
        await self._finalize_gdrive(settings.gdrive_processed_subfolder, "done")
```

3e. In `_cancel_workflow`, before `self.data.reset()`, add the errors move:

```python
        await self._finalize_gdrive(settings.gdrive_errors_subfolder, "error")
```

3f. Update the event dispatch in `handle_event` to forward the ids:

```python
        if event_type == "new_timesheet":
            await self._handle_new_timesheet(
                event["path"],
                event.get("gdrive_file_id"),
                event.get("gdrive_folder_id"),
            )
```

> If the test references `coord.settings`, adjust per the Step 1 note: workflow.py uses the module-level `settings`, so update the test to import `from src.config import settings` and drop `coord.settings`.

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/unit/test_workflow_gdrive_moves.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Run the FULL unit suite (no regressions)**

Run: `python -m pytest tests/unit -v`
Expected: PASS (all green).

- [ ] **Step 6: Commit**

```bash
git add src/workflow.py tests/unit/test_workflow_gdrive_moves.py
git commit -m "feat(invoice-automation): move Drive file to processed/errors on terminal states"
```

---

### Task 9: Wire watcher selection in `main.py`

**Files:**
- Modify: `src/main.py` — `start()` (select watcher, build Drive client/db, pass into workflow + watcher), `_run_folder_watcher()` (forward gdrive ids).
- Create: `tests/unit/test_main_watcher_selection.py`

**Interfaces:**
- Produces a module-level factory `build_watcher(workflow, *, drive_client=None, gdrive_db=None)` in `src/main.py` that returns a `FolderWatcher` when `settings.watch_source == "local"` and a `GDriveWatcher` otherwise. This keeps selection unit-testable without booting the whole service.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_main_watcher_selection.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_main_watcher_selection.py -v`
Expected: FAIL (AttributeError: module 'src.main' has no attribute 'build_watcher').

- [ ] **Step 3: Implement**

3a. Add imports near the top of `src/main.py`:

```python
from src.gdrive.auth import get_drive_service
from src.gdrive.client import DriveClient
from src.gdrive.db import GDriveDB
from src.gdrive.watcher import GDriveWatcher
from src.config import settings
```

(Use the existing `settings` import if already present — do not duplicate.)

3b. Add the factory at module level:

```python
def build_watcher(workflow, *, drive_client=None, gdrive_db=None):
    """Return the configured watcher (local FolderWatcher or GDriveWatcher)."""
    if settings.watch_source == "local":
        return FolderWatcher()
    return GDriveWatcher(
        client=drive_client,
        db=gdrive_db,
        is_workflow_idle=lambda: workflow.data.state == WorkflowState.IDLE,
    )
```

Ensure `WorkflowState` is imported in `main.py` (`from src.models import WorkflowState`); add it if missing.

3c. In `start()`, replace `self.watcher = FolderWatcher()` with conditional construction. Build Drive deps only in gdrive mode, BEFORE constructing the workflow, and pass them into the workflow:

```python
        drive_client = None
        gdrive_db = None
        if settings.watch_source != "local":
            drive_client = DriveClient(get_drive_service())
            gdrive_db = GDriveDB(settings.gdrive_db_path)

        self.workflow = WorkflowCoordinator(
            telegram_bot=self.bot,
            gmail_monitor=self.gmail_monitor,
            llm_client=self.llm,
            drive_client=drive_client,
            gdrive_db=gdrive_db,
        )

        self.watcher = build_watcher(
            self.workflow, drive_client=drive_client, gdrive_db=gdrive_db
        )
```

(Remove the now-duplicated original `self.watcher = FolderWatcher()` and the original `self.workflow = WorkflowCoordinator(...)` block; keep the Telegram callback/reset wiring that follows.)

3d. In `_run_folder_watcher`, forward the Drive ids in the event:

```python
                    await self.workflow.handle_event({
                        "type": "new_timesheet",
                        "path": event.file_path,
                        "gdrive_file_id": event.gdrive_file_id,
                        "gdrive_folder_id": event.gdrive_folder_id,
                    })
```

3e. Re-consent on first gdrive run: the startup `get_gmail_service()` →
`get_credentials()` now includes the Task 2 Step 3b scope-staleness gate, so a
pre-existing token lacking the Drive scope forces one OAuth flow automatically.
(Do NOT rely on expiry alone — that was the bug fixed in Task 2.)

3f. Extend the existing `on_reset` handler in `start()` so `/reset` also unsticks
the Drive watcher. The current handler resets workflow state and clears
`data/temp` + `data/incoming`; add, when `gdrive_db` is set:

```python
            if gdrive_db is not None:
                cleared = gdrive_db.clear_in_progress()
                if cleared:
                    logger.info("Cleared %d stuck in_progress Drive row(s)", cleared)
```

(`gdrive_db` is in scope from the `start()` construction above; capture it in the
closure. Without this, a stalled `in_progress` row blocks the watcher forever —
`has_in_progress()` stays true.)

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/unit/test_main_watcher_selection.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run FULL unit suite**

Run: `python -m pytest tests/unit -v`
Expected: PASS (all green).

- [ ] **Step 6: Commit**

```bash
git add src/main.py tests/unit/test_main_watcher_selection.py
git commit -m "feat(invoice-automation): select watcher by WATCH_SOURCE in main"
```

---

### Task 10: `.env.example`, docker-compose, docs

**Files:**
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Modify: `CLAUDE.md`
- Modify: `CHANGELOG.md`

**Interfaces:** none (config/docs only).

- [ ] **Step 1: Add the new env vars to `.env.example`** (after the Folders section):

```env
# Watch source: gdrive (Google Drive folder) or local (folder watcher)
WATCH_SOURCE=gdrive

# Google Drive watcher (used when WATCH_SOURCE=gdrive)
GDRIVE_WATCH_PATH=_documents_intake/techlab/invoicing_automation
GDRIVE_POLL_INTERVAL_SECONDS=30
GDRIVE_DB_PATH=/app/data/gdrive.db
GDRIVE_PROCESSED_SUBFOLDER=processed
GDRIVE_ERRORS_SUBFOLDER=errors
```

- [ ] **Step 2: Add container env to `docker-compose.yml`** under `environment:`:

```yaml
      - WATCH_SOURCE=${WATCH_SOURCE:-gdrive}
      - GDRIVE_WATCH_PATH=${GDRIVE_WATCH_PATH:-_documents_intake/techlab/invoicing_automation}
      - GDRIVE_DB_PATH=/app/data/gdrive.db
```

- [ ] **Step 3: Update `CLAUDE.md`** — in "Environment Variables" add the `WATCH_SOURCE` / `GDRIVE_*` block, and add a short "Watch source" subsection under Architecture noting: gdrive default, reuses the Gmail OAuth client with the added `drive` scope (one-time re-consent), processed files moved to `processed/`/`errors/` in Drive, dedup via `data/gdrive.db`.

- [ ] **Step 4: Update `CHANGELOG.md`** — add a dated entry: "Added Google Drive watch source (`WATCH_SOURCE=gdrive`, default) — polls `_documents_intake/techlab/invoicing_automation`, dedups via SQLite, moves processed files to `processed/`/`errors/`; local folder watcher retained via `WATCH_SOURCE=local`. Requires one-time OAuth re-consent for the added Drive scope."

- [ ] **Step 5: Commit**

```bash
git add .env.example docker-compose.yml CLAUDE.md CHANGELOG.md
git commit -m "docs(invoice-automation): document GDrive watch source + env"
```

---

### Task 11: Live verification on the local docker-compose stack (DEFINITION OF DONE)

**Goal:** Prove the GDrive watcher works end-to-end against the real Drive folder using the local compose stack.

**Pre-req — Drive-scoped token:** The added `drive` scope means the current
`config/token.json` no longer satisfies the scope gate (Task 2 Step 3b), so a
re-consent is needed.
- **(a) Re-consent the existing client (primary path):** delete
  `config/token.json`, start the stack, open the OAuth URL printed in logs,
  approve gmail+drive. **Before starting, confirm the `:8080` callback is
  reachable from wherever the browser runs** (the flow binds `0.0.0.0:8080` in
  the container, published in compose). On this headless VM, either port-forward
  `:8080` to the machine with the browser, or run the OAuth flow on a desktop
  with the same `credentials.json` and copy the resulting `token.json` into
  `config/`. If `:8080` is not reachable, Task 11 hard-blocks here — resolve it
  first.
- **(b) Borrow PA's Drive token — LIKELY A DEAD END, verify before relying:**
  PA's token is bound to PA's OAuth **client_id** and stored in
  `google_workspace_mcp`'s own format, NOT an `InstalledAppFlow` `authorized_user`
  `token.json` bound to invoice-automation's client_id. Refresh tokens are not
  portable across client_ids, so dropping PA's token into `config/token.json`
  will almost certainly fail to load/refresh. Only viable if you instead point
  invoice-automation's `credentials.json` at PA's client AND mint a fresh
  `authorized_user` token for it. Default to path (a). Do NOT commit any token.

- [ ] **Step 1: Ensure the test Drive folder exists**

Confirm (or create) `_documents_intake/techlab/invoicing_automation` in the Drive account used by `FROM_EMAIL`. Place one sample timesheet PDF there (a Jira-export-style PDF the parser can read, e.g. reuse a fixture from a prior workflow run).

- [ ] **Step 2: Build and start the stack**

Run:
```bash
docker compose build
WATCH_SOURCE=gdrive docker compose up -d
docker compose logs -f invoice-automation
```
Expected in logs: "Watching Drive folder '_documents_intake/techlab/invoicing_automation' (id=...)" and, within one poll interval, "New Drive timesheet: <name>".

- [ ] **Step 3: Verify pickup → workflow start**

Expected: a Telegram approval message appears (PENDING_INIT_APPROVAL), and `data/gdrive.db` has the file row as `in_progress`. Confirm with:
```bash
docker compose exec invoice-automation python -c "import sqlite3; print(sqlite3.connect('/app/data/gdrive.db').execute('select id,name,status from gdrive_files').fetchall())"
```

- [ ] **Step 4: Verify move-to-processed**

Drive `processed/` is created on completion. To exercise the terminal path without the full email round-trip, cancel the workflow from Telegram (CANCEL) and confirm:
- the Drive file moved to `errors/` (cancel path),
- the db row is `error`,
- the watcher resumes and `has_in_progress()` is false.
For the full `processed/` path, run a complete workflow (approve → emails → docs → final) or temporarily drive `_archive_files` via the existing debug menu if available. Record which path was exercised.

- [ ] **Step 5: Verify local fallback still works**

Run:
```bash
docker compose down
WATCH_SOURCE=local docker compose up -d
```
Drop a PDF into `./data/incoming/` and confirm it is detected (existing behavior), proving no regression.

- [ ] **Step 6: Record results + commit any fixes**

Append a short "Verification" note to `_tasks/02-gdrive-watch-source/03-plan.md` (or a `04-verification.md`) capturing: token method used (a/b), log excerpts, db state, which terminal path was exercised. Commit any code fixes discovered during verification with clear messages. Revert any borrowed token.

---

## Self-Review

**Spec coverage** (design §1-§10):
- §3 producer interface / watcher selection → Tasks 6, 7, 9.
- §4 `src/gdrive/` package (auth/client/db/watcher) → Tasks 2, 3, 4, 7.
- §5 workflow integration (origin + terminal moves) → Tasks 6, 8, 9.
- §6 config/env → Tasks 5, 10.
- §7 auth/re-consent → Tasks 2, 9 (startup), 11 (operational).
- §8 testing → every task (TDD) + Task 1 scaffold.
- "verified via local compose stack" goal → Task 11.

**Placeholder scan:** No "TBD"/"handle edge cases" — every code step shows code. The two NOTE blocks (Tasks 8, 9) instruct the implementer to read exact current bodies before editing existing functions, because those bodies are large and must be preserved; the additions themselves are given verbatim.

**Type consistency:** `GDriveDB` status literals (`in_progress`/`done`/`error`) consistent across Tasks 3, 7, 8. `DriveClient` method names (`resolve_folder_path`, `list_pdfs`, `download`, `ensure_subfolder`, `move`) consistent across Tasks 4, 7, 8. `FileEvent` / `WorkflowData` fields (`gdrive_file_id`, `gdrive_folder_id`) consistent across Tasks 6, 7, 8, 9. `build_watcher` / `_finalize_gdrive` signatures consistent across their defining and calling tasks.

**Known risk to watch during execution:** if a `FileEvent` is enqueued but the
process dies before the workflow marks the row terminal, the row stays
`in_progress` and stalls the watcher. Recovery: `/reset` now calls
`gdrive_db.clear_in_progress()` (Task 9 Step 3f) — flipping stuck rows to `error`
so the watcher resumes. Note this in CLAUDE.md (Task 10). No auto-recovery beyond
`/reset` (YAGNI).

**Async note (intentional):** `poll_once` calls the synchronous googleapiclient
(`list_pdfs`/`download`/`resolve_folder_path`) directly inside the asyncio loop.
This is consistent with the repo's existing `GmailMonitor`, which also calls
`.execute()` synchronously inside async methods. Do NOT wrap in
`asyncio.to_thread` — matching the established convention keeps the code uniform.
The poll runs in its own task and the workflow is single-tenant, so brief blocking
during a poll is acceptable.
