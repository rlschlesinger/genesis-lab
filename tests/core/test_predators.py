"""Predators as a second species (Milestone 6, increment 6.1, D-057).

Predators' bodies, costs, deaths and reproduction, and that worlds without predators are
exactly what they were. Tests that need predators unable to eat set a capture radius no
encounter can reach (``HARMLESS``); capture itself is tested in test_predation.py.
"""

import math
from pathlib import Path

import numpy as np
import pydantic
import pytest

from genesis.analytics.experiments import apply_changes
from genesis.core.config import SimulationConfig, config_hash, load_config
from genesis.core.organism import DeathCause
from genesis.core.simulation import PredatorStreams, RngStreams, Simulation

CONFIGS = Path(__file__).parents[2] / "configs"
PREDATORS = CONFIGS / "predators.yaml"


# A capture radius nothing reaches in practice: predators that never catch anything.
HARMLESS = {"predators.capture_radius": 1e-9}


def predator_config(**changes) -> SimulationConfig:
    """predators.yaml with dotted-path overrides, e.g. predator_config(**{"run.seed": 7})."""
    return apply_changes(load_config(PREDATORS), changes)


def without_predators(config: SimulationConfig) -> SimulationConfig:
    raw = config.model_dump()
    del raw["predators"]
    return SimulationConfig.model_validate(raw)


def flatten(d: dict, prefix: str = "") -> dict:
    out = {}
    for key, value in d.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(flatten(value, f"{name}."))
        else:
            out[name] = value
    return out


# --- Config --------------------------------------------------------------------------------


def test_predator_config_differs_from_neural_only_by_predators():
    # predators.yaml is neural.yaml plus one section, so prey in a predator world are the same
    # prey E007 studied, and E008's no-predator condition is just neural.yaml.
    neural = load_config(CONFIGS / "neural.yaml")
    predators = load_config(PREDATORS)
    assert without_predators(predators) == neural
    neural_flat, predator_flat = flatten(neural.model_dump()), flatten(predators.model_dump())
    differing = {k for k in predator_flat if predator_flat[k] != neural_flat.get(k)}
    assert differing and all(k.startswith("predators.") for k in differing)


@pytest.mark.parametrize("name", ["default.yaml", "evolution.yaml", "neural.yaml"])
def test_configs_without_predators_dump_and_hash_as_before(name):
    # The section is omitted from the dump when absent, so no older config's hash moves.
    config = load_config(CONFIGS / name)
    assert config.predators is None
    assert "predators" not in config.model_dump()
    assert config_hash(config) == config_hash(SimulationConfig.model_validate(config.model_dump()))


def test_predator_reproduction_must_be_affordable():
    raw = load_config(PREDATORS).model_dump()
    raw["predators"]["genome"]["reproduction_threshold"]["min"] = 100.0  # = 80 + 20
    with pytest.raises(pydantic.ValidationError, match="predators: genome.reproduction"):
        SimulationConfig.model_validate(raw)


def test_predators_cannot_use_the_food_seeker():
    raw = load_config(PREDATORS).model_dump()
    raw["predators"]["controller"] = "nearest_food_seeker"
    with pytest.raises(pydantic.ValidationError):
        SimulationConfig.model_validate(raw)


def test_predator_population_must_fit_its_cap():
    raw = load_config(PREDATORS).model_dump()
    raw["predators"]["initial_count"] = raw["predators"]["max_population"] + 1
    with pytest.raises(pydantic.ValidationError, match="exceeds"):
        SimulationConfig.model_validate(raw)


# --- Streams and setup -----------------------------------------------------------------


def test_the_predator_stream_leaves_every_earlier_stream_unchanged():
    # Appending a stream must not move the seven before it (D-012): compare with the streams
    # a seven-way spawn gives.
    streams = RngStreams.from_seed(5)
    old = np.random.SeedSequence(5).spawn(7)
    names = ["setup", "food", "controller", "reproduction", "tiebreak", "mutation", "brain"]
    for name, seed in zip(names, old, strict=True):
        assert getattr(streams, name).random() == np.random.default_rng(seed).random()


def test_predator_sub_streams_are_distinct_and_reproducible():
    a = PredatorStreams.from_generator(RngStreams.from_seed(5).predators)
    b = PredatorStreams.from_generator(RngStreams.from_seed(5).predators)
    draws = [g.random() for g in (a.setup, a.controller, a.reproduction, a.mutation)]
    assert draws == [g.random() for g in (b.setup, b.controller, b.reproduction, b.mutation)]
    assert len(set(draws)) == 4


def test_prey_and_food_start_the_same_with_or_without_predators():
    # E008's matched pairs: on one seed, adding predators changes nothing about the prey or
    # the food the world starts with (predators draw only from their own stream).
    with_p = Simulation(predator_config())
    without = Simulation(without_predators(predator_config()))
    assert np.array_equal(with_p.world.food.positions, without.world.food.positions)
    for a, b in zip(with_p.organisms, without.organisms, strict=True):
        assert (a.id, a.x, a.y, a.heading, a.energy) == (b.id, b.x, b.y, b.heading, b.energy)
        assert np.array_equal(a.brain.to_vector(), b.brain.to_vector())


