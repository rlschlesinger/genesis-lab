"""Two kinds of food and a heritable diet (Milestone 6, increment 6.8, D-063).

The mechanics on their own: food kinds and where they come from, what a meal is worth, the
ledger, how the diet is inherited and mutated, how the diet seeker chooses, and that worlds
with one food are exactly what they were.
"""

import math
import statistics
from pathlib import Path

import numpy as np
import pydantic
import pytest

from genesis.analytics.experiments import apply_changes
from genesis.core.config import MutationConfig, SimulationConfig, load_config
from genesis.core.simulation import RngStreams, Simulation
from genesis.evolution.mutation import mutate_value
from genesis.intelligence.controllers import DietSeeker, NearestFoodSeeker
from genesis.intelligence.sensors import KindSenses, Observations

CONFIGS = Path(__file__).parents[2] / "configs"
DIETS = CONFIGS / "diets.yaml"


def diets(**changes) -> SimulationConfig:
    return apply_changes(load_config(DIETS), changes)


def flatten(d: dict, prefix: str = "") -> dict:
    out = {}
    for key, value in d.items():
        if isinstance(value, dict):
            out.update(flatten(value, f"{prefix}{key}."))
        else:
            out[f"{prefix}{key}"] = value
    return out


# --- Config ---------------------------------------------------------------------------------


def test_diets_config_differs_from_evolution_only_where_intended():
    evolution = flatten(load_config(CONFIGS / "evolution.yaml").model_dump())
    two = flatten(load_config(DIETS).model_dump())
    differing = {k for k in two if two[k] != evolution.get(k)}
    assert differing == {
        "food.energy_value",
        "organisms.initial_count",
        "organisms.controller",
        "genome.speed.mutable",
        "genome.sense_range.mutable",
        "genome.metabolic_rate.mutable",
        "genome.reproduction_threshold.mutable",
        *{k for k in two if k.startswith("resources.")},
    }


def test_older_configs_have_no_resources_section_in_their_dump():
    for name in ("default.yaml", "evolution.yaml", "neural.yaml", "predators.yaml"):
        assert "resources" not in load_config(CONFIGS / name).model_dump()


def test_the_diet_seeker_needs_two_foods_and_the_diet_stays_in_0_1():
    raw = load_config(CONFIGS / "evolution.yaml").model_dump()
    raw["organisms"]["controller"] = "diet_seeker"
    with pytest.raises(pydantic.ValidationError, match="needs a resources"):
        SimulationConfig.model_validate(raw)
    raw = load_config(DIETS).model_dump()
    raw["resources"]["diet"]["max"] = 1.5
    with pytest.raises(pydantic.ValidationError, match=r"within \[0, 1\]"):
        SimulationConfig.model_validate(raw)


# --- Streams and food -----------------------------------------------------------------------


def test_the_resources_stream_leaves_every_earlier_stream_unchanged():
    streams = RngStreams.from_seed(11)
    old = np.random.SeedSequence(11).spawn(8)
    names = ["setup", "food", "controller", "reproduction", "tiebreak", "mutation", "brain",
             "predators"]  # fmt: skip
    for name, seed in zip(names, old, strict=True):
        assert getattr(streams, name).random() == np.random.default_rng(seed).random()


def test_food_appears_where_it_would_with_one_food_and_half_of_it_is_b():
    one = load_config(DIETS).model_dump()
    del one["resources"]
    one["organisms"]["controller"] = "nearest_food_seeker"
    single = Simulation(SimulationConfig.model_validate(one))
    double = Simulation(diets())
    assert np.array_equal(single.world.food.positions, double.world.food.positions)
    assert not single.world.food.kinds.any()  # one food: every item is A
    kinds = double.world.food.kinds
    assert len(kinds) == double.world.food.count and set(kinds.tolist()) == {0, 1}
    assert 0.35 < kinds.mean() < 0.65  # 150 items, half B on average


def test_eaten_food_takes_its_kind_with_it():
    sim = Simulation(diets())
    for _ in range(200):
        sim.step()
        assert len(sim.world.food.kinds) == sim.world.food.count


# --- What a meal is worth -------------------------------------------------------------------


def meals_of(sim: Simulation) -> list:
    return [e for e in sim.events_this_tick if e.kind == "meal"]


def test_a_meal_gives_the_diets_share_and_the_rest_leaves_through_the_ledger():
    # With mutation off every diet stays at the founders' 0.5: with k = 2 every meal gives
    # V / 4, of either kind (children's diets would otherwise drift a little from 0.5).
    sim = Simulation(diets(**{"mutation.enabled": False}))
    value = sim.config.food.energy_value
    eaten = 0
    for _ in range(50):
        sim.step()
        for meal in meals_of(sim):
            assert meal.energy == value * 0.5**2
            eaten += 1
    assert eaten > 0
    assert sim.ledger.undigested == pytest.approx(eaten * value * 0.75, rel=1e-12)


