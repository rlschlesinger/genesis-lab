"""Tests for `genesis report`: built from files only, deterministic, robust to odd runs."""

import json
from pathlib import Path

import pytest

from genesis.analytics.runs import execute_run
from genesis.cli import main
from genesis.core.config import SimulationConfig, load_config
from genesis.report import write_report
from genesis.report.data import downsample, load_run

CONFIGS = Path(__file__).parents[1] / "configs"


def config(name="evolution.yaml", **changes) -> SimulationConfig:
    raw = load_config(CONFIGS / name).model_dump()
    raw["run"]["max_ticks"] = 400
    for path, value in changes.items():
        *parents, leaf = path.split(".")
        section = raw
        for key in parents:
            section = section[key]
        section[leaf] = value
    return SimulationConfig.model_validate(raw)


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("evo")
    execute_run(config(), out)
    return out


def test_report_contains_every_section_and_gene(run_dir):
    html = write_report(run_dir).read_text()
    meta = json.loads((run_dir / "run.json").read_text())
    assert meta["run_id"] in html
    for section in ("Population", "Gene trends", "Distributions", "Mutations"):
        assert section in html
    for gene in meta["config"]["genome"]:
        assert gene in html
    for div_id in ("population", "gene-trends", "distributions"):
        assert f'id="{div_id}"' in html


def test_report_is_self_contained(run_dir):
    # Checks our markup, not Plotly's bundled library code (which mentions map-tile font URLs
    # for chart types we don't use; they are never fetched).
    html = write_report(run_dir).read_text()
    assert "<script src=" not in html  # no external scripts
    assert "<link" not in html  # no external stylesheets or web fonts
    assert "@import" not in html  # no CSS imports
    # One <script> for the Plotly library, plus one small inline script per chart.
    assert html.count("<script>") == 1 + html.count('class="chart"')


def test_report_is_deterministic(run_dir, tmp_path):
    a = write_report(run_dir, tmp_path / "a.html").read_bytes()
    b = write_report(run_dir, tmp_path / "b.html").read_bytes()
    assert a == b


def test_report_uses_only_recorded_files(run_dir, tmp_path):
    # Copy just the recorded files elsewhere: the report must build from them alone.
    copy = tmp_path / "copy"
    copy.mkdir()
    for f in run_dir.iterdir():
        if f.suffix in {".csv", ".json"}:
            (copy / f.name).write_bytes(f.read_bytes())
    assert write_report(copy).exists()


def test_report_for_a_run_without_mutation(tmp_path):
    execute_run(config("default.yaml"), tmp_path)
    html = write_report(tmp_path).read_text()
    assert "without mutation" in html


def test_report_for_a_run_that_went_extinct(tmp_path):
    execute_run(config("default.yaml", **{"food.initial_count": 0,
                                           "food.regrowth_per_tick": 0.0}), tmp_path)  # fmt: skip
    meta = json.loads((tmp_path / "run.json").read_text())
    assert meta["stop_reason"] == "extinction"
    assert write_report(tmp_path).exists()


def test_missing_files_give_a_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="is missing"):
        load_run(tmp_path)


def test_failed_run_is_refused(run_dir, tmp_path):
    copy = tmp_path / "failed"
    copy.mkdir()
    for f in run_dir.iterdir():
        (copy / f.name).write_bytes(f.read_bytes())
    meta = json.loads((copy / "run.json").read_text()) | {"status": "failed"}
    (copy / "run.json").write_text(json.dumps(meta))
    with pytest.raises(ValueError, match="failed"):
        load_run(copy)


def test_downsample_keeps_first_and_last_and_bounds_size():
    rows = [{"tick": t} for t in range(20_001)]
    kept = downsample(rows, max_points=2000)
    assert kept[0]["tick"] == 0 and kept[-1]["tick"] == 20_000
    assert len(kept) <= 2001
    assert downsample(rows[:50], max_points=2000) == rows[:50]


def test_cli_report_command(run_dir, tmp_path, capsys):
    out = tmp_path / "r.html"
    assert main(["report", str(run_dir), "--out", str(out)]) == 0
    assert out.exists() and "report written" in capsys.readouterr().out
    assert main(["report", str(tmp_path / "nope")]) == 2
