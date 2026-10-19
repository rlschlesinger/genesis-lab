"""Tests for the command-line interface."""

import json
from pathlib import Path

from genesis import cli
from genesis.cli import main
from genesis.core.simulation import Simulation

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


def test_overwrite_flag_allows_reusing_the_directory(tmp_path):
    args = ["run", "--config", DEFAULT_CONFIG, "--ticks", "5", "--out", str(tmp_path), "--quiet"]
    assert main(args) == 0
    assert main(args) == 2
    assert main([*args, "--overwrite"]) == 0


def test_progress_goes_to_stderr_every_n_ticks_unless_quiet(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli, "PROGRESS_EVERY", 10)
    args = ["run", "--config", DEFAULT_CONFIG, "--ticks", "25", "--out", str(tmp_path / "a")]
    assert main(args) == 0
    err = capsys.readouterr().err
    assert "tick     10:" in err and "tick     20:" in err
    assert "tick     25:" not in err  # only on multiples of PROGRESS_EVERY
    assert main([*args[:-1], str(tmp_path / "b"), "--quiet"]) == 0
    assert capsys.readouterr().err == ""


def test_failure_during_the_run_exits_1_and_points_at_the_record(tmp_path, capsys, monkeypatch):
    def failing_step(self):
        raise RuntimeError("boom")

    monkeypatch.setattr(Simulation, "step", failing_step)
    out = tmp_path / "run"
    assert main(["run", "--config", DEFAULT_CONFIG, "--out", str(out), "--quiet"]) == 1
    err = capsys.readouterr().err
    assert "run failed: boom" in err and "run.json" in err
    assert json.loads((out / "run.json").read_text())["status"] == "failed"