def test_predator_founders_follow_the_prey_in_id_order():
    config = predator_config()
    sim = Simulation(config)
    n, m = config.organisms.initial_count, config.predators.initial_count
    assert [o.id for o in sim.predators] == list(range(n, n + m))
    assert all(o.energy == config.predators.initial_energy for o in sim.predators)
    assert all(o.traits.speed == config.predators.genome.speed.initial for o in sim.predators)
    assert all(o.brain is None for o in sim.predators)  # brains come with their senses, 6.3


# --- Running ---------------------------------------------------------------------------


def test_predator_worlds_are_deterministic_and_balance_their_energy():
    # The ledger is checked inside every step: a predator cost missing from it would raise.
    a, b = Simulation(predator_config()), Simulation(predator_config())
    for _ in range(300):
        a.step()
        b.step()
    assert a.state_digest() == b.state_digest()
    assert a.ledger.check(a.energy_stock(), a.tick) is None


def test_predators_never_eat_food_and_starve_on_schedule():
    # Unable to catch prey, a predator's energy only goes down; each pays at least its
    # metabolism every tick, so all must have starved by initial_energy / metabolic_rate.
    config = predator_config(**{"run.max_ticks": 1000}, **HARMLESS)
    sim = Simulation(config)
    limit = math.ceil(
        config.predators.initial_energy / config.predators.genome.metabolic_rate.initial
    )
    previous = {o.id: o.energy for o in sim.predators}
    while sim.predators and sim.tick <= limit:
        sim.step()
        for o in sim.predators:
            assert o.energy < previous[o.id] and o.food_eaten == 0 and o.prey_eaten == 0
            previous[o.id] = o.energy
    assert sim.predators == []
    assert len(sim.dead_predators) == config.predators.initial_count
    assert all(o.death_cause is DeathCause.STARVATION for o in sim.dead_predators)
    assert sim.predator_summary.population == 0 and math.isnan(sim.predator_summary.mean_energy)


def test_prey_records_never_include_predators():
    sim = Simulation(predator_config(**HARMLESS))
    predator_ids = {o.id for o in sim.predators}
    for _ in range(200):
        summary = sim.step()
        assert summary.population == len(sim.organisms)
        assert not predator_ids & {o.id for o in [*sim.organisms, *sim.dead]}
        assert not predator_ids & {e.organism_id for e in sim.events_this_tick}


def test_predators_reproduce_by_their_own_rules():
    # Founders start above their threshold and have no cap pressure: every one has a child on
    # tick 0, paid for by its own offspring_energy and overhead, in the ledger.
    config = predator_config(**{"predators.initial_energy": 200.0, "predators.max_population": 100})
    sim = Simulation(config)
    founders = list(sim.predators)
    sim.step()
    cfg = config.predators
    children = [o for o in sim.predators if o.parent_id is not None]
    assert len(children) == len(founders) == sim.predator_summary.births
    assert all(o.energy == cfg.offspring_energy and o.generation == 1 for o in children)
    assert all(o.offspring_count == 1 for o in founders)
    ids = [o.id for o in sim.predators]
    assert ids == sorted(ids) and min(o.id for o in children) > max(o.id for o in sim.organisms)


def test_predator_cap_limits_births():
    config = predator_config(**{"predators.initial_energy": 200.0, "predators.max_population": 13})
    sim = Simulation(config)
    sim.step()
    assert len(sim.predators) == 13


def test_a_world_runs_on_after_the_prey_die_out_and_stops_when_everyone_has():
    # No food: the prey starve first (50 EU), the predators later (120 EU). The run must not
    # stop when the prey are gone, and must stop once the predators are gone too.
    config = predator_config(
        **{"food.initial_count": 0, "food.regrowth_per_tick": 0.0, "run.max_ticks": 5000}
    )
    sim = Simulation(config)
    while sim.organisms:
        sim.step()
    assert sim.predators and not sim.finished
    sim.run()
    assert not sim.organisms and not sim.predators and sim.tick < 5000


def test_a_prey_world_runs_on_after_the_predators_die_out():
    sim = Simulation(predator_config(**{"run.max_ticks": 800}, **HARMLESS))
    sim.run()
    assert sim.predators == [] and sim.organisms and sim.tick == 800


def test_predators_that_catch_nothing_leave_the_prey_history_untouched():
    # Predators that never reach a prey can't affect it, and they draw only from their own
    # streams, so the prey's whole history is the predator-free world's, tick for tick (only
    # later IDs shift, since predator founders take IDs after the prey founders). Once they
    # catch prey this stops holding: that is the point of predators.
    with_p = Simulation(predator_config(**HARMLESS))
    without = Simulation(without_predators(predator_config()))
    for _ in range(300):
        assert with_p.step() == without.step()
