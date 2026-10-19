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
from genesis.evolution.genome import Genome, express

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
    t, cfg = express(Genome.from_config(config.genome)), config.organisms
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


def first_active_tick(org) -> int:
    # Founders act from tick 0. Newborns are created during tick birth_tick, after the
    # acting steps, so their first active tick is the next one.
    return 0 if org.parent_id is None else org.birth_tick + 1


def test_old_age_kills_after_exactly_max_age_active_ticks():
    max_age = 10
    sim = Simulation(make_config(**{"organisms.max_age": max_age, "run.max_ticks": 300}))
    sim.run()
    old = [o for o in sim.dead if o.death_cause is DeathCause.OLD_AGE]
    assert any(o.parent_id is not None for o in old)  # covers newborns, not only founders
    for org in old:
        assert org.age == max_age
        assert org.death_tick == first_active_tick(org) + max_age


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


# --- Reproduction -------------------------------------------------------------------------


def sim_with_one_rich_organism(energy=200.0, **changes):
    """A simulation where organism 0 can afford to reproduce on tick 0 and nobody else can."""
    sim = Simulation(make_config(**NO_FOOD, **changes))
    for org in sim.organisms:
        org.energy = 10.0
    sim.organisms[0].energy = energy
    sim.ledger.initial_stock = sim.energy_stock()  # we edited the state, so restate the books
    return sim


def test_eligible_organism_produces_an_exact_copy():
    sim = sim_with_one_rich_organism()
    cfg = sim.config.organisms
    parent = sim.organisms[0]
    summary = sim.step()
    assert summary.births == 1
    child = sim.organisms[-1]
    assert child.parent_id == parent.id
    assert child.generation == parent.generation + 1
    assert child.birth_tick == 0
    assert child.traits == parent.traits
    assert child.energy == cfg.offspring_energy
    assert parent.offspring_count == 1
    assert parent.energy_invested == cfg.offspring_energy + cfg.reproduction_overhead


def test_parent_pays_transfer_plus_overhead():
    sim = sim_with_one_rich_organism(energy=200.0)
    cfg = sim.config.organisms
    parent = sim.organisms[0]
    sim.step()
    # 200 - this tick's living costs - (offspring_energy + overhead)
    expected = 200.0 - parent.energy_spent - cfg.offspring_energy - cfg.reproduction_overhead
    assert parent.energy == pytest.approx(expected)


def test_below_threshold_no_reproduction():
    sim = sim_with_one_rich_organism(energy=60.0)  # threshold is 80
    assert sim.step().births == 0


def test_at_most_one_child_per_parent_per_tick():
    sim = sim_with_one_rich_organism(energy=10_000.0)
    assert sim.step().births == 1


def test_newborn_does_not_act_on_its_birth_tick():
    sim = sim_with_one_rich_organism()
    sim.step()
    child = sim.organisms[-1]
    born_at = (child.x, child.y, child.heading)
    assert child.age == 0
    assert child.energy_spent == 0.0  # paid no costs: it didn't live through tick 0
    sim.step()
    assert (child.x, child.y, child.heading) != born_at  # acts from the next tick
    assert child.age == 1


def test_newborns_keep_population_in_id_order():
    sim = Simulation(make_config(**{"run.max_ticks": 400}))
    sim.run()
    ids = [o.id for o in sim.organisms]
    assert ids == sorted(ids)


def test_population_never_exceeds_cap():
    # Food-rich world with a small cap, so the cap is actually reached.
    sim = Simulation(
        make_config(**{"organisms.max_population": 40, "food.regrowth_per_tick": 20.0,
                       "run.max_ticks": 600})
    )  # fmt: skip
    summaries = sim.run()
    assert max(s.population for s in summaries) == 40
    assert all(s.population <= 40 for s in summaries)


def test_births_are_counted_and_generations_accumulate():
    sim = Simulation(make_config(**{"run.max_ticks": 1500}))
    summaries = sim.run()
    everyone = [*sim.organisms, *sim.dead]
    born = [o for o in everyone if o.parent_id is not None]
    assert sum(s.births for s in summaries) == len(born) > 0
    assert max(o.generation for o in everyone) >= 2  # grandchildren exist


def test_reproduction_overhead_is_recorded_in_the_ledger():
    sim = Simulation(make_config(**{"run.max_ticks": 1000}))
    summaries = sim.run()
    births = sum(s.births for s in summaries)
    overhead = sim.config.organisms.reproduction_overhead
    assert sim.ledger.reproduction_overhead == pytest.approx(births * overhead)


def test_ledger_and_determinism_hold_with_reproduction():
    a = Simulation(make_config(**{"run.max_ticks": 1500}))
    b = Simulation(make_config(**{"run.max_ticks": 1500}))
    a.run()  # step() checks the ledger every tick
    b.run()
    assert a.state_digest() == b.state_digest()


# --- Lineages -----------------------------------------------------------------------------


def test_founder_lineage_is_inherited():
    sim = Simulation(make_config(**{"run.max_ticks": 800}))
    sim.run()
    everyone = {o.id: o for o in [*sim.organisms, *sim.dead]}
    founder_ids = {o.id for o in everyone.values() if o.parent_id is None}
    for org in everyone.values():
        if org.parent_id is None:
            assert org.founder_id == org.id
        else:
            assert org.founder_id == everyone[org.parent_id].founder_id
        assert org.founder_id in founder_ids


def test_lineages_can_only_disappear_never_appear():
    # No mutation and no immigration: a lineage that dies out can never come back.
    summaries = Simulation(make_config(**{"run.max_ticks": 2000})).run()
    counts = [s.lineages for s in summaries]
    assert counts[0] <= 30
    assert all(later <= earlier for earlier, later in zip(counts, counts[1:], strict=False))


