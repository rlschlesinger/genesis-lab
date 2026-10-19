"""Tests for behaviour.csv and brains.csv: known values for the rule-based controllers, brain
diversity and drift, an independent recount, and the trip into the lake."""

import csv
import math
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pytest

from genesis.analytics.behaviour import BEHAVIOUR_FIELDS, behaviour_row
from genesis.analytics.metrics import BRAIN_FIELDS
from genesis.analytics.runs import execute_run
from genesis.core.config import SimulationConfig, load_config
from genesis.core.simulation import Decision, Simulation
from genesis.intelligence.controllers import Actions
from genesis.intelligence.sensors import Observations
from genesis.lake.db import connect
from genesis.lake.ingest import ingest_run

CONFIGS = Path(__file__).parents[2] / "configs"


def config(name="neural.yaml", ticks=400, **organisms) -> SimulationConfig:
    raw = load_config(CONFIGS / name).model_dump()
    raw["run"]["max_ticks"] = ticks
    raw["organisms"] |= organisms
    if raw["organisms"]["controller"] != "neural":
        raw.pop("brain", None)
    return SimulationConfig.model_validate(raw)


def rows(path: Path) -> list[dict]:
    with path.open(newline="") as f:
        return [{k: float(v) for k, v in r.items()} for r in csv.DictReader(f)]


@pytest.fixture(scope="module")
def runs(tmp_path_factory) -> dict[str, Path]:
    out = {}
    for controller in ("neural", "nearest_food_seeker", "random_walk"):
        folder = tmp_path_factory.mktemp(controller)
        execute_run(config(controller=controller), folder)
        out[controller] = folder
    return out


# --- known values ---------------------------------------------------------------------------


def test_one_behaviour_row_per_tick_row(runs):
    for folder in runs.values():
        ticks = rows(folder / "ticks.csv")
        behaviour = rows(folder / "behaviour.csv")
        assert [r["tick"] for r in behaviour] == [r["tick"] for r in ticks]


def test_food_seeker_always_turns_toward_food_at_full_throttle(runs):
    behaviour = rows(runs["nearest_food_seeker"] / "behaviour.csv")
    judged = [r["toward_food"] for r in behaviour if not math.isnan(r["toward_food"])]
    assert judged and all(v == 1.0 for v in judged)
    assert all(r["mean_throttle"] == 1.0 for r in behaviour)


def test_random_walk_turns_toward_food_about_half_the_time(runs):
    behaviour = rows(runs["random_walk"] / "behaviour.csv")
    seen = sum(r["seeing_food"] for r in behaviour)
    toward = sum(r["toward_food"] * r["seeing_food"] for r in behaviour if r["seeing_food"])
    assert toward / seen == pytest.approx(0.5, abs=0.05)


def test_rule_based_runs_have_no_brain_columns_or_brain_rows(runs):
    for controller in ("nearest_food_seeker", "random_walk"):
        behaviour = rows(runs[controller] / "behaviour.csv")
        assert all(math.isnan(r["weight_sd"]) and math.isnan(r["weight_drift"]) for r in behaviour)
        assert rows(runs[controller] / "brains.csv") == []


def test_brain_drift_starts_at_zero_and_grows(runs):
    behaviour = rows(runs["neural"] / "behaviour.csv")
    assert behaviour[0]["weight_drift"] == 0.0  # no births yet on tick 0
    assert behaviour[0]["weight_sd"] == pytest.approx(0.5, rel=0.15)  # random founders
    assert behaviour[-1]["weight_drift"] > 0.01


# --- brains.csv -----------------------------------------------------------------------------


def test_brains_csv_holds_every_organisms_weights_exactly():
    cfg = config(ticks=200)
    sim = Simulation(cfg)
    sim.run()
    everyone = {o.id: o for o in [*sim.organisms, *sim.dead]}
    with tempfile.TemporaryDirectory() as folder:
        execute_run(cfg, Path(folder))
        with (Path(folder) / "brains.csv").open(newline="") as f:
            reader = csv.reader(f)
            assert next(reader) == BRAIN_FIELDS
            brain_rows = list(reader)
    assert len(brain_rows) == len(everyone)
    for row in brain_rows:
        expected = everyone[int(row[0])].brain.to_vector()
        assert [float(v) for v in row[1:]] == expected.tolist()  # exact: repr round-trips


# --- independent recount --------------------------------------------------------------------


