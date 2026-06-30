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
