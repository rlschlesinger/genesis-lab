"""Tests for RunRecorder and the gene statistics / genome snapshot files."""

import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path

import pytest

from genesis.analytics.recorder import RunRecorder, gene_stat_rows
from genesis.analytics.runs import execute_run
from genesis.core.config import SimulationConfig, load_config
from genesis.core.simulation import Simulation
from genesis.evolution.genome import gene_names

CONFIGS = Path(__file__).parents[2] / "configs"


def evolution_config(**run) -> SimulationConfig:
    raw = load_config(CONFIGS / "evolution.yaml").model_dump()
    raw["run"].update(run)
    return SimulationConfig.model_validate(raw)


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def test_gene_stat_rows_known_values():
    rows = gene_stat_rows(7, {"speed": [1.0, 2.0, 3.0, 4.0]})
    assert rows == [{"tick": 7, "gene": "speed", "n": 4, "mean": 2.5,
                     "sd": statistics.pstdev([1, 2, 3, 4]), "min": 1.0, "max": 4.0}]  # fmt: skip


def test_gene_stat_rows_empty_population_is_nan_not_zero():
    (row,) = gene_stat_rows(3, {"speed": []})
    assert row["n"] == 0
    assert all(math.isnan(row[k]) for k in ("mean", "sd", "min", "max"))


def test_snapshots_on_the_interval_and_the_final_tick():
    sim = Simulation(evolution_config(max_ticks=237))
    recorder = RunRecorder(genome_snapshot_every=50)
    while not sim.finished:
        recorder.observe(sim, sim.step())
    snapshot_ticks = sorted({r["tick"] for r in recorder.genomes})
    assert snapshot_ticks == [0, 50, 100, 150, 200, 236]


def test_one_stats_row_per_tick_per_gene():
    sim = Simulation(evolution_config(max_ticks=40))
    recorder = RunRecorder(genome_snapshot_every=10)
    while not sim.finished:
        recorder.observe(sim, sim.step())
    assert len(recorder.gene_stats) == 40 * len(gene_names())


def test_recorder_does_not_change_results():
    plain = Simulation(evolution_config(max_ticks=300))
    plain.run()
    watched = Simulation(evolution_config(max_ticks=300))
    recorder = RunRecorder(genome_snapshot_every=1)
    while not watched.finished:
        recorder.observe(watched, watched.step())
    assert plain.state_digest() == watched.state_digest()


def test_invalid_interval_rejected():
    with pytest.raises(ValueError):
        RunRecorder(genome_snapshot_every=0)


@pytest.fixture(scope="module")
def recorded_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("run")
    execute_run(evolution_config(max_ticks=1200), out)
    return out


def test_statistics_match_a_recount_from_the_raw_genomes(recorded_run):
    # The two files are produced separately; for every snapshot tick, recomputing the
    # statistics from genomes.csv must reproduce gene_stats.csv exactly.
    stats = {(int(r["tick"]), r["gene"]): r for r in read_csv(recorded_run / "gene_stats.csv")}
    snapshots = defaultdict(list)
    for row in read_csv(recorded_run / "genomes.csv"):
        snapshots[int(row["tick"])].append(row)
    assert len(snapshots) >= 20
    for tick, rows in snapshots.items():
        for gene in gene_names():
            values = [float(r[f"gene_{gene}"]) for r in rows]
            recorded = stats[(tick, gene)]
            assert int(recorded["n"]) == len(values)
            assert float(recorded["mean"]) == pytest.approx(statistics.fmean(values), rel=1e-12)
            assert float(recorded["sd"]) == pytest.approx(statistics.pstdev(values), abs=1e-12)
            assert float(recorded["min"]) == min(values)
            assert float(recorded["max"]) == max(values)


def test_stats_n_matches_population_every_tick(recorded_run):
    population = {
        int(r["tick"]): int(r["population"]) for r in read_csv(recorded_run / "ticks.csv")
    }
    for row in read_csv(recorded_run / "gene_stats.csv"):
        assert int(row["n"]) == population[int(row["tick"])]


def test_frozen_gene_has_zero_spread(recorded_run):
    rows = [r for r in read_csv(recorded_run / "gene_stats.csv") if r["gene"] == "max_turn"]
    assert all(float(r["sd"]) == 0.0 and float(r["mean"]) == 0.5 for r in rows)