@pytest.mark.parametrize(("d", "kind", "share"), [(0.0, 0, 1.0), (0.0, 1, 0.0), (1.0, 1, 1.0),
                                                   (0.2, 0, 0.64), (0.2, 1, 0.04)])  # fmt: skip
def test_what_each_diet_keeps_of_each_kind(d, kind, share):
    sim = Simulation(diets())
    org = sim.organisms[0]
    org.diet = d
    assert sim._digests(org)[kind] == pytest.approx(share)


def test_a_neutral_diet_digests_as_the_founders_do_whatever_its_value():
    sim = Simulation(diets(**{"resources.diet.neutral": True}))
    org = sim.organisms[0]
    for d in (0.0, 0.3, 1.0):
        org.diet = d
        assert sim._digests(org) == (0.25, 0.25)


def test_the_energy_ledger_balances_over_a_long_two_food_run():
    # Checked inside every step; a meal's undigested part missing from the ledger would raise.
    sim = Simulation(diets(**{"run.max_ticks": 2000}))
    sim.run()
    assert sim.tick == 2000


# --- Inheritance ----------------------------------------------------------------------------


def test_the_diet_mutates_like_a_gene_and_stays_in_its_bounds():
    gene = load_config(DIETS).resources.diet
    on = MutationConfig(enabled=True, rate=1.0, size=0.5)
    rng = np.random.default_rng(3)
    values = [mutate_value(0.95, gene, on, rng) for _ in range(500)]
    assert all(0.0 <= v <= 1.0 for v in values) and len(set(values)) > 400
    off = MutationConfig(enabled=False, rate=1.0, size=0.5)
    assert mutate_value(0.3, gene, off, np.random.default_rng(3)) == 0.3


def test_children_inherit_their_parents_diet_with_small_changes():
    sim = Simulation(diets(**{"run.max_ticks": 3000}))
    sim.run()
    everyone = {o.id: o for o in [*sim.organisms, *sim.dead]}
    steps = [abs(o.diet - everyone[o.parent_id].diet) for o in everyone.values()
             if o.parent_id is not None]  # fmt: skip
    assert steps and statistics.median(steps) == 0.0  # most births: rate 0.1, no change
    assert 0 < max(steps) < 0.3  # a mutation moves d by a few hundredths (size 0.05)
    assert statistics.pstdev(o.diet for o in sim.organisms) > 0.0


def test_two_food_worlds_replay_exactly_and_the_diet_is_in_the_digest():
    a, b = Simulation(diets()), Simulation(diets())
    for _ in range(300):
        a.step()
        b.step()
    assert a.state_digest() == b.state_digest()
    b.organisms[0].diet = b.organisms[0].diet + 1e-12
    assert a.state_digest() != b.state_digest()


# --- The diet seeker ------------------------------------------------------------------------


def kind_obs(found_a, dist_a, found_b, dist_b, worth_a, worth_b) -> Observations:
    n = len(found_a)
    a = np.array(found_a, bool)
    b = np.array(found_b, bool)
    return Observations(
        food_found=a | b, food_distance=np.minimum(dist_a, dist_b), food_bearing=np.zeros(n),
        energy=np.full(n, 50.0),
        kinds=KindSenses(
            a, np.array(dist_a, float), np.full(n, 0.5),
            b, np.array(dist_b, float), np.full(n, -0.5),
            np.array(worth_a, float), np.array(worth_b, float),
        ),
    )  # fmt: skip


def test_the_diet_seeker_heads_for_the_most_energy_per_distance():
    inf = math.inf
    obs = kind_obs(
        found_a=[True, True, True, False, False],
        dist_a=[10, 2, 5, inf, inf],
        found_b=[True, True, True, True, False],
        dist_b=[4, 10, 5, 3, inf],
        worth_a=[1.0, 0.25, 0.25, 1.0, 0.25],
        worth_b=[0.0, 0.25, 0.25, 0.0, 0.25],
    )
    actions = DietSeeker().decide(obs, np.random.default_rng(0))
    wander = (
        NearestFoodSeeker()
        .decide(
            Observations(np.zeros(5, bool), np.full(5, inf), np.zeros(5), np.full(5, 50.0)),
            np.random.default_rng(0),
        )
        .turn
    )
    assert actions.turn[0] == 0.5  # a specialist on A ignores the nearer B, worth nothing
    assert actions.turn[1] == 0.5  # equal worth: the nearer kind
    assert actions.turn[2] == 0.5  # an exact tie: A
    assert actions.turn[3] == wander[3]  # only worthless food in sight: wander
    assert actions.turn[4] == wander[4]  # nothing in sight: wander, the seeker's draws
    assert (actions.throttle == 1.0).all()
