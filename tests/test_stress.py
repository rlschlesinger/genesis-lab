"""Stress tests: the edges of the state space and the edges of scale (increment 3.12).

Each test here is a situation that *could* break something without any single module being
wrong: nobody alive after the first tick, a population cap of one, every gene parked on its
bound, 5,000 organisms, a 2000 x 2000 world with 20,000 food items, 50,000 ticks of ledger
rounding, 120 runs through the batch runner and into the lake. The fast ones run with the
normal suite; the ones marked ``slow`` take a minute or more and run with ``pytest -m slow``.
"""

import math
import tracemalloc
from pathlib import Path

import pytest
import yaml

from genesis.analytics.batch import run_experiment
from genesis.analytics.recorder import RunRecorder
from genesis.analytics.runs import execute_run
from genesis.analytics.spec import load_spec
from genesis.core import spatial
from genesis.core.config import SimulationConfig
from genesis.core.organism import DeathCause
from genesis.core.simulation import Simulation
from genesis.evolution.genome import gene_names
from genesis.lake.db import connect
from genesis.lake.ingest import ingest_paths

ROOT = Path(__file__).parents[1]
CONFIGS = ROOT / "configs"


def config(name: str = "default.yaml", **sections) -> SimulationConfig:
    """A config file with whole-section updates, e.g. config(food={"initial_count": 0})."""
    raw = yaml.safe_load((CONFIGS / name).read_text())
    for section, changes in sections.items():
        raw[section].update(changes)
    return SimulationConfig.model_validate(raw)


