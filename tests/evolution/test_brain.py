"""Tests for brains as genes: founders' random weights, mutation, inheritance in a running
simulation, and that runs without brains are untouched."""

from pathlib import Path

import numpy as np
import pytest

from genesis.core.config import BrainConfig, SimulationConfig, config_hash, load_config
from genesis.core.simulation import RngStreams, Simulation
from genesis.evolution.brain import founder_brains, mutate_brain, reflect_array
from genesis.evolution.mutation import reflect
from genesis.intelligence.neural import PARAMETER_COUNT, Brain

CONFIGS = Path(__file__).parents[2] / "configs"


def with_brains(path="evolution.yaml", **brain) -> SimulationConfig:
    raw = load_config(CONFIGS / path).model_dump()
    raw["brain"] = brain
    return SimulationConfig.model_validate(raw)


# --- reflection and founders ----------------------------------------------------------------


def test_reflect_array_matches_the_scalar_gene_rule():
    values = np.random.default_rng(0).normal(0, 10, 5000)
    expected = [reflect(float(v), -4.0, 4.0) for v in values]
    assert reflect_array(values, -4.0, 4.0).tolist() == expected


def test_each_founder_gets_its_own_brain_within_the_limits():
    brains = founder_brains(30, BrainConfig(), np.random.default_rng(1))
    vectors = np.array([b.to_vector() for b in brains])
    assert vectors.shape == (30, PARAMETER_COUNT)
    assert len({v.tobytes() for v in vectors}) == 30  # all different
    assert np.all(np.abs(vectors) <= 4.0)
    assert vectors.std() == pytest.approx(0.5, rel=0.05)  # initial_sd


def test_founder_brains_are_reproducible_and_drawn_in_founder_order():
    a = founder_brains(5, BrainConfig(), np.random.default_rng(2))
    rng = np.random.default_rng(2)
    one_at_a_time = [founder_brains(1, BrainConfig(), rng)[0] for _ in range(5)]
    for x, y in zip(a, one_at_a_time, strict=True):
        assert x.to_vector().tobytes() == y.to_vector().tobytes()


# --- mutation -------------------------------------------------------------------------------


def parent_brain() -> Brain:
    return founder_brains(1, BrainConfig(), np.random.default_rng(3))[0]


def test_rate_zero_returns_the_parent_brain_but_still_draws():
    parent = parent_brain()
    rng = np.random.default_rng(4)
    child, changed = mutate_brain(parent, BrainConfig(mutation_rate=0.0), rng)
    assert child is parent and changed == 0
    # 62 uniform + 62 normal draws were consumed regardless: the next draw matches a stream
    # that made those draws explicitly.
    reference = np.random.default_rng(4)
    reference.random(PARAMETER_COUNT)
    reference.normal(size=PARAMETER_COUNT)
    assert rng.random() == reference.random()


def test_mutation_changes_about_rate_of_the_weights_and_never_the_parent():
    parent = parent_brain()
    before = parent.to_vector().copy()
    rng = np.random.default_rng(5)
    counts = [mutate_brain(parent, BrainConfig(mutation_rate=0.1), rng)[1] for _ in range(2000)]
    assert np.mean(counts) == pytest.approx(0.1 * PARAMETER_COUNT, rel=0.05)
    np.testing.assert_array_equal(parent.to_vector(), before)


def test_mutation_steps_have_the_configured_size_and_no_direction():
    parent = Brain.from_vector(np.zeros(PARAMETER_COUNT))  # far from the limits
    rng = np.random.default_rng(6)
    cfg = BrainConfig(mutation_rate=1.0, mutation_size=0.2)
    steps = np.concatenate([mutate_brain(parent, cfg, rng)[0].to_vector() for _ in range(500)])
    assert steps.std() == pytest.approx(0.2, rel=0.03)
    assert abs(steps.mean()) < 0.01


def test_huge_mutations_stay_within_the_limits():
    parent = parent_brain()
    rng = np.random.default_rng(7)
    cfg = BrainConfig(mutation_rate=1.0, mutation_size=50.0)
    for _ in range(200):
        parent, _ = mutate_brain(parent, cfg, rng)
        assert np.all(np.abs(parent.to_vector()) <= cfg.weight_limit)


# --- in a running simulation ----------------------------------------------------------------


def test_rng_streams_are_append_only():
    """Adding the brain stream must not change the six existing streams (D-012)."""
    streams = RngStreams.from_seed(42)
    children = np.random.SeedSequence(42).spawn(6)
    for name, child in zip(
        ["setup", "food", "controller", "reproduction", "tiebreak", "mutation"],
        children,
        strict=True,
    ):
        assert getattr(streams, name).random() == np.random.default_rng(child).random()


def test_rule_based_configs_have_no_brain_section_and_unchanged_hashes():
    config = load_config(CONFIGS / "default.yaml")
    assert config.brain is None
    assert "brain" not in config.model_dump(mode="json")
    assert config_hash(config) == config_hash(SimulationConfig.model_validate(config.model_dump()))
    assert all(o.brain is None for o in Simulation(config).organisms)


