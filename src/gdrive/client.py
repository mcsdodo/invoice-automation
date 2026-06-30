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
