**Date:** 2026-06-30
**Subject:** Watch a Google Drive folder for timesheets instead of (only) a local folder
**Status:** Planning

## Summary

Today the service detects new timesheet PDFs with a local folder watcher
(`src/watcher.py`, `watchdog.PollingObserver` over a bind-mounted directory).
We want it to instead watch the Google Drive folder
`_documents_intake/techlab/invoicing_automation`, reusing the *intake pattern*
from the `personal-assistant` project (resolve folder by name → ID, dedup new
files, move processed files out of the way).

The local watcher stays available as a selectable fallback.

## Requirements

1. **GDrive as default input.** A new watcher polls the Drive folder
   `_documents_intake/techlab/invoicing_automation` for new PDFs and feeds them
   into the existing `WorkflowCoordinator` exactly like the local watcher does
   (same `new_timesheet` event, same state machine, Telegram, email — unchanged).

2. **Selectable source.** `WATCH_SOURCE=gdrive|local` (default `gdrive`). When
   `local`, behaviour is identical to today; existing tests stay green.

3. **Direct Google API in Python.** Use `google-api-python-client` directly
   (NOT personal-assistant's `gmail-mcp` server). Reuse the *pattern*, not the
   infrastructure.

4. **Reuse the existing OAuth client.** Add the Drive scope to the service's
   existing Gmail OAuth client (`config/credentials.json` / `config/token.json`,
   `src/gmail/auth.py`). One credential, one token, one re-consent. No second
   OAuth client, no service account.

5. **Move processed files in Drive.** Mirror the local archive behaviour: on
   workflow **COMPLETE**, move the Drive file into a `processed/` subfolder; on
   parse failure / cancel, move it to `errors/`. This requires the full `drive`
   scope (Drive OAuth scopes are not folder-scoped, and `drive.file` cannot see
   files the app did not create).

6. **Single-tenant semantics preserved.** The service handles one timesheet at a
   time (the `IDLE` guard in `WorkflowCoordinator`). The GDrive watcher must not
   pull a new file while a workflow is in flight, and must not lose a file by
   marking it "seen" before the workflow accepts it.

7. **No new container, no new volume.** Stays a single service; the dedup DB and
   temporary downloads live under the existing `./data` mount.

## Out of scope

- Uploading any output (merged PDF, invoice) back to Drive — outputs continue to
  go out by email and to the local archive as today.
- Multi-owner / multi-bucket scanning (personal-assistant's batch-of-N design).
  This service watches exactly one folder.
- Changing the workflow state machine, Telegram approvals, or email logic.

## Decisions (locked with user 2026-06-30)

| Decision | Choice |
|---|---|
| Google access | Direct `google-api-python-client` in Python |
| Watch source | Keep both; `WATCH_SOURCE=gdrive` default, `local` fallback |
| Processed files | Move to `processed/` in Drive on COMPLETE, `errors/` on failure |
| OAuth | Reuse existing Gmail OAuth client; add `drive` scope; re-consent once |

## Notes / risks

- **Re-consent required.** Adding the `drive` scope invalidates the current
  `token.json`. The existing interactive OAuth flow (port 8080 callback) must be
  re-run once after deploy. See `_TECH_DEBT/01-oauth-docker-workarounds.md`.
- The `processed/`/`errors/` move is the real dedup (file leaves the watch
  folder), exactly like the local flow moves the file out of `incoming/`. The
  SQLite table is the in-flight guard + audit, not the sole dedup.

## Source pattern reference (personal-assistant)

Read for the porting target (TypeScript, do not copy verbatim):
- `compose.stacks/infra/personal-assistant/pollers/gdrive-poller/src/main.ts`
  — `resolveWatchFolders()` (name→ID descent), `pollGdrive()`, `pollCycle()`.
- `compose.stacks/infra/personal-assistant/pollers/lib/gdrive-db.ts`
  — SQLite dedup table (`id` PK, `INSERT OR IGNORE`, `fileExists`).
- Move-to-`processed`/`errors`:
  `compose.stacks/infra/personal-assistant/claude-code/channels/invoice/intake-worker.ts`
  (`moveGdriveFile`) and `.../postprocess-service.ts`.
