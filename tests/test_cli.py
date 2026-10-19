"""Tests for the command-line interface."""

import json
from pathlib import Path

from genesis.cli import main

DEFAULT_CONFIG = str(Path(__file__).parents[1] / "configs" / "default.yaml")


def test_run_command_succeeds_and_applies_overrides(tmp_path, capsys):
    out = tmp_path / "run"
    code = main(["run", "--config", DEFAULT_CONFIG, "--seed", "3", "--ticks", "40",
                 "--out", str(out), "--quiet"])  # fmt: skip
    assert code == 0
    meta = json.loads((out / "run.json").read_text())
    assert meta["seed"] == 3
    assert meta["ticks_run"] == 40
    assert "completed" in capsys.readouterr().out


def test_invalid_override_is_rejected_before_running(tmp_path, capsys):
    out = tmp_path / "run"
    assert main(["run", "--config", DEFAULT_CONFIG, "--seed", "-1", "--out", str(out)]) == 2
    assert "invalid configuration" in capsys.readouterr().err
    assert not out.exists()


def test_missing_config_file_is_reported(tmp_path, capsys):
    assert main(["run", "--config", str(tmp_path / "nope.yaml")]) == 2
    assert "invalid configuration" in capsys.readouterr().err


def test_non_empty_output_directory_is_refused(tmp_path, capsys):
    (tmp_path / "existing.txt").write_text("earlier results")
    assert main(["run", "--config", DEFAULT_CONFIG, "--ticks", "5", "--out", str(tmp_path)]) == 2
    assert "not empty" in capsys.readouterr().err
