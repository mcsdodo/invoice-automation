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
