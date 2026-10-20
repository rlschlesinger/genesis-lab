"""Senses for predators and prey (Milestone 6, increment 6.3, D-059).

Predators sense the nearest prey as prey sense food; prey with brains get three inputs about
the nearest predator. Checked on hand-worked cases, then in the simulation: brain sizes,
chasing, neural predators, and the places that name a brain's inputs.
"""

import math
from pathlib import Path

import numpy as np
import pydantic
import pytest

from genesis.analytics.experiments import apply_changes
from genesis.api.details import organism_detail
from genesis.api.runs import LiveRun
from genesis.core.config import SimulationConfig, load_config
from genesis.core.simulation import Simulation
from genesis.intelligence.brain_inputs import (
    INPUT_NAMES,
    PREY_INPUT_NAMES,
    brain_inputs,
    input_names,
    parameter_names,
)
from genesis.intelligence.sensors import Observations, ThreatSenses, sense_threats
from genesis.lake.ingest import ingest_run

PREDATORS = Path(__file__).parents[2] / "configs" / "predators.yaml"


def predator_config(**changes) -> SimulationConfig:
    return apply_changes(load_config(PREDATORS), changes)


def neural_predators(**changes) -> SimulationConfig:
    """predators.yaml with neural predators (a section can't be added by a dotted path)."""
    raw = predator_config(**changes).model_dump()
    raw["predators"]["controller"] = "neural"
    raw["predators"]["brain"] = {}
    return SimulationConfig.model_validate(raw)


# --- The three predator inputs, by hand ----------------------------------------------------


def test_a_predator_to_the_left_at_half_range():
    # A prey at the origin facing +x (heading 0), sense range 20; a predator at (0, 10): 10
    # units away, a quarter turn to the left.
    threat = sense_threats(np.array([[0.0, 0.0]]), np.zeros(1), np.full(1, 20.0),
                           np.array([[0.0, 10.0]]))  # fmt: skip
    assert threat.found.tolist() == [True]
    assert threat.distance[0] == 10.0 and threat.bearing[0] == pytest.approx(math.pi / 2)
    obs = Observations(
        food_found=np.zeros(1, bool), food_distance=np.full(1, np.inf),
        food_bearing=np.zeros(1), energy=np.full(1, 40.0), threat=threat,
    )  # fmt: skip
    row = brain_inputs(obs, np.full(1, 20.0), np.full(1, 80.0), np.full(1, 5.0), np.zeros(1))[0]
    assert len(row) == 10
    assert row[7] == 1.0 and row[8] == pytest.approx(1.0) and row[9] == 0.5


def test_ahead_and_behind_look_alike_by_design():
    # No predator_ahead input (D-059): straight ahead and straight behind both give sin = 0.
    ahead = sense_threats(np.zeros((1, 2)), np.zeros(1), np.full(1, 20.0), np.array([[5.0, 0]]))
    behind = sense_threats(np.zeros((1, 2)), np.zeros(1), np.full(1, 20.0), np.array([[-5.0, 0]]))
    assert np.sin(ahead.bearing[0]) == pytest.approx(0.0, abs=1e-12)
    assert np.sin(behind.bearing[0]) == pytest.approx(0.0, abs=1e-12)


def test_no_predator_in_sight_gives_zeros_and_leaves_the_first_seven_alone():
    rng = np.random.default_rng(3)
    n = 50
    base = Observations(
        food_found=rng.random(n) < 0.5, food_distance=rng.uniform(0, 20, n),
        food_bearing=rng.uniform(-3, 3, n), energy=rng.uniform(0, 100, n),
    )  # fmt: skip
    nothing = ThreatSenses(np.zeros(n, bool), np.full(n, np.inf), np.zeros(n))
    args = (np.full(n, 20.0), np.full(n, 80.0), rng.uniform(0, 30, n), rng.uniform(-1, 1, n))
    seven = brain_inputs(base, *args)
    ten = brain_inputs(Observations(**{**_fields(base), "threat": nothing}), *args)
    assert seven.shape == (n, 7) and ten.shape == (n, 10)
    assert np.array_equal(ten[:, :7], seven)
    assert not ten[:, 7:].any()


def _fields(obs: Observations) -> dict:
    return {f: getattr(obs, f) for f in ("food_found", "food_distance", "food_bearing", "energy")}


def test_names_for_both_brain_sizes():
    assert input_names(7) == INPUT_NAMES and input_names(10) == PREY_INPUT_NAMES
    names = parameter_names(PREY_INPUT_NAMES)
    assert len(names) == 80 == len(set(names))
    assert "wh_0_predator_seen" in names and parameter_names()[:7] == names[:7]
    with pytest.raises(ValueError):
        input_names(8)


# --- Config --------------------------------------------------------------------------------


def test_prey_brains_must_fit_the_world():
    raw = predator_config().model_dump()
    raw["brain"]["founder_weights"] = [[0.0] * 62] * raw["organisms"]["initial_count"]
    with pytest.raises(pydantic.ValidationError, match="a brain here has 80"):
        SimulationConfig.model_validate(raw)
    raw["brain"]["founder_weights"] = [[0.0] * 80] * raw["organisms"]["initial_count"]
    sim = Simulation(SimulationConfig.model_validate(raw))
    assert all(o.brain.shape == (10, 6, 2) for o in sim.organisms)


