"""Tests for Organism and Traits: energy bookkeeping, death rules, and data safety."""

import dataclasses
from pathlib import Path

import pytest

from genesis.core.config import load_config
from genesis.core.organism import DeathCause, Organism
from genesis.evolution.genome import Genome, express

DEFAULT_CONFIG = Path(__file__).parents[2] / "configs" / "default.yaml"

GENOME = Genome.from_config(load_config(DEFAULT_CONFIG).genome)
TRAITS = express(GENOME)


def make_organism(**overrides) -> Organism:
    fields = dict(
        id=1, parent_id=None, founder_id=1, generation=0, birth_tick=0,
        genome=GENOME, traits=TRAITS, x=10.0, y=10.0, heading=0.0, energy=50.0,
    )  # fmt: skip
    fields.update(overrides)
    return Organism(**fields)


# --- Traits -------------------------------------------------------------------------------


def test_traits_are_immutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        TRAITS.speed = 99.0


# --- Construction -------------------------------------------------------------------------


def test_new_organism_starts_alive_with_zeroed_totals():
    org = make_organism()
    assert org.alive and org.age == 0
    assert org.death_tick is None and org.death_cause is None
    totals = (
        org.energy_gained,
        org.energy_spent,
        org.energy_invested,
        org.food_eaten,
        org.offspring_count,
    )
    assert totals == (0, 0, 0, 0, 0)


def test_misspelled_attribute_raises():
    org = make_organism()
    with pytest.raises(AttributeError):
        org.enrgy = 5.0


def test_positional_construction_rejected():
    # kw_only=True: guards against swapping two numbers by position.
    with pytest.raises(TypeError):
        Organism(1, None, 1, 0, 0, GENOME, TRAITS, 10.0, 10.0, 0.0, 50.0)


# --- Energy -------------------------------------------------------------------------------


def test_spend_deducts_and_records():
    org = make_organism(energy=50.0)
    assert org.spend(10.0) == 10.0
    assert org.energy == 40.0
    assert org.energy_spent == 10.0


def test_overspending_stops_at_zero_and_reports_actual_amount():
    org = make_organism(energy=0.3)
    paid = org.spend(0.5)
    assert paid == pytest.approx(0.3)  # only what it had
    assert org.energy == 0.0
    assert org.energy_spent == pytest.approx(0.3)  # the ledger sees 0.3, not 0.5


def test_reaching_zero_energy_does_not_kill_immediately():
    # Deaths are processed in their own tick step, never mid-update.
    org = make_organism(energy=1.0)
    org.spend(5.0)
    assert org.energy == 0.0
    assert org.alive


def test_negative_spend_rejected():
    with pytest.raises(ValueError):
        make_organism().spend(-1.0)


def test_eat_adds_energy_and_counts_food():
    org = make_organism(energy=10.0)
    org.eat(20.0)
    org.eat(20.0)
    assert org.energy == 50.0
    assert org.energy_gained == 40.0
    assert org.food_eaten == 2


@pytest.mark.parametrize("bad", [0.0, -5.0])
def test_eating_non_positive_energy_rejected(bad):
    with pytest.raises(ValueError):
        make_organism().eat(bad)


def test_energy_bookkeeping_balances():
    # start + gained - spent == current: the per-organism version of the energy ledger.
    org = make_organism(energy=50.0)
    for _ in range(10):
        org.spend(7.3)
        org.eat(4.1)
    assert org.energy == pytest.approx(50.0 + org.energy_gained - org.energy_spent)


# --- Death --------------------------------------------------------------------------------


def test_healthy_organism_survives():
    assert make_organism(energy=10.0, age=5).cause_of_death(max_age=100) is None


def test_zero_energy_means_starvation():
    assert make_organism(energy=0.0).cause_of_death(max_age=None) is DeathCause.STARVATION


def test_reaching_max_age_means_old_age():
    org = make_organism(age=100)
    assert org.cause_of_death(max_age=100) is DeathCause.OLD_AGE
    assert make_organism(age=99).cause_of_death(max_age=100) is None


def test_no_max_age_means_no_old_age_death():
    assert make_organism(age=10**9).cause_of_death(max_age=None) is None


def test_starvation_takes_precedence_over_old_age():
    org = make_organism(energy=0.0, age=100)
    assert org.cause_of_death(max_age=100) is DeathCause.STARVATION


