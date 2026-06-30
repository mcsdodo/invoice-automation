**Date:** 2026-06-30
**Subject:** Google Drive watch source — architecture & design
**Status:** Planning (approved by user 2026-06-30)

## 1. Goal

Add a Google Drive watcher that polls
`_documents_intake/techlab/invoicing_automation` for timesheet PDFs and feeds
them into the existing workflow, selectable via `WATCH_SOURCE=gdrive|local`
(default `gdrive`). Processed files are moved to `processed/` (or `errors/`) in
Drive, mirroring the local archive flow. Implemented directly with
`google-api-python-client`, reusing the service's existing Gmail OAuth client.

## 2. Key constraint: single-tenant

`WorkflowCoordinator` handles exactly one timesheet at a time — the `IDLE` guard
(`src/workflow.py`) rejects a second `new_timesheet` while a workflow is in
flight. The design must:

- never pull a new Drive file while a workflow is active, and
- never mark a file "seen" before the workflow has accepted it (else a rejected
  file is lost).

This is why the watcher gates on workflow state and uses an explicit
`in_progress`/`done`/`error` status rather than a fire-and-forget "seen" set.

## 3. Architecture

The new watcher sits behind the **same producer interface** the local watcher
already exposes (`get_event() -> FileEvent`). Nothing downstream changes except
that the event/workflow now carries the file's Drive origin so it can be moved
on completion.

```
WATCH_SOURCE=gdrive
  GDriveWatcher.poll() ──┐
                         ├─► FileEvent{path, gdrive_file_id, gdrive_folder_id} ─► asyncio.Queue
WATCH_SOURCE=local       │
  FolderWatcher (today) ─┘
        │
        ▼
  WorkflowCoordinator  (IDLE → PENDING_INIT_APPROVAL → WAITING_DOCS → ALL_DOCS_READY → COMPLETE)
        │ on COMPLETE   → move Drive file → processed/   + local archive (unchanged)
        │ on fail/cancel→ move Drive file → errors/
```

## 4. New package: `src/gdrive/`

### `src/gdrive/auth.py`
- `get_drive_service() -> Resource` building `build("drive", "v3", credentials=creds)`.
- Reuses the credentials produced by `src/gmail/auth.py`. Add
  `https://www.googleapis.com/auth/drive` to the shared `SCOPES` list in
  `src/gmail/auth.py` so the single token carries both Gmail and Drive scopes.

### `src/gdrive/client.py` — thin Drive wrapper (ports PA's `resolveWatchFolders`/move logic)
- `resolve_folder_path(path: str) -> str` — descend `a/b/c` resolving each
  segment by name to a folder ID:
  `name = '<seg>' and '<parentId>' in parents and mimeType =
  'application/vnd.google-apps.folder' and trashed = false`. The root segment is
  resolved without a parent clause. Result cached.
- `list_pdfs(folder_id) -> list[DriveFile]` — `files.list` filtered to
  `mimeType = 'application/pdf'`, non-trashed, direct children only.
- `download(file_id, dest_path)` — `files.get_media` → write bytes to a local
  temp path (the PDF parser/merger need a local file).
- `ensure_subfolder(parent_id, name) -> str` — find-or-create `processed`/`errors`.
- `move(file_id, dest_folder_id)` — `files.update(addParents=dest,
  removeParents=current)` (the parent-swap "move").

### `src/gdrive/db.py` — SQLite dedup / in-flight state
- DB at `data/gdrive.db` (under the existing `./data` mount). WAL mode.
- Table `gdrive_files(id TEXT PRIMARY KEY, name TEXT, status TEXT, seen_at TEXT)`,
  `status ∈ {in_progress, done, error}`.
- Helpers: `get_status(id)`, `mark_in_progress(id, name)`, `mark_done(id)`,
  `mark_error(id)`, `has_in_progress()`.

### `src/gdrive/watcher.py` — `GDriveWatcher`
- Same `get_event()` contract as `FolderWatcher` (async queue of `FileEvent`).
- Takes an `is_workflow_idle: Callable[[], bool]` injected by `main.py`.
- Poll loop (default 30s):
  1. resolve watch folder ID (cached);
  2. if NOT (`is_workflow_idle()` and not `db.has_in_progress()`) → skip this
     cycle (a workflow is active);
  3. else `list_pdfs`, pick the oldest whose status is not `done`/`in_progress`;
  4. `db.mark_in_progress(id)`, `download` to `data/temp/`, enqueue
     `FileEvent(path, gdrive_file_id, gdrive_folder_id)`.