def test_toward_food_matches_a_hand_count():
    # Three organisms see food: bearings +1.0, -0.5, +0.2 rad; turns +0.3, +0.3, +0.5.
    #  #1 turns left toward food on its left: |1.0 - 0.3| = 0.7 < 1.0  -> toward
    #  #2 turns left, food on its right:      |-0.5 - 0.3| = 0.8 > 0.5 -> away
    #  #3 overshoots: |0.2 - 0.5| = 0.3 > 0.2                          -> away
    # A fourth sees nothing. Max turn 0.5 for all; throttles 1, 0.5, 0, 0.5.
    obs = Observations(
        food_found=np.array([True, True, True, False]),
        food_distance=np.array([5.0, 5.0, 5.0, np.inf]),
        food_bearing=np.array([1.0, -0.5, 0.2, 0.0]),
        energy=np.ones(4),
    )
    decision = Decision(
        obs, Actions(np.array([0.3, 0.3, 0.5, -0.9]), np.array([1, 0.5, 0, 0.5])), np.full(4, 0.5)
    )
    row = behaviour_row(7, decision, [], {})
    assert list(row) == BEHAVIOUR_FIELDS
    assert (row["tick"], row["n"], row["seeing_food"]) == (7, 4, 3)
    assert row["toward_food"] == pytest.approx(1 / 3)
    # |turn| as applied (-0.9 clipped to -0.5) over max_turn: 0.6, 0.6, 1.0, 1.0 -> 0.8
    assert row["mean_turn"] == pytest.approx(0.8)
    assert row["mean_throttle"] == pytest.approx(0.5)


def test_toward_food_wraps_the_bearing_past_straight_behind():
    """Food almost directly behind on the right (bearing -3.0 rad). Turning left by 0.5 puts
    it at -3.5 rad, which wrapped is +2.78 rad: 159 degrees to the left, nearer dead ahead
    than 172 degrees to the right was. Without wrapping, |-3.5| > 3.0 would count as away."""
    obs = Observations(
        food_found=np.array([True, True]),
        food_distance=np.array([5.0, 5.0]),
        food_bearing=np.array([-3.0, 3.0]),
        energy=np.ones(2),
    )
    decision = Decision(obs, Actions(np.array([0.5, -0.5]), np.ones(2)), np.full(2, 0.5))
    assert behaviour_row(0, decision, [], {})["toward_food"] == 1.0


def test_empty_population_row_has_no_values():
    row = behaviour_row(3, None, [], {})
    assert (row["n"], row["seeing_food"]) == (0, 0)
    assert all(math.isnan(row[c]) for c in BEHAVIOUR_FIELDS[3:])


# --- into the lake --------------------------------------------------------------------------


def test_neural_run_round_trips_through_the_lake(runs, tmp_path):
    result = ingest_run(runs["neural"], tmp_path)
    assert result.ingested, result.reason
    con = connect(tmp_path)
    n_brains, n_organisms = con.execute(
        "SELECT (SELECT count(*) FROM brains), (SELECT count(*) FROM organisms)"
    ).fetchone()
    assert n_brains == n_organisms > 30
    has_brains, rate = con.execute(
        "SELECT has_brains, brain_mutation_rate FROM run_params"
    ).fetchone()
    assert has_brains and rate == 0.1
    last = con.execute("SELECT weight_drift FROM behaviour ORDER BY tick DESC LIMIT 1").fetchone()
    assert last[0] == pytest.approx(rows(runs["neural"] / "behaviour.csv")[-1]["weight_drift"])


def drop_last_row(rows: list[list[str]]) -> list[list[str]]:
    return rows[:-1]


def set_cell(column: str, value: str):
    def change(rows: list[list[str]]) -> list[list[str]]:
        header, first, *rest = rows
        first = list(first)
        first[header.index(column)] = value
        return [header, first, *rest]

    return change


@pytest.mark.parametrize(
    "file, damage, check",
    [
        ("brains.csv", drop_last_row, "row counts"),  # an organism without its brain
        ("behaviour.csv", drop_last_row, "row counts"),  # a tick without its behaviour row
        ("brains.csv", set_cell("wh_0_food_ahead", "4.5"), "ranges"),  # beyond +/-4
        ("behaviour.csv", set_cell("toward_food", "1.5"), "ranges"),  # a share above 1
    ],
)
def test_damaged_brain_files_are_refused(runs, tmp_path, file, damage, check):
    damaged = tmp_path / "run"
    shutil.copytree(runs["neural"], damaged)
    with (damaged / file).open(newline="") as f:
        table = list(csv.reader(f))
    with (damaged / file).open("w", newline="") as f:
        csv.writer(f, lineterminator="\n").writerows(damage(table))
    result = ingest_run(damaged, tmp_path / "lake")
    assert not result.ingested
    assert f"[{check}]" in result.reason


def test_brain_rows_in_a_run_without_brains_are_refused(runs, tmp_path):
    """A rule-based run has no brain section, so a brains.csv with rows is a corrupt folder,
    even when every value is a valid weight of an existing organism."""
    damaged = tmp_path / "run"
    shutil.copytree(runs["nearest_food_seeker"], damaged)
    with (damaged / "brains.csv").open("w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(BRAIN_FIELDS)
        writer.writerow([0, *([0.0] * (len(BRAIN_FIELDS) - 1))])
    result = ingest_run(damaged, tmp_path / "lake")
    assert not result.ingested
    assert "[row counts]" in result.reason and "no brains" in result.reason
