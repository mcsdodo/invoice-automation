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
