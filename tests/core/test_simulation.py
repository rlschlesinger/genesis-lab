"""Tests for the simulation loop: setup, determinism, stream independence, deaths, stopping."""

import math
from collections import Counter
from pathlib import Path

import numpy as np
import pytest
import yaml

from genesis.core.config import SimulationConfig
from genesis.core.energy import EnergyLedgerError
from genesis.core.organism import DeathCause
from genesis.core.simulation import RngStreams, Simulation

DEFAULT_CONFIG = Path(__file__).parents[2] / "configs" / "default.yaml"


def make_config(**changes) -> SimulationConfig:
    """Default config with dotted-path overrides, e.g. make_config(**{"run.seed": 7})."""
    raw = yaml.safe_load(DEFAULT_CONFIG.read_text())
    for path, value in changes.items():
        *parents, leaf = path.split(".")
        section = raw
        for key in parents:
            section = section[key]
        section[leaf] = value
    return SimulationConfig.model_validate(raw)


# Food that never appears: organisms can only starve. Used to test deaths and stopping.
NO_FOOD = {"food.initial_count": 0, "food.regrowth_per_tick": 0.0}


# --- Setup --------------------------------------------------------------------------------


def test_founders_match_config():
    config = make_config()
    sim = Simulation(config)
    assert len(sim.organisms) == config.organisms.initial_count
    assert [o.id for o in sim.organisms] == list(range(config.organisms.initial_count))
    assert all(o.generation == 0 and o.parent_id is None for o in sim.organisms)
    assert all(o.energy == config.organisms.initial_energy for o in sim.organisms)
    positions = np.array([[o.x, o.y] for o in sim.organisms])
    assert sim.world.contains(positions).all()


# --- Determinism --------------------------------------------------------------------------


def test_same_seed_gives_identical_state_every_tick():
    a, b = Simulation(make_config()), Simulation(make_config())
    for _ in range(200):
        assert a.step() == b.step()
        assert a.state_digest() == b.state_digest()


def test_different_seeds_diverge():
    a = Simulation(make_config(**{"run.seed": 1}))
    b = Simulation(make_config(**{"run.seed": 2}))
    assert a.state_digest() != b.state_digest()


def test_digest_detects_a_tiny_change():
    a, b = Simulation(make_config()), Simulation(make_config())
    b.organisms[0].energy += 1e-12
    assert a.state_digest() != b.state_digest()


def test_rng_streams_are_independent():
    # Drawing heavily from one stream must not change what another stream produces next.
    quiet, busy = RngStreams.from_seed(42), RngStreams.from_seed(42)
    busy.controller.normal(size=10_000)
    np.testing.assert_array_equal(quiet.food.uniform(size=5), busy.food.uniform(size=5))


def test_rng_streams_differ_from_each_other():
    streams = RngStreams.from_seed(42)
    assert streams.food.uniform() != streams.controller.uniform()


def test_controller_choice_does_not_change_the_starting_world():
    # Paired-seed comparisons rely on this: both controllers start from an identical world.
    walk = Simulation(make_config(**{"organisms.controller": "random_walk"}))
    seek = Simulation(make_config(**{"organisms.controller": "nearest_food_seeker"}))
    assert walk.state_digest() == seek.state_digest()


# --- Ticking ------------------------------------------------------------------------------


def test_step_advances_clock_and_ages_survivors():
    sim = Simulation(make_config())
    summary = sim.step()
    assert summary.tick == 0
    assert sim.tick == 1
    assert all(o.age == 1 for o in sim.organisms)


def test_energy_costs_are_charged_each_tick():
    config = make_config()
    sim = Simulation(config)
    sim.step()
    t, cfg = config.organisms.traits, config.organisms
    max_cost = t.metabolic_rate + cfg.move_cost_per_distance * t.speed
    for org in sim.organisms:
        # Spent at least metabolism, at most metabolism + a full-speed move (less at walls).
        assert t.metabolic_rate - 1e-12 <= org.energy_spent <= max_cost + 1e-12


def test_no_food_means_everyone_starves():
    sim = Simulation(make_config(**NO_FOOD))
    sim.run()
    assert not sim.organisms
    assert len(sim.dead) == sim.config.organisms.initial_count
    assert all(o.death_cause is DeathCause.STARVATION for o in sim.dead)


