"""Capture: predators catching prey (Milestone 6, increment 6.2, D-058).

The rule itself (core/predation.py) on hand-placed positions, then the simulation around it:
energy passed on as specified, caught prey doing nothing more, contested strikes decided by
chance and not by ID, extinction of either species, and reproducible recorded runs.
"""

import math
from pathlib import Path

import numpy as np
import pytest

from genesis.analytics.experiments import apply_changes
from genesis.analytics.runs import execute_run
from genesis.core.config import SimulationConfig, load_config
from genesis.core.organism import DeathCause
from genesis.core.predation import resolve_strikes
from genesis.core.simulation import Simulation

PREDATORS = Path(__file__).parents[2] / "configs" / "predators.yaml"

# Every predator reaches some prey every tick, and every strike lands: captures are certain.
CERTAIN = {"predators.capture_radius": 200.0, "predators.capture_probability": 1.0}


def predator_config(**changes) -> SimulationConfig:
    return apply_changes(load_config(PREDATORS), changes)


def at(*points) -> np.ndarray:
    return np.array(points, dtype=np.float64).reshape(-1, 2)


# --- The rule ------------------------------------------------------------------------------


def test_each_predator_strikes_once_and_each_prey_is_struck_once():
    # Three predators, all within reach of the same two prey: only two strikes can happen.
    rng = np.random.default_rng(0)
    strikes = resolve_strikes(at((0, 0), (1, 0), (2, 0)), at((0.5, 0), (1.5, 0)), 5.0, 1.0, rng)
    assert strikes.attempts == 2
    assert len(set(strikes.predators.tolist())) == 2
    assert len(set(strikes.prey.tolist())) == 2


def test_the_closest_predator_gets_the_prey():
    for seed in range(20):
        strikes = resolve_strikes(
            at((0, 0), (10, 0)),
            at(
                (9, 0),
            ),
            20.0,
            1.0,
            np.random.default_rng(seed),
        )
        assert strikes.predators.tolist() == [1] and strikes.prey.tolist() == [0]


def test_nothing_happens_out_of_reach_or_with_nobody_there():
    rng = np.random.default_rng(0)
    assert resolve_strikes(at((0, 0)), at((5, 0)), 4.9, 1.0, rng).attempts == 0
    assert resolve_strikes(at(), at((5, 0)), 10.0, 1.0, rng).attempts == 0
    assert resolve_strikes(at((0, 0)), at(), 10.0, 1.0, rng).attempts == 0


def test_a_contested_prey_goes_to_either_predator_by_chance_not_by_id():
    # Two predators exactly equidistant from one prey. The winner is a coin flip from the
    # stream: the same on the same seed, and over many seeds each wins about half the time.
    def winner(seed: int) -> int:
        strikes = resolve_strikes(
            at((0, 0), (2, 0)), at((1, 0)), 1.5, 1.0, np.random.default_rng(seed)
        )
        return int(strikes.predators[0])

    assert [winner(s) for s in range(10)] == [winner(s) for s in range(10)]
    wins = sum(winner(s) for s in range(400))
    assert 160 < wins < 240  # predator 1 wins ~200 of 400; ID order would give 0 or 400


def test_strikes_succeed_with_the_configured_probability():
    predators = at(*[(10.0 * k, 0) for k in range(2000)])
    prey = predators + 0.5  # one prey beside each predator, none shared
    strikes = resolve_strikes(predators, prey, 1.0, 0.3, np.random.default_rng(1))
    assert strikes.attempts == 2000
    assert 0.27 < strikes.captures / strikes.attempts < 0.33
    sure = resolve_strikes(predators, prey, 1.0, 1.0, np.random.default_rng(1))
    assert sure.captures == sure.attempts == 2000


# --- In the simulation ---------------------------------------------------------------------


def run_first_tick(**changes):
    sim = Simulation(predator_config(**CERTAIN, **changes))
    start = {o.id: (o.energy, o.energy_spent, o.age) for o in sim.organisms}
    sim.step()
    return sim, start