def test_brains_do_not_change_anything_else_yet():
    """Until 4.4 no controller reads brains, and they use their own stream: with or without
    brains, the population history must be identical tick for tick."""
    plain = load_config(CONFIGS / "evolution.yaml")
    plain = SimulationConfig.model_validate(
        {**plain.model_dump(), "run": {**plain.run.model_dump(), "max_ticks": 400}}
    )
    brained = SimulationConfig.model_validate({**plain.model_dump(), "brain": {}})
    a, b = Simulation(plain).run(), Simulation(brained).run()
    assert a == b
    assert sum(s.births for s in b) > 20  # the test covers inheritance, not just founders


def test_newborns_inherit_their_parents_brain():
    """With brain mutation off, every child's brain equals its parent's, bit for bit."""
    sim = Simulation(with_brains(mutation_rate=0.0))
    by_id = {o.id: o for o in sim.organisms}
    for _ in range(300):
        sim.step()
        by_id.update({o.id: o for o in sim.organisms})
    children = [o for o in by_id.values() if o.parent_id is not None]
    assert len(children) > 20
    for child in children:
        parent = by_id[child.parent_id]
        assert child.brain.to_vector().tobytes() == parent.brain.to_vector().tobytes()


def test_mutated_children_differ_from_their_parent_in_a_few_weights():
    sim = Simulation(with_brains(mutation_rate=0.1))
    by_id = {o.id: o for o in sim.organisms}
    for _ in range(300):
        sim.step()
        by_id.update({o.id: o for o in sim.organisms})
    differing = [
        int(np.count_nonzero(o.brain.to_vector() != by_id[o.parent_id].brain.to_vector()))
        for o in by_id.values()
        if o.parent_id is not None
    ]
    assert len(differing) > 20
    assert np.mean(differing) == pytest.approx(0.1 * PARAMETER_COUNT, rel=0.3)
    assert max(differing) < PARAMETER_COUNT


def test_mutation_disabled_freezes_brains_too():
    raw = with_brains(mutation_rate=0.5).model_dump()
    raw["mutation"]["enabled"] = False
    sim = Simulation(SimulationConfig.model_validate(raw))
    founders = {o.id: o.brain for o in sim.organisms}
    for _ in range(300):
        sim.step()
    lineage_brains = {o.founder_id: o.brain for o in sim.organisms}
    assert all(lineage_brains[f] is founders[f] for f in lineage_brains)


def test_brain_runs_are_deterministic_and_the_digest_sees_weights():
    a, b = Simulation(with_brains()), Simulation(with_brains())
    for _ in range(200):
        a.step()
        b.step()
    assert a.state_digest() == b.state_digest()
    # Identical except one founder weight nudged by 1e-9: the digest must notice.
    c = Simulation(with_brains())
    vector = c.organisms[0].brain.to_vector().copy()
    vector[0] += 1e-9
    c.organisms[0].brain = Brain.from_vector(vector)
    assert Simulation(with_brains()).state_digest() != c.state_digest()


# --- founders given specific brains (E007's evaluation worlds) -------------------------------


def given_weights(n: int, seed: int = 11) -> list[list[float]]:
    return np.random.default_rng(seed).uniform(-4, 4, (n, PARAMETER_COUNT)).tolist()


def test_config_brain_size_matches_the_network():
    from genesis.core.config import BRAIN_PARAMETERS

    assert BRAIN_PARAMETERS == PARAMETER_COUNT


def test_founders_get_exactly_the_given_brains_and_draw_nothing():
    weights = given_weights(30)
    sim = Simulation(with_brains(founder_weights=weights))
    for org, vector in zip(sim.organisms, weights, strict=True):
        assert org.brain.to_vector().tolist() == vector
    # The brain stream is untouched: its next number is its first.
    fresh = RngStreams.from_seed(sim.config.run.seed).brain
    assert sim.rng.brain.random() == fresh.random()


def test_given_brains_survive_a_trip_through_run_json():
    """Weights are stored in the config as JSON; Python's float repr makes that exact."""
    import json

    config = with_brains(founder_weights=given_weights(30))
    again = SimulationConfig.model_validate(json.loads(json.dumps(config.model_dump(mode="json"))))
    assert again.brain.founder_weights == config.brain.founder_weights
    assert config_hash(again) == config_hash(config)


@pytest.mark.parametrize(
    "weights, message",
    [
        (given_weights(29), "29 brains for 30 founders"),
        ([[0.0] * 61] * 30, "has 61 numbers"),
        ([[4.5] * 62] * 30, "exceeds weight_limit"),
        ([[float("nan")] * 62] * 30, "not finite"),
    ],
)
def test_bad_founder_weights_are_rejected(weights, message):
    with pytest.raises(ValueError, match=message):
        with_brains(founder_weights=weights)