def test_deaths_are_counted_and_recorded():
    sim = Simulation(make_config(**NO_FOOD))
    summaries = sim.run()
    # Two independent records of the same events must agree, tick by tick: the per-tick
    # summaries, and the death_tick stamped on each dead organism.
    from_organisms = Counter(d.death_tick for d in sim.dead)
    from_summaries = {s.tick: s.deaths for s in summaries if s.deaths}
    assert from_summaries == dict(from_organisms)
    assert sum(from_summaries.values()) == sim.config.organisms.initial_count


def test_dead_are_never_processed_again():
    # Organism.spend raises on a dead organism, so finishing without error proves the loop
    # never touched the dead after they died.
    sim = Simulation(make_config(**NO_FOOD, **{"run.stop_on_extinction": False}))
    sim.run()
    assert sim.tick == sim.config.run.max_ticks


def test_old_age_kills_at_max_age():
    sim = Simulation(make_config(**{"organisms.max_age": 10}))
    summaries = sim.run()
    assert all(o.death_cause is DeathCause.OLD_AGE and o.death_tick == 10 for o in sim.dead)
    assert summaries[10].deaths == sim.config.organisms.initial_count


# --- Stopping -----------------------------------------------------------------------------


def test_run_stops_at_max_ticks():
    sim = Simulation(make_config(**{"run.max_ticks": 25}))
    assert len(sim.run()) == 25
    assert sim.finished


def test_run_stops_early_on_extinction():
    sim = Simulation(make_config(**NO_FOOD))
    summaries = sim.run()
    assert len(summaries) < sim.config.run.max_ticks
    assert summaries[-1].population == 0


def test_mean_energy_is_nan_for_empty_population():
    sim = Simulation(make_config(**NO_FOOD))
    assert math.isnan(sim.run()[-1].mean_energy)


@pytest.mark.parametrize("controller", ["random_walk", "nearest_food_seeker"])
def test_both_controllers_run(controller):
    sim = Simulation(make_config(**{"organisms.controller": controller, "run.max_ticks": 50}))
    assert len(sim.run()) == 50


# --- Eating and the energy ledger ---------------------------------------------------------


def test_ledger_balances_every_tick_with_eating():
    # step() checks the ledger itself and raises on a mismatch; 1000 ticks of the default
    # world (eating, starving, regrowth at the cap) completing is the test.
    sim = Simulation(make_config(**{"run.max_ticks": 1000}))
    summaries = sim.run()
    assert sum(s.food_eaten for s in summaries) > 0
    assert sim.ledger.expected_stock == pytest.approx(sim.energy_stock())


def test_ledger_detects_energy_created_by_a_bug():
    sim = Simulation(make_config())
    sim.step()
    sim.organisms[0].energy += 5.0  # simulate a bug: energy from nowhere
    with pytest.raises(EnergyLedgerError, match="tick 1"):
        sim.step()


def test_organism_on_top_of_food_eats_it():
    sim = Simulation(make_config(**{"food.regrowth_per_tick": 0.0}))
    org = sim.organisms[0]
    org.x, org.y = (float(v) for v in sim.world.food.positions[0])
    org.heading = 0.0
    food_before = sim.world.food.count
    summary = sim.step()
    assert org.food_eaten == 1
    assert summary.food_eaten >= 1
    assert sim.world.food.count == food_before - summary.food_eaten


def test_food_eaten_summaries_match_organism_records():
    sim = Simulation(make_config(**{"run.max_ticks": 500}))
    summaries = sim.run()
    per_organism = sum(o.food_eaten for o in [*sim.organisms, *sim.dead])
    assert sum(s.food_eaten for s in summaries) == per_organism


def test_energy_left_at_old_age_death_is_recorded_as_lost():
    sim = Simulation(make_config(**{"organisms.max_age": 10}))
    sim.run()
    assert sim.ledger.lost_at_death == pytest.approx(sum(o.energy for o in sim.dead))
    assert sim.ledger.lost_at_death > 0


def test_determinism_holds_with_eating():
    a, b = Simulation(make_config()), Simulation(make_config())
    for _ in range(300):
        a.step()
        b.step()
    assert a.state_digest() == b.state_digest()