def crowd(n: int, ticks: int) -> SimulationConfig:
    """The benchmark's recipe: a population held at N with food to match."""
    return config(
        run={"max_ticks": ticks, "stop_on_extinction": False},
        organisms={"initial_count": n, "max_population": n, "initial_energy": 200.0},
        food={"max_count": max(300, n), "initial_count": max(150, n // 2),
              "regrowth_per_tick": n * 0.05},
    )  # fmt: skip


# Zero food and too little energy to pay one tick's metabolism: every founder starves on tick 0
# (organisms eat *before* paying costs, so without the empty larder they would survive).
DEAD_ON_ARRIVAL = dict(
    food={"initial_count": 0, "regrowth_per_tick": 0.0},
    organisms={"initial_energy": 0.1},
    recording={"events": ["birth", "death", "meal"]},
)


# --- Extinction on tick 0, all the way into the lake ----------------------------------------------


def test_extinction_on_tick_0_is_recorded_loaded_and_queryable(tmp_path):
    cfg = config(**DEAD_ON_ARRIVAL)
    sim = Simulation(cfg)
    summaries = sim.run()
    assert sim.tick == 1 and sim.organisms == [] and len(sim.dead) == 30
    (only,) = summaries
    assert (only.population, only.deaths, only.lineages) == (0, 30, 0)
    assert math.isnan(only.mean_energy)
    assert all(o.death_cause is DeathCause.STARVATION and o.death_tick == 0 for o in sim.dead)
    assert sim.ledger.metabolism == pytest.approx(3.0)  # 30 x 0.1: all they had

    result = execute_run(cfg, tmp_path / "run")
    assert (result.ticks_run, result.stop_reason, result.final_population) == (1, "extinction", 0)
    lines = (tmp_path / "run" / "gene_stats.csv").read_text().splitlines()
    assert len(lines) == 1 + len(gene_names()) and lines[1].endswith(",0,nan,nan,nan,nan")
    assert (tmp_path / "run" / "genomes.csv").read_text().count("\n") == 1  # header only

    (ingested,) = ingest_paths([tmp_path / "run"], tmp_path / "lake")
    assert ingested.ingested, ingested.reason
    con = connect(tmp_path / "lake")
    assert con.sql("SELECT ticks_run, final_population, organisms_ever FROM runs").fetchall() == [
        (1, 0, 30)
    ]
    assert con.sql("SELECT count(*), count(mean) FROM gene_stats").fetchall() == [(6, 0)]
    assert con.sql("SELECT count(*) FROM organisms WHERE NOT alive").fetchall() == [(30,)]
    assert con.sql("SELECT count(*) FROM events WHERE kind = 'death'").fetchall() == [(30,)]
    assert con.sql("SELECT count(*) FROM lineage_sizes").fetchall() == [(30,)]


def test_an_empty_world_keeps_ticking_when_asked_not_to_stop():
    cfg = config(
        **{**DEAD_ON_ARRIVAL, "food": {"initial_count": 0, "regrowth_per_tick": 2.0}},
        run={"stop_on_extinction": False, "max_ticks": 300},
    )
    sim = Simulation(cfg)
    summaries = sim.run()
    assert sim.tick == 300 and len(summaries) == 300 and not sim.organisms
    assert all(math.isnan(s.mean_energy) and s.population == 0 for s in summaries)
    # Food keeps arriving (and leaving the ledger's books balanced) with nobody to eat it.
    assert summaries[-1].food_count == min(300, sum(s.food_spawned for s in summaries))
    assert sim.ledger.food_spawned == pytest.approx(summaries[-1].food_count * 20.0)


# --- The population cap ---------------------------------------------------------------------------


@pytest.mark.parametrize("cap", [1, 2])
def test_a_cap_of_one_or_two_is_never_exceeded(cap):
    cfg = config(
        "evolution.yaml",
        run={"max_ticks": 1500, "seed": 3},
        organisms={"max_population": cap, "initial_count": 1},
        food={"regrowth_per_tick": 10.0},
    )
    sim = Simulation(cfg)
    summaries = sim.run()
    assert max(s.population for s in summaries) <= cap
    births = sum(s.births for s in summaries)
    # With a cap of 1 the lone founder can never make room; with a cap of 2 it has one child.
    assert births == (0 if cap == 1 else 1)


def test_a_rich_world_pins_the_population_at_the_cap():
    cfg = config(
        "evolution.yaml",
        run={"max_ticks": 400},
        organisms={"max_population": 200},
        food={"max_count": 2000, "initial_count": 2000, "regrowth_per_tick": 40.0},
    )
    sim = Simulation(cfg)
    summaries = sim.run()
    populations = [s.population for s in summaries]
    assert max(populations) == 200
    at_cap = [s for s in summaries if s.population == 200]
    assert len(at_cap) > 200
    # At the cap, births are rationed to the room deaths make, never more.
    for before, after in zip(summaries, summaries[1:], strict=False):
        assert after.births <= 200 - (before.population - after.deaths)


# --- Genes parked exactly on their bounds ---------------------------------------------------------


@pytest.mark.parametrize("bound", ["min", "max"])
def test_genes_starting_on_a_bound_stay_within_bounds_under_mutation(bound):
    raw = yaml.safe_load((CONFIGS / "evolution.yaml").read_text())
    for gene in raw["genome"].values():
        gene["initial"] = gene[bound]
    raw["run"]["max_ticks"] = 600
    sim = Simulation(SimulationConfig.model_validate(raw))
    sim.run()
    assert sim.tick == 600 and len(sim.mutation_log) > 0
    everyone = [*sim.organisms, *sim.dead]
    for name, gene in raw["genome"].items():
        values = [getattr(o.genome, name) for o in everyone]
        assert gene["min"] <= min(values) and max(values) <= gene["max"], name
    # Reflection keeps mutated genes strictly inside the range, never piled on the bound.
    changed = [e for e in sim.mutation_log if e.gene == "speed"]
    assert any(raw["genome"]["speed"]["min"] < e.after < raw["genome"]["speed"]["max"]
               for e in changed)  # fmt: skip


# --- Tiny and huge worlds -------------------------------------------------------------------------


def test_one_organism_in_a_world_three_by_two_units():
    cfg = config(
        run={"max_ticks": 500},
        world={"width": 3.0, "height": 2.0},
        food={"eat_radius": 2.0, "max_count": 5, "initial_count": 5, "regrowth_per_tick": 1.0},
        organisms={"initial_count": 1, "max_population": 1},
    )
    sim = Simulation(cfg)
    summaries = sim.run()
    assert sim.tick == 500 and len(sim.organisms) == 1
    (org,) = sim.organisms
    assert 0.0 <= org.x <= 3.0 and 0.0 <= org.y <= 2.0
    assert sum(s.food_eaten for s in summaries) > 400  # it can reach anything in this world


def test_a_huge_world_with_twenty_thousand_food_items_matches_all_pairs(monkeypatch):
    cfg = config(
        run={"max_ticks": 8, "stop_on_extinction": False},
        world={"width": 2000.0, "height": 2000.0},
        food={"max_count": 20000, "initial_count": 20000, "regrowth_per_tick": 50.0},
        organisms={"initial_count": 300, "max_population": 300},
    )
    with_grid = Simulation(cfg)
    with_grid.run()
    monkeypatch.setattr(spatial, "DENSE_PAIR_LIMIT", float("inf"))
    all_pairs = Simulation(cfg)
    all_pairs.run()
    assert with_grid.state_digest() == all_pairs.state_digest()


# --- Scale ----------------------------------------------------------------------------------------


def test_five_thousand_organisms_run_record_and_balance():
    cfg = crowd(5000, ticks=5)
    sim = Simulation(cfg)
    recorder = RunRecorder(genome_snapshot_every=5, events=("birth", "death", "meal"))
    while not sim.finished:
        recorder.observe(sim, sim.step())  # the ledger check inside step() must hold
    assert sim.tick == 5 and len(sim.organisms) == 5000
    assert len(recorder.ticks) == 5 and len(recorder.genomes) == 2 * 5000
    assert sum(e["kind"] == "meal" for e in recorder.events) == sum(
        r["food_eaten"] for r in recorder.ticks
    )


def test_three_thousand_organisms_and_food_items_need_little_memory():
    # All-pairs at this size would build several 3000 x 3000 tables (72 MB each); the grid
    # must not. Measured on the Python heap, which excludes NumPy's own small overheads.
    cfg = crowd(3000, ticks=3)
    tracemalloc.start()
    try:
        sim = Simulation(cfg)
        assert sim.world.food.count == 1500  # 3000 x 1500 pairs on the first tick
        baseline = tracemalloc.get_traced_memory()[0]
        sim.run()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert (peak - baseline) < 60e6, f"peak {peak - baseline:.0f} bytes above the start"


# --- Slow: minutes, run with `pytest -m slow` -----------------------------------------------------


@pytest.mark.slow
def test_ledger_rounding_stays_far_below_tolerance_over_fifty_thousand_ticks():
    sim = Simulation(config("evolution.yaml", run={"max_ticks": 50_000}))
    worst = 0.0
    while not sim.finished:
        sim.step()
        if sim.tick % 1000 == 0:
            drift = abs(sim.energy_stock() - sim.ledger.expected_stock)
            worst = max(worst, drift / sim.ledger.tolerance)
    assert sim.tick == 50_000
    # Measured 2026-10-19: worst ratio 0.002. Fifteen times that still leaves a wide margin
    # below 1.0 (the EnergyLedgerError line) and would signal a real change in rounding.
    assert worst < 0.03, f"drift reached {worst:.3f} of the tolerance"


@pytest.mark.slow
def test_a_batch_of_one_hundred_and_twenty_runs_loads_into_the_lake(tmp_path):
    spec = {
        "experiment_id": "E999",
        "title": "stress: 120 short runs",
        "definition": "docs/experiments/E999-does-not-exist.md",
        "base_config": "configs/evolution.yaml",
        "base_changes": {"run.max_ticks": 300},
        "conditions": [{"label": "a"}, {"label": "b", "changes": {"food.regrowth_per_tick": 1.0}}],
        "seeds": {"first": 100, "count": 60},
        "output": str(tmp_path / "out"),
    }
    path = tmp_path / "E999.yaml"
    path.write_text(yaml.safe_dump(spec))
    outcomes = run_experiment(load_spec(path, ROOT), workers=3, lake=tmp_path / "lake", root=ROOT)
    assert len(outcomes) == 120 and all(o.ok for o in outcomes)
    con = connect(tmp_path / "lake")
    assert con.sql("SELECT count(*) FROM completed_runs").fetchall() == [(120,)]
    assert con.sql("SELECT count(*) FROM ticks").fetchall()[0][0] <= 120 * 300
    by_condition = con.sql(
        "SELECT condition, count(*) FROM completed_runs GROUP BY condition ORDER BY condition"
    ).fetchall()
    assert by_condition == [("a", 60), ("b", 60)]
    means = con.sql(
        "SELECT gene, count(*) FROM settled_gene_means(200, 299) GROUP BY gene ORDER BY gene"
    ).fetchall()
    assert [g for g, _ in means] == sorted(gene_names())
    assert all(count <= 120 for _, count in means)
