"""Tests for the atomic file writers: a failed write leaves no trace and no damage."""

import json

import pytest

from genesis.analytics.storage import write_csv, write_json


def test_write_json_round_trips(tmp_path):
    path = tmp_path / "meta.json"
    write_json(path, {"a": 1, "b": [1.5, None]})
    assert json.loads(path.read_text()) == {"a": 1, "b": [1.5, None]}
    assert path.read_text().endswith("\n")
    assert not list(tmp_path.glob("*.tmp"))


def test_write_csv_uses_unix_line_endings_and_empty_cells_for_none(tmp_path):
    path = tmp_path / "t.csv"
    write_csv(path, ["x", "y"], [{"x": 1, "y": None}, {"x": 0.1, "y": "s"}])
    assert path.read_bytes() == b"x,y\n1,\n0.1,s\n"


def test_failed_write_keeps_the_old_file_and_leaves_no_temp_file(tmp_path):
    path = tmp_path / "meta.json"
    write_json(path, {"status": "running"})
    with pytest.raises(TypeError):  # a set is not JSON-serialisable
        write_json(path, {"status": {"not", "json"}})
    assert json.loads(path.read_text()) == {"status": "running"}  # untouched
    assert not list(tmp_path.glob("*.tmp"))


def test_csv_row_with_an_unknown_column_is_rejected_before_anything_is_written(tmp_path):
    path = tmp_path / "t.csv"
    with pytest.raises(ValueError):
        write_csv(path, ["x"], [{"x": 1, "typo": 2}])
    assert not path.exists()
    assert not list(tmp_path.glob("*.tmp"))