# --- Genome -------------------------------------------------------------------------------


def test_every_organism_carries_a_genome_whose_expression_is_its_traits():
    sim = Simulation(make_config(**{"run.max_ticks": 500}))
    sim.run()
    for org in [*sim.organisms, *sim.dead]:
        assert org.traits == express(org.genome)


def test_without_mutation_every_genome_equals_the_founders():
    sim = Simulation(make_config(**{"run.max_ticks": 500}))
    founder_genome = sim.organisms[0].genome
    sim.run()
    assert all(o.genome == founder_genome for o in [*sim.organisms, *sim.dead])


def test_adding_the_mutation_stream_left_earlier_streams_unchanged():
    # SeedSequence.spawn hands out children by position, so appending a stream must not
    # change any existing one (D-012). Compare against streams spawned the old way (5 children).
    new = RngStreams.from_seed(42)
    old_children = np.random.SeedSequence(42).spawn(5)
    for name, child in zip(["setup", "food", "controller", "reproduction", "tiebreak"],
                           old_children, strict=True):  # fmt: skip
        expected = np.random.default_rng(child).uniform(size=3)
        np.testing.assert_array_equal(getattr(new, name).uniform(size=3), expected)


# --- Inheritance with mutation ------------------------------------------------------------

MUTATING = {"mutation.enabled": True, "mutation.rate": 0.3, "mutation.size": 0.1}


@pytest.fixture(scope="module")
def mutated_run():
    """One 1500-tick run with frequent mutation, shared by the lineage tests (it's slow-ish)."""
    sim = Simulation(make_config(**MUTATING, **{"run.max_ticks": 1500}))
    summaries = sim.run()
    return sim, summaries


def test_lineage_integrity_every_genome_is_parent_plus_recorded_changes(mutated_run):
    # The core inheritance guarantee: for EVERY organism that ever lived, its genome equals its
    # parent's genome with exactly the logged changes applied, and nothing else.
    sim, _ = mutated_run
    everyone = {o.id: o for o in [*sim.organisms, *sim.dead]}
    changes_by_child: dict[int, list] = {}
    for event in sim.mutation_log:
        changes_by_child.setdefault(event.child_id, []).append(event)

    initial = Genome.from_config(sim.config.genome)
    for org in everyone.values():
        if org.parent_id is None:
            assert org.genome == initial
            assert org.id not in changes_by_child
            continue
        parent = everyone[org.parent_id]
        events = changes_by_child.get(org.id, [])
        for e in events:
            assert e.parent_id == parent.id and e.tick == org.birth_tick
            assert e.before == getattr(parent.genome, e.gene)
        expected = parent.genome.as_dict() | {e.gene: e.after for e in events}
        assert org.genome.as_dict() == expected
        assert org.traits == express(org.genome)


def test_mutation_creates_variation_within_bounds(mutated_run):
    sim, _ = mutated_run
    genomes = {o.genome for o in [*sim.organisms, *sim.dead]}
    assert len(genomes) > 100  # many distinct genomes, not just the founders'
    for org in [*sim.organisms, *sim.dead]:
        for name, value in org.genome.as_dict().items():
            bounds = getattr(sim.config.genome, name)
            assert bounds.min <= value <= bounds.max


def test_mutation_counts_in_summaries_match_the_log(mutated_run):
    sim, summaries = mutated_run
    assert sum(s.mutations for s in summaries) == len(sim.mutation_log) > 0


def test_ledger_and_determinism_hold_with_mutation():
    a = Simulation(make_config(**MUTATING, **{"run.max_ticks": 800}))
    b = Simulation(make_config(**MUTATING, **{"run.max_ticks": 800}))
    a.run()  # step() checks the energy ledger every tick
    b.run()
    assert a.state_digest() == b.state_digest()
    assert a.mutation_log == b.mutation_log


def test_digest_sees_a_difference_in_an_unexpressed_gene():
    a, b = Simulation(make_config()), Simulation(make_config())
    org = b.organisms[0]
    org.genome = Genome(**(org.genome.as_dict() | {"neutral_marker": 0.51}))
    assert a.state_digest() != b.state_digest()


def test_frozen_genes_stay_fixed_in_a_full_run():
    changes = {"genome.speed.mutable": False, "genome.sense_range.mutable": False}
    sim = Simulation(make_config(**MUTATING, **changes, **{"run.max_ticks": 800}))
    sim.run()
    assert {o.genome.speed for o in [*sim.organisms, *sim.dead]} == {1.5}
    assert {o.genome.sense_range for o in [*sim.organisms, *sim.dead]} == {20.0}
    assert not any(e.gene in ("speed", "sense_range") for e in sim.mutation_log)


# --- Trade-off costs ----------------------------------------------------------------------


def test_sensing_cost_is_charged_and_recorded():
    sim = Simulation(make_config(**NO_FOOD, **{"organisms.sense_cost_per_unit": 0.004}))
    sim.step()
    # 30 founders, sense range 20, 0.004 EU per unit per tick: 30 x 0.08 = 2.4 EU.
    assert sim.ledger.sensing == pytest.approx(30 * 20.0 * 0.004)


def test_ledger_balances_with_all_trade_offs_and_mutation():
    evolution = DEFAULT_CONFIG.with_name("evolution.yaml")
    raw = yaml.safe_load(evolution.read_text())
    raw["run"]["max_ticks"] = 1500
    sim = Simulation(SimulationConfig.model_validate(raw))
    sim.run()  # step() checks the ledger every tick
    assert sim.ledger.sensing > 0
    assert len(sim.mutation_log) > 0