- One file per cycle — the next is picked only after the current workflow frees
  up.

## 5. Workflow integration (`src/workflow.py`, `src/models.py`, `src/main.py`)

- `FileEvent` (in `src/watcher.py`) and `WorkflowData` (in `src/models.py`) gain
  optional `gdrive_file_id` and `gdrive_folder_id`.
- `main.py` selects the watcher from `settings.watch_source`; `_run_folder_watcher`
  becomes watcher-agnostic (both expose `get_event()`), and passes
  `is_workflow_idle=lambda: self.workflow.data.state == WorkflowState.IDLE` to
  `GDriveWatcher`.
- `_handle_new_timesheet` stores the Drive origin on `WorkflowData`.
- On **COMPLETE** (`_archive_files`): if a Drive origin is set, also
  `ensure_subfolder(folder_id, "processed")` + `move(file_id, processed_id)` and
  `db.mark_done(file_id)`. Local archive is unchanged.
- On **parse failure / cancel** (`_cancel_workflow` and the parse-error path):
  if a Drive origin is set, move to `errors/` and `db.mark_error(file_id)`.
- Drive moves are best-effort and wrapped so a Drive API hiccup notifies via
  Telegram but does not crash the workflow (consistent with the project's
  "errors → Telegram, stay in state" convention).

## 6. Config (`src/config.py`) and env

New settings (pydantic `Settings`, env-overridable):

| Setting | Env | Default |
|---|---|---|
| `watch_source` | `WATCH_SOURCE` | `gdrive` |
| `gdrive_watch_path` | `GDRIVE_WATCH_PATH` | `_documents_intake/techlab/invoicing_automation` |
| `gdrive_poll_interval_seconds` | `GDRIVE_POLL_INTERVAL_SECONDS` | `30` |
| `gdrive_db_path` | `GDRIVE_DB_PATH` | `data/gdrive.db` |
| `gdrive_processed_subfolder` | `GDRIVE_PROCESSED_SUBFOLDER` | `processed` |
| `gdrive_errors_subfolder` | `GDRIVE_ERRORS_SUBFOLDER` | `errors` |

- `.env.example` + `docker-compose.yml` get these vars.
- **No new volume** — `gdrive.db` and temp downloads live under the existing
  `./data` mount. `requirements.txt` already has the Google libs (Gmail uses
  them), so no new dependency.

## 7. Auth / re-consent

- The `drive` scope is added to the existing Gmail OAuth client. Adding a scope
  invalidates the stored `token.json`; the existing interactive OAuth flow (port
  8080 callback) must be re-run once after deploy to mint a combined
  gmail+drive token. Operator step, documented in the task and
  `_TECH_DEBT/01-oauth-docker-workarounds.md`.

## 8. Testing

Mirror the repo's existing mocked-API style (the Drive `Resource` is mocked the
way Gmail is). New unit tests:

- `client.resolve_folder_path` — multi-segment name→ID descent, missing segment.
- `db` — status transitions, `has_in_progress`, dedup of a `done` id.
- `watcher` poll logic — idle-gating (no pull while busy / while `in_progress`),
  one-file-per-cycle, mark_in_progress before enqueue.
- workflow hooks — move-to-`processed` on COMPLETE, move-to-`errors` on
  failure/cancel; Drive-move failure surfaces to Telegram without crashing.
- `WATCH_SOURCE=local` path unchanged — existing tests stay green.

## 9. Component boundaries (for review)

| Unit | Does | Depends on |
|---|---|---|
| `gdrive/auth.py` | build Drive service from shared creds | `gmail/auth.py` creds, `googleapiclient` |
| `gdrive/client.py` | resolve/list/download/move in Drive | Drive `Resource` |
| `gdrive/db.py` | dedup + in-flight state | sqlite3, `data/` |
| `gdrive/watcher.py` | poll + idle-gate → `FileEvent` | client, db, `is_workflow_idle` |
| `workflow.py` (delta) | persist Drive origin; move on terminal states | client, db |

Each is independently testable with the Drive service mocked.

## 10. Publishing note

`invoice-automation` is a public subtree. This task references monorepo-internal
paths (`compose.stacks/infra/personal-assistant/...`) and the local deployment
model. Scrub per the subtree-push scrubbing rules before any public push.