def test_cause_of_death_does_not_change_state():
    org = make_organism(energy=0.0)
    org.cause_of_death(max_age=None)
    assert org.alive


def test_die_records_tick_and_cause():
    org = make_organism()
    org.die(tick=42, cause=DeathCause.OLD_AGE)
    assert not org.alive
    assert org.death_tick == 42
    assert org.death_cause == "old_age"  # StrEnum compares equal to its string value


@pytest.mark.parametrize(
    "action",
    [
        lambda o: o.spend(1.0),
        lambda o: o.eat(10.0),
        lambda o: o.die(tick=2, cause=DeathCause.STARVATION),
    ],
    ids=["spend", "eat", "die-twice"],
)
def test_dead_organisms_cannot_act(action):
    org = make_organism()
    org.die(tick=1, cause=DeathCause.STARVATION)
    with pytest.raises(RuntimeError, match="is dead"):
        action(org)


# --- Reproduction cost --------------------------------------------------------------------


def test_can_reproduce_at_threshold():
    assert make_organism(energy=80.0).can_reproduce  # threshold is 80: "at or above"
    assert not make_organism(energy=79.9).can_reproduce


def test_pay_for_offspring_deducts_and_records_separately_from_spending():
    org = make_organism(energy=100.0)
    org.pay_for_offspring(transfer=40.0, overhead=10.0)
    assert org.energy == 50.0
    assert org.energy_invested == 50.0
    assert org.energy_spent == 0.0  # living costs and offspring costs are kept apart
    assert org.offspring_count == 1


def test_unaffordable_offspring_raises_instead_of_clamping():
    with pytest.raises(RuntimeError, match="cannot afford"):
        make_organism(energy=30.0).pay_for_offspring(transfer=40.0, overhead=10.0)


# --- spend_all: Organism.spend for a whole population, bit for bit (D-038) --------------------


def spend_in_a_loop(energies, *costs):
    """The reference: one Organism per entry, charged with spend() in the given order."""
    organisms = [make_organism(energy=e) for e in energies]
    paid = [[] for _ in costs]
    for org_index, org in enumerate(organisms):
        for cost_index, cost in enumerate(costs):
            paid[cost_index].append(org.spend(float(cost[org_index])))
    return paid, [o.energy for o in organisms], [o.energy_spent for o in organisms]


@pytest.mark.parametrize("seed", range(5))
def test_spend_all_matches_spend_one_at_a_time(seed):
    import numpy as np

    from genesis.core.organism import spend_all

    rng = np.random.default_rng(seed)
    n = 500
    # Energies near zero so that many organisms run out part-way through the three costs.
    energies = rng.choice([0.0, 0.1, 0.25, 0.3, 1.0, 50.0], size=n) * rng.uniform(0.9, 1.1, n)
    energies[::7] = 0.0
    costs = (rng.uniform(0, 0.3, n), rng.choice([0.0, 0.08], size=n), rng.uniform(0, 0.4, n))
    paid, energy, spent = spend_all(energies, np.zeros(n), *costs)
    ref_paid, ref_energy, ref_spent = spend_in_a_loop(energies, *costs)
    for a, b in zip(paid, ref_paid, strict=True):
        assert a.tolist() == b
    assert energy.tolist() == ref_energy
    assert spent.tolist() == ref_spent
    assert (energy >= 0).all()


def test_spend_all_rejects_negative_costs_and_accepts_an_empty_population():
    import numpy as np

    from genesis.core.organism import spend_all

    with pytest.raises(ValueError, match="negative"):
        spend_all(np.array([5.0]), np.zeros(1), np.array([-1.0]))
    paid, energy, spent = spend_all(np.empty(0), np.empty(0), np.empty(0), np.empty(0))
    assert len(paid) == 2 and energy.size == 0 and spent.size == 0


def test_spend_all_leaves_its_inputs_untouched():
    import numpy as np

    from genesis.core.organism import spend_all

    energy, spent, cost = np.array([1.0, 2.0]), np.array([0.0, 0.0]), np.array([0.5, 3.0])
    spend_all(energy, spent, cost)
    assert energy.tolist() == [1.0, 2.0] and spent.tolist() == [0.0, 0.0]