def test_neural_predators_need_a_brain_and_the_right_number_of_founder_brains():
    raw = predator_config().model_dump()
    raw["predators"]["controller"] = "neural"
    with pytest.raises(pydantic.ValidationError, match="needs a predators.brain"):
        SimulationConfig.model_validate(raw)
    raw["predators"]["brain"] = {"founder_weights": [[0.0] * 62] * 3}
    with pytest.raises(pydantic.ValidationError, match="3 brains for 10 predator founders"):
        SimulationConfig.model_validate(raw)


def test_a_world_ready_for_predators_can_have_none():
    sim = Simulation(predator_config(**{"predators.initial_count": 0}))
    assert sim.predators == []
    sim.step()
    assert sim.last_decision.thought.inputs.shape == (30, 10)
    assert not sim.last_decision.thought.inputs[:, 7:].any()  # never a predator to see


# --- In the simulation ---------------------------------------------------------------------


def test_prey_brains_are_told_about_the_predators_they_can_see():
    sim = Simulation(predator_config())
    for _ in range(60):
        prey = [(o.x, o.y, o.heading, o.traits.sense_range) for o in sim.organisms]
        hunters = np.array([[o.x, o.y] for o in sim.predators]).reshape(-1, 2)
        sim.step()
        arr = np.array(prey)
        expected = sense_threats(arr[:, :2], arr[:, 2], arr[:, 3], hunters).found
        assert np.array_equal(sim.last_decision.thought.inputs[:, 7], expected)
    assert sim.last_decision.thought.inputs.shape[1] == 10


def test_predators_see_the_nearest_prey_where_it_was_at_the_start_of_the_tick():
    sim = Simulation(predator_config())
    for _ in range(30):
        prey = np.array([[o.x, o.y] for o in sim.organisms])
        hunters = [(o.x, o.y, o.traits.sense_range) for o in sim.predators]
        sim.step()
        seen = sim.last_predator_decision.observations
        for k, (x, y, reach) in enumerate(hunters):
            nearest = np.hypot(prey[:, 0] - x, prey[:, 1] - y).min()
            assert seen.food_found[k] == (nearest <= reach)
            if seen.food_found[k]:
                assert seen.food_distance[k] == pytest.approx(nearest)


def test_chasing_predators_catch_more_than_wandering_ones():
    # Same worlds, same settings, only the predators' controller differs.
    def captures(controller: str) -> int:
        total = 0
        for seed in (1, 2, 3):
            sim = Simulation(
                predator_config(**{"run.seed": seed, "predators.controller": controller})
            )
            for _ in range(300):
                sim.step()
                total += sim.predator_summary.captures if sim.predator_summary else 0
        return total

    assert captures("nearest_prey_seeker") > 2 * captures("random_walk")


def test_neural_predators_think_inherit_and_replay():
    config = neural_predators(**{"predators.initial_energy": 200.0})
    a, b = Simulation(config), Simulation(config)
    assert all(o.brain.shape == (7, 6, 2) for o in a.predators)
    founders = {o.id: o.brain.to_vector() for o in a.predators}
    for _ in range(200):
        a.step()
        b.step()
    assert a.state_digest() == b.state_digest()
    thought = a.last_predator_decision.thought
    assert thought is not None and thought.inputs.shape == (len(a.predators), 7)
    children = [o for o in [*a.predators, *a.dead_predators] if o.parent_id is not None]
    assert children  # 200 EU is above their threshold: every founder had a child on tick 0
    assert all(o.brain.shape == (7, 6, 2) for o in children)
    changed = [o for o in children if o.parent_id in founders
               and not np.array_equal(o.brain.to_vector(), founders[o.parent_id])]  # fmt: skip
    assert changed  # brains mutate at birth, from the predators' own stream


def test_predator_brains_differ_from_the_prey_brains_stream():
    # Predators draw their brains from their own stream: prey brains are the same whether the
    # predators are neural or not.
    plain, neural = Simulation(predator_config()), Simulation(neural_predators())
    for a, b in zip(plain.organisms, neural.organisms, strict=True):
        assert np.array_equal(a.brain.to_vector(), b.brain.to_vector())


# --- Places that name a brain's inputs -----------------------------------------------------


def test_organism_details_name_all_ten_inputs_and_eighty_weights():
    sim = Simulation(predator_config())
    sim.step()
    run = LiveRun("r", "predators", sim.config, sim)
    detail = organism_detail(run, sim.organisms[0].id)
    assert len(detail.brain_weights) == 80
    assert detail.thought.input_names == list(PREY_INPUT_NAMES)
    assert len(detail.thought.inputs) == 10


def test_brains_csv_has_eighty_columns_and_the_lake_takes_them(tmp_path):
    from genesis.analytics.runs import execute_run

    config = predator_config(**{"run.max_ticks": 20})
    execute_run(config, tmp_path / "run", run_id="p")
    header = (tmp_path / "run" / "brains.csv").read_text().splitlines()[0].split(",")
    assert header == ["id", *parameter_names(PREY_INPUT_NAMES)]
    result = ingest_run(tmp_path / "run", tmp_path / "lake")
    assert result.ingested, result.reason  # from 6.4 (D-060)
