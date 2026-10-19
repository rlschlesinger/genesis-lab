"""Neural organisms in the full simulation: deterministic, energy-conserving, extinction-safe,
and not leaking into rule-based runs."""

from dataclasses import replace
from pathlib import Path

import numpy as np

from genesis.core.config import SimulationConfig, load_config
from genesis.core.geometry import wrap_angle
from genesis.core.simulation import Simulation
from genesis.intelligence.brain_inputs import wall_distance_ahead
from genesis.intelligence.controllers import NeuralController
from genesis.intelligence.neural import BrainStack
from genesis.intelligence.sensors import BodySenses, sense_food

NEURAL = Path(__file__).parents[2] / "configs" / "neural.yaml"


def neural_config(**sections) -> SimulationConfig:
    raw = load_config(NEURAL).model_dump()
    for section, changes in sections.items():
        raw[section] = {**raw[section], **changes}
    return SimulationConfig.model_validate(raw)


def test_neural_runs_are_deterministic():
    a, b = Simulation(neural_config()), Simulation(neural_config())
    sa = [a.step() for _ in range(300)]
    sb = [b.step() for _ in range(300)]
    assert sa == sb
    assert a.state_digest() == b.state_digest()


def test_different_seeds_give_different_brains_and_histories():
    a = Simulation(neural_config(run={"seed": 1}))
    b = Simulation(neural_config(run={"seed": 2}))
    assert a.organisms[0].brain.to_vector().tobytes() != b.organisms[0].brain.to_vector().tobytes()
    assert [a.step() for _ in range(100)] != [b.step() for _ in range(100)]


def test_neural_organisms_move_eat_reproduce_and_the_ledger_balances():
    # step() checks the energy ledger every tick and raises if it doesn't balance.
    sim = Simulation(neural_config())
    summaries = [sim.step() for _ in range(1000)]
    assert sum(s.food_eaten for s in summaries) > 0
    assert sum(s.births for s in summaries) > 0
    assert any(o.x != 0 for o in sim.organisms)


def test_actions_in_the_simulation_are_what_the_controller_computes():
    """Recompute tick 0's decision outside the simulation, from the same state and the same
    random state: the simulation's new headings must match it bit for bit. This is what the
    inspector (4.6) relies on."""
    sim = Simulation(neural_config())
    replay = Simulation(neural_config())  # an identical twin, used only to read state
    replay.world.food.regrow(replay.rng.food)  # tick 0's step 1: food regrows before sensing
    living = replay.organisms
    positions = np.array([[o.x, o.y] for o in living])
    headings = np.array([o.heading for o in living])
    traits = [o.traits for o in living]
    sense_ranges = np.array([t.sense_range for t in traits])
    obs = sense_food(
        positions,
        headings,
        sense_ranges,
        np.array([o.energy for o in living]),
        replay.world.food.positions,
    )
    body = BodySenses(
        wall_distance=wall_distance_ahead(positions, headings, 200.0, 200.0),
        sense_range=sense_ranges,
        max_turn=np.array([t.max_turn for t in traits]),
        reproduction_threshold=np.array([t.reproduction_threshold for t in traits]),
    )
    thought = NeuralController().think(
        replace(obs, body=body), replay.rng.controller, BrainStack.of([o.brain for o in living])
    )
    expected = wrap_angle(headings + thought.actions.turn)

    sim.step()
    got = np.array([o.heading for o in sim.organisms[: len(living)]])
    assert got.tobytes() == expected.tobytes()


def test_extinct_neural_population_keeps_ticking_without_errors():
    sim = Simulation(
        neural_config(
            food={"initial_count": 0, "regrowth_per_tick": 0.0},
            organisms={"initial_energy": 0.5},
            run={"stop_on_extinction": False, "max_ticks": 20},
        )
    )
    summaries = sim.run()
    assert summaries[-1].population == 0
    assert len(summaries) == 20


def test_brains_without_a_neural_controller_are_carried_but_never_used():
    """The no-selection control: a rule-based run that carries brains behaves exactly like one
    that doesn't (D-042)."""
    raw = load_config(NEURAL).model_dump()
    raw["organisms"]["controller"] = "nearest_food_seeker"
    raw["run"]["max_ticks"] = 300
    carried = SimulationConfig.model_validate(raw)
    del raw["brain"]
    plain = SimulationConfig.model_validate(raw)
    assert Simulation(carried).run() == Simulation(plain).run()