def test_each_predator_catches_one_prey_and_gains_its_share_of_the_energy():
    sim, _ = run_first_tick()
    cfg = sim.config.predators
    deaths = {e.organism_id: e for e in sim.events_this_tick if e.detail == "predation"}
    meals = [e for e in sim.predator_events_this_tick if e.kind == "meal"]
    assert len(meals) == len(deaths) == cfg.initial_count == sim.predator_summary.captures
    for meal in meals:
        victim = deaths[meal.other_id]
        assert victim.other_id is None  # events.csv only names this run's prey
        assert meal.energy == victim.energy * cfg.capture_efficiency
    # A catch can lift a predator over its reproduction threshold (120 + 0.8 x 50 = 160), so
    # some have a child the same tick: the children have caught nothing.
    for hunter in (o for o in sim.predators if o.parent_id is None):
        assert hunter.prey_eaten == 1
        assert hunter.energy_gained == next(m.energy for m in meals if m.organism_id == hunter.id)
    # What predators didn't get left the system through the ledger's predation flow.
    assert sim.ledger.predation == math.fsum(
        d.energy - d.energy * cfg.capture_efficiency for d in deaths.values()
    )


def test_a_caught_prey_does_nothing_more():
    # Prey start above their reproduction threshold (80), so every prey left alive has a
    # child on tick 0. A caught one must not: nor pay costs, nor age, nor stay in the list.
    sim, start = run_first_tick(**{"organisms.initial_energy": 100.0})
    victims = [o for o in sim.dead if o.death_cause is DeathCause.PREDATION]
    assert victims
    victim_ids = {o.id for o in victims}
    for o in victims:
        energy, spent, age = start[o.id]
        assert o.energy_spent == spent and o.age == age == 0 and o.offspring_count == 0
        assert o.death_tick == 0 and not o.alive
    assert not victim_ids & {o.id for o in sim.organisms}
    assert not victim_ids & {o.parent_id for o in sim.organisms}
    survivors = [o for o in sim.organisms if o.parent_id is None]
    assert survivors and all(o.offspring_count == 1 for o in survivors)


def test_caught_prey_count_as_deaths_of_the_tick():
    sim = Simulation(predator_config(**CERTAIN))
    before = len(sim.organisms)
    summary = sim.step()
    assert summary.deaths >= sim.predator_summary.captures > 0
    assert summary.population == before - summary.deaths + summary.births


def test_predators_can_wipe_out_the_prey_and_then_starve_without_a_crash():
    config = predator_config(**CERTAIN, **{"run.max_ticks": 2000})
    sim = Simulation(config)
    sim.run()
    assert sim.organisms == [] and sim.predators == [] and sim.tick < 2000
    causes = {o.death_cause for o in sim.dead}
    assert DeathCause.PREDATION in causes
    assert all(o.death_cause is DeathCause.STARVATION for o in sim.dead_predators)


def test_capture_worlds_are_deterministic():
    a, b = Simulation(predator_config()), Simulation(predator_config())
    captures = 0
    for _ in range(400):
        a.step()
        b.step()
        captures += a.predator_summary.captures
    assert a.state_digest() == b.state_digest()
    assert captures > 0  # the default settings do produce captures within 400 ticks


@pytest.mark.parametrize("seed", [1, 2])
def test_recorded_predator_runs_replay_byte_for_byte(tmp_path, seed):
    config = apply_changes(predator_config(), {"run.seed": seed, "run.max_ticks": 300})
    first = execute_run(config, tmp_path / "a", run_id="r")
    second = execute_run(config, tmp_path / "b", run_id="r")
    assert first.final_state_digest == second.final_state_digest
    for csv in sorted((tmp_path / "a").glob("*.csv")):
        assert csv.read_bytes() == (tmp_path / "b" / csv.name).read_bytes(), csv.name
