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


# --- Sampling (ticks_every) ---------------------------------------------------------------


def record(config, **recorder_kwargs) -> tuple[Simulation, RunRecorder]:
    sim = Simulation(config)
    recorder = RunRecorder(genome_snapshot_every=50, **recorder_kwargs)
    while not sim.finished:
        recorder.observe(sim, sim.step())
    return sim, recorder


def test_sampled_rows_are_every_nth_tick_plus_the_final_one():
    _, rec = record(evolution_config(max_ticks=100), ticks_every=7)
    ticks = [r["tick"] for r in rec.ticks]
    assert ticks == [*range(0, 100, 7), 99]
    assert {r["tick"] for r in rec.gene_stats} == set(ticks)


def test_flow_totals_are_the_same_at_any_interval():
    # Flows (births, deaths, meals, mutations) are summed between rows, so totals never
    # depend on the sampling interval. Plain sampling would silently drop most of them.
    config = evolution_config(max_ticks=400)
    _, every_tick = record(config, ticks_every=1)
    _, sampled = record(config, ticks_every=13)
    for field in ("births", "deaths", "food_spawned", "food_eaten", "mutations"):
        assert sum(r[field] for r in sampled.ticks) == sum(r[field] for r in every_tick.ticks), (
            field
        )


def test_stock_columns_are_snapshots_of_the_recorded_tick():
    config = evolution_config(max_ticks=200)
    _, every_tick = record(config, ticks_every=1)
    _, sampled = record(config, ticks_every=10)
    full = {r["tick"]: r for r in every_tick.ticks}
    for row in sampled.ticks:
        for field in ("population", "food_count", "lineages"):
            assert row[field] == full[row["tick"]][field], (field, row["tick"])


def test_sampling_never_changes_the_simulation():
    config = evolution_config(max_ticks=300)
    a, _ = record(config, ticks_every=1)
    b, _ = record(config, ticks_every=25)
    assert a.state_digest() == b.state_digest()


# --- Event log ----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def logged():
    return record(evolution_config(max_ticks=600), events=("birth", "death", "meal"))


def test_event_counts_match_the_tick_totals(logged):
    _, rec = logged
    by_kind = {k: sum(e["kind"] == k for e in rec.events) for k in ("birth", "death", "meal")}
    assert by_kind["birth"] == sum(r["births"] for r in rec.ticks) > 0
    assert by_kind["death"] == sum(r["deaths"] for r in rec.ticks) > 0
    assert by_kind["meal"] == sum(r["food_eaten"] for r in rec.ticks) > 0


def test_birth_and_death_events_agree_with_organism_records(logged):
    sim, rec = logged
    everyone = {o.id: o for o in [*sim.organisms, *sim.dead]}
    for e in rec.events:
        org = everyone[e["organism_id"]]
        if e["kind"] == "birth":
            assert e["other_id"] == org.parent_id and e["tick"] == org.birth_tick
        elif e["kind"] == "death":
            assert e["tick"] == org.death_tick and e["detail"] == org.death_cause


def test_events_are_numbered_in_order_within_each_tick(logged):
    _, rec = logged
    by_tick: dict[int, list[int]] = {}
    for e in rec.events:
        by_tick.setdefault(e["tick"], []).append(e["seq"])
    assert all(seqs == list(range(len(seqs))) for seqs in by_tick.values())


def test_meals_then_deaths_then_births_within_a_tick(logged):
    # The order things happen in a tick (steps 5, 6, 7).
    _, rec = logged
    rank = {"meal": 0, "death": 1, "birth": 2}
    by_tick: dict[int, list[int]] = {}
    for e in rec.events:
        by_tick.setdefault(e["tick"], []).append(rank[e["kind"]])
    assert all(ranks == sorted(ranks) for ranks in by_tick.values())


def test_only_requested_event_kinds_are_kept():
    _, rec = record(evolution_config(max_ticks=300), events=("death",))
    assert rec.events and {e["kind"] for e in rec.events} == {"death"}


def test_logging_events_never_changes_the_simulation():
    config = evolution_config(max_ticks=300)
    a, _ = record(config)
    b, _ = record(config, events=("birth", "death", "meal"))
    assert a.state_digest() == b.state_digest()
