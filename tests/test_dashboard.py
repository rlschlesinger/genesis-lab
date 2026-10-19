"""Tests for experiment dashboards: built from the lake, runs vs summaries, robust to odd data."""

import json
import shutil
from pathlib import Path

import pytest

from genesis.analytics.runs import execute_run
from genesis.cli import main
from genesis.core.config import SimulationConfig, load_config
from genesis.lake.ingest import ingest_paths
from genesis.report import dashboard_figures as figures
from genesis.report.dashboard import write_dashboard
from genesis.report.dashboard_data import load_experiment

ROOT = Path(__file__).parents[1]


def make_config(seed: int, **food) -> SimulationConfig:
    raw = load_config(ROOT / "configs" / "evolution.yaml").model_dump()
    raw["run"].update(max_ticks=300, seed=seed)
    raw["food"].update(food)
    return SimulationConfig.model_validate(raw)


@pytest.fixture(scope="module")
def lake(tmp_path_factory) -> Path:
    """E900: 'plenty' and 'scarce' x 3 seeds, one run that starves, one failed run."""
    runs = tmp_path_factory.mktemp("runs")
    for condition, food in (("plenty", {}), ("scarce", {"regrowth_per_tick": 1.0})):
        for seed in (1, 2, 3):
            execute_run(
                make_config(seed, **food),
                runs / f"{condition}-s{seed}",
                experiment_id="E900",
                condition=condition,
            )
    execute_run(
        make_config(4, regrowth_per_tick=0.0, initial_count=0),
        runs / "scarce-s4",
        experiment_id="E900",
        condition="scarce",
    )
    failed = runs / "failed"
    failed.mkdir()
    (failed / "run.json").write_text(
        json.dumps(
            {
                "run_id": "R-failed",
                "experiment_id": "E900",
                "condition": "plenty",
                "status": "failed",
                "seed": 9,
                "config": {},
                "error": "boom",
                "started_at": "2026-10-19T00:00:00+00:00",
            }
        )
    )
    lake = tmp_path_factory.mktemp("lake")
    assert all(r.ingested for r in ingest_paths([runs], lake))
    return lake


@pytest.fixture(scope="module")
def data(lake):
    return load_experiment("E900", lake, window=(200, 299))


def test_loads_completed_runs_and_counts_the_failed_one(data):
    assert len(data.runs) == 8 and len(data.completed) == 7
    assert data.conditions == ["plenty", "scarce"]  # no spec file: sorted
    assert set(data.population["run_id"]) == set(data.completed["run_id"])


def test_one_faint_line_per_run_and_one_bold_median_per_condition(data):
    fig = figures.population_figure(data)
    faint = [t for t in fig.data if t.opacity == figures.RUN_OPACITY]
    bold = [t for t in fig.data if t.showlegend]
    assert len(faint) == 7  # every completed run, individually
    assert [t.name for t in bold] == ["plenty", "scarce"]
    assert all(t.line.width > faint[0].line.width for t in bold)


def test_summary_hover_reports_how_many_runs_it_is_based_on(data):
    fig = figures.population_figure(data)
    scarce = next(t for t in fig.data if t.name == "scarce")
    counts = list(scarce.customdata)
    assert counts[0] == 4 and counts[-1] < 4  # the starving run drops out: survivorship


def test_settled_values_exclude_runs_extinct_in_the_window(data):
    assert len(data.settled) == 6  # 7 completed, minus the one that starved before tick 200
    fig = figures.settled_figure(data)
    dots = [t for t in fig.data if t.mode == "markers" and t.marker.symbol != "diamond"]
    assert sum(len(t.y) for t in dots) == 6 * len(data.evolving_genes)


def test_dashboard_page(lake, tmp_path):
    out = write_dashboard(
        "E900", lake, tmp_path / "d.html", window=(200, 299), pairs=[("scarce", "plenty")]
    )
    html = out.read_text()
    for text in (
        "E900",
        "Population",
        "Gene trends",
        "Settled values",
        "Paired differences",
        "survivorship",
    ):
        assert text in html, text
    assert "<script src=" not in html and "<link" not in html  # offline


def test_dashboard_is_deterministic(lake, tmp_path):
    a = write_dashboard("E900", lake, tmp_path / "a.html", pairs=[("scarce", "plenty")])
    b = write_dashboard("E900", lake, tmp_path / "b.html", pairs=[("scarce", "plenty")])
    assert a.read_bytes() == b.read_bytes()


def test_paired_panel_only_when_asked(lake, tmp_path):
    html = write_dashboard("E900", lake, tmp_path / "d.html").read_text()
    assert "Paired differences" not in html


def test_without_gene_data_only_population_is_shown(lake, tmp_path):
    copy = tmp_path / "lake"
    shutil.copytree(lake, copy)
    shutil.rmtree(copy / "gene_stats")  # like a Milestone 1 experiment
    html = write_dashboard("E900", copy, tmp_path / "d.html").read_text()
    assert "Population" in html and "Gene trends" not in html and "Settled values" not in html


def test_errors_are_clear(lake, tmp_path):
    with pytest.raises(ValueError, match="no runs of E777"):
        write_dashboard("E777", lake, tmp_path / "x.html")
    with pytest.raises(ValueError, match="unknown condition"):
        write_dashboard("E900", lake, tmp_path / "x.html", pairs=[("plenty", "nope")])


def test_dashboard_command(lake, tmp_path, capsys):
    out = tmp_path / "cli.html"
    assert (
        main(
            [
                "dashboard",
                "E900",
                "--lake",
                str(lake),
                "--out",
                str(out),
                "--compare",
                "scarce:plenty",
                "--window",
                "200",
                "299",
            ]
        )
        == 0
    )
    assert out.exists() and "dashboard written" in capsys.readouterr().out
    assert main(["dashboard", "E900", "--lake", str(lake), "--compare", "nocolon"]) == 2
    assert main(["dashboard", "E777", "--lake", str(lake)]) == 2
